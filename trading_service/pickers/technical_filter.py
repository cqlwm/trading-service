"""技术分析独立阶段：把技术指标计算从选币器中解耦出来。

作为 ISymbolFilter 实现，逐个拉取 K 线并调用 ITechnicalAnalyzer，
将 CrossSignal 的字段回填到 SymbolInfo。

关键不变量：纯增强——analyzer 返回 None（远离均线、无穿越、K线不足）时，
SymbolInfo 数量不减、技术字段保持默认值。买入信号判定仍由策略负责。
"""
from __future__ import annotations

import logging

from trading_service.clients.protocols import KlineClient
from trading_service.pickers.technical_analyzer import ITechnicalAnalyzer
from trading_service.pickers.pipeline import ISymbolFilter
from trading_service.pickers.base import SymbolInfo

logger = logging.getLogger(__name__)

# 计算 SMA200 所需的最小 K 线数（201 根才能得到第一个 SMA 值，留 1 根余量取 210）
KLINE_LIMIT_FOR_SMA200 = 210


class TechnicalAnalysisFilter(ISymbolFilter):
    """技术分析过滤器：拉K线 + 计算信号 + 回填字段（纯增强，不丢弃）。"""

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
        """拉取单个 symbol 的 K 线并回填技术字段（原地修改）。"""
        klines = self.client.get_future_klines(
            symbol=info.symbol,
            interval=self.kline_interval,
            limit=KLINE_LIMIT_FOR_SMA200,
        )

        signal = self.analyzer.detect_200sma_signal(klines, info.symbol)
        if signal:
            info.sma_200 = signal.sma_200
            info.price_vs_sma200_percent = signal.distance_percent
            info.cross_signal = signal.cross_type
            info.cross_ago = signal.cross_ago
            info.volatility_10 = signal.volatility_10
            info.is_sideways_bottom = signal.is_sideways
