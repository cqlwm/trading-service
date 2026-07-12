"""技术分析独立阶段：把技术指标计算从选币器中解耦出来。

作为 ISymbolFilter 实现，逐个拉取 K 线并调用 ITechnicalAnalyzer，
将 CrossSignal 的字段写入 klines DataFrame。

关键不变量：纯增强--analyzer 返回 None（远离均线、无穿越、K线不足）时，
SymbolInfo 数量不减、klines DataFrame 不含信号列。买入信号判定仍由策略负责。
"""
from __future__ import annotations

import logging

import talib

from trading_service.clients.protocols import KlineClient
from trading_service.pickers.kline_utils import build_ohlcv_dataframe
from trading_service.pickers.technical_analyzer import ITechnicalAnalyzer
from trading_service.pickers.pipeline import ISymbolFilter
from trading_service.pickers.base import SymbolInfo

logger = logging.getLogger(__name__)

# 计算 SMA200 所需的最小 K 线数（201 根才能得到第一个 SMA 值，留 1 根余量取 210）
KLINE_LIMIT_FOR_SMA200 = 210


class TechnicalAnalysisFilter(ISymbolFilter):
    """技术分析过滤器：拉K线 + 构建 DataFrame + 计算指标（纯增强，不丢弃）。

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
        """对每个 SymbolInfo 拉取 K 线并构建 klines DataFrame。

        纯增强：单个 symbol 分析失败或无信号时不丢弃该 SymbolInfo，
        其 klines DataFrame 中不写入信号列。
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
        """拉取单个 symbol 的 K 线，构建 DataFrame（原地修改）。"""
        klines = self.client.get_future_klines(
            symbol=info.symbol,
            interval=self.kline_interval,
            limit=KLINE_LIMIT_FOR_SMA200,
        )

        if len(klines) < 201:
            return

        # 构建 DataFrame（OHLCV）-- BinanceFutureKline 到此为止，不再向下传递
        df = build_ohlcv_dataframe(klines)

        # TA-Lib 计算 SMA200
        df["sma_200"] = talib.SMA(df["close"].to_numpy(dtype=float), timeperiod=200)

        # 金叉/死叉检测（基于 DataFrame 的复合判定）
        signal = self.analyzer.detect_200sma_signal(df, info.symbol)
        if signal:
            # 将信号信息写入 DataFrame 最后一行
            df.loc[df.index[-1], "cross_signal"] = signal.cross_type.value
            df.loc[df.index[-1], "price_vs_sma200_percent"] = signal.distance_percent
            df.loc[df.index[-1], "volatility_10"] = signal.volatility_10
            df.loc[df.index[-1], "is_sideways_bottom"] = signal.is_sideways

        info.klines[self.kline_interval] = df
