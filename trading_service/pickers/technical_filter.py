"""技术分析独立阶段：把技术指标计算从选币器中解耦出来。

作为 ISymbolFilter 实现，逐个拉取 K 线并调用 ITechnicalAnalyzer，
将 CrossSignal 的字段回填到 SymbolInfo，同时构建 DataFrame 承载 K 线和指标。

关键不变量：纯增强--analyzer 返回 None（远离均线、无穿越、K线不足）时，
SymbolInfo 数量不减、技术字段保持默认值。买入信号判定仍由策略负责。
"""
from __future__ import annotations

import logging

import pandas as pd
import talib

from trading_service.clients.protocols import KlineClient
from trading_service.pickers.technical_analyzer import ITechnicalAnalyzer
from trading_service.pickers.pipeline import ISymbolFilter
from trading_service.pickers.base import SymbolInfo

logger = logging.getLogger(__name__)

# 计算 SMA200 所需的最小 K 线数（201 根才能得到第一个 SMA 值，留 1 根余量取 210）
KLINE_LIMIT_FOR_SMA200 = 210


class TechnicalAnalysisFilter(ISymbolFilter):
    """技术分析过滤器：拉K线 + 构建 DataFrame + 计算指标 + 回填字段（纯增强，不丢弃）。

    K 线数据在 DataFrame 中承载，后续检测器和策略复用，不重新拉取。
    """

    def __init__(
        self,
        analyzer: ITechnicalAnalyzer,
        client: KlineClient,
        kline_interval: str = "4h",
    ) -> None:
        self.analyzer = analyzer
        self.client = client
        self.kline_interval = kline_interval

    async def apply(self, infos: list[SymbolInfo]) -> list[SymbolInfo]:
        """对每个 SymbolInfo 拉取 K 线并回填技术分析字段。

        纯增强：单个 symbol 分析失败或无信号时不丢弃该 SymbolInfo，
        其技术字段保持默认值（None/False）。
        """
        if not infos:
            return []

        import asyncio
        loop = asyncio.get_event_loop()

        for info in infos:
            try:
                await loop.run_in_executor(None, self._enrich_one, info)
            except Exception as e:  # noqa: BLE001
                logger.debug(f"{info.symbol}: 技术分析失败 - {e}")

        return infos

    def _enrich_one(self, info: SymbolInfo) -> None:
        """拉取单个 symbol 的 K 线，构建 DataFrame，回填技术字段（原地修改）。"""
        klines = self.client.get_future_klines(
            symbol=info.symbol,
            interval=self.kline_interval,
            limit=KLINE_LIMIT_FOR_SMA200,
        )

        if len(klines) < 201:
            return

        # 构建 DataFrame（OHLCV）
        df = pd.DataFrame({
            "datetime": [k.close_time for k in klines],
            "open": [k.open_price_float for k in klines],
            "high": [k.high_price_float for k in klines],
            "low": [k.low_price_float for k in klines],
            "close": [k.close_price_float for k in klines],
            "volume": [k.volume_float for k in klines],
        })

        # TA-Lib 计算 SMA200
        df["sma_200"] = talib.SMA(df["close"].to_numpy(), timeperiod=200)

        # 金叉/死叉检测（保留现有复合逻辑）
        signal = self.analyzer.detect_200sma_signal(klines, info.symbol)
        if signal:
            # 将信号信息写入 DataFrame 最后一行
            df.loc[df.index[-1], "cross_signal"] = signal.cross_type.value
            df.loc[df.index[-1], "price_vs_sma200_percent"] = signal.distance_percent
            df.loc[df.index[-1], "volatility_10"] = signal.volatility_10
            df.loc[df.index[-1], "is_sideways_bottom"] = signal.is_sideways

            # 回填旧字段（向后兼容）
            info.sma_200 = signal.sma_200
            info.price_vs_sma200_percent = signal.distance_percent
            info.cross_signal = signal.cross_type
            info.cross_ago = signal.cross_ago
            info.volatility_10 = signal.volatility_10
            info.is_sideways_bottom = signal.is_sideways

        info.klines = df
