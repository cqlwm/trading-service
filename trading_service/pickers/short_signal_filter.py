"""做空信号过滤器：从候选列表中保留有做空信号的币种。

依赖 TechnicalAnalysisFilter 先回填技术字段（cross_signal、price_vs_sma200_percent 等）。
设计为「丢弃式」过滤器：不符合做空条件的直接移除，与 TechnicalAnalysisFilter 的「纯增强不丢弃」互补。
"""

from __future__ import annotations

import logging

from trading_service.pickers.base import SymbolInfo
from trading_service.pickers.pipeline import ISymbolFilter
from trading_service.types import CrossSignalType

logger = logging.getLogger(__name__)


class ShortSignalFilter(ISymbolFilter):
    """做空信号过滤器。

    保留条件（满足任一即保留）：
    - 死叉（cross_signal == DEAD）：收盘价从上向下穿越 SMA200，趋势转空
    - 远离均线顶部（price_vs_sma200_percent > overbought_threshold）：
      价格远高于 200 均线，有均值回归的可能

    丢弃：金叉、靠近均线、无信号、或技术字段未回填的币种。
    """

    def __init__(self, overbought_threshold: float = 15.0) -> None:
        self._overbought_threshold = overbought_threshold

    async def apply(self, infos: list[SymbolInfo]) -> list[SymbolInfo]:
        """过滤出有做空信号的币种。"""
        result = [info for info in infos if self._is_short_signal(info)]

        logger.info(
            f"做空信号过滤: {len(infos)} -> {len(result)} "
            f"(阈值={self._overbought_threshold}%)"
        )
        return result

    def _is_short_signal(self, info: SymbolInfo) -> bool:
        """判定是否有做空信号。"""
        # 死叉
        if info.cross_signal == CrossSignalType.DEAD:
            return True

        # 远离均线顶部（price_vs_sma200_percent > 阈值）
        if (
            info.price_vs_sma200_percent is not None
            and info.price_vs_sma200_percent > self._overbought_threshold
        ):
            return True

        return False
