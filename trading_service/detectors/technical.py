"""技术分析信号检测器。

接收策略选好的候选币（已含技术分析字段），产出金叉/死叉/横盘信号。
不再自己组装 SelectionPipeline，由策略传入候选币。
"""

from __future__ import annotations

from trading_service.detectors.base import SignalDetector, SignalResult
from trading_service.pickers import SymbolInfo
from trading_service.repository import TradingRepository
from trading_service.types import CrossSignalType


class TechnicalSignalDetector(SignalDetector):
    """技术分析信号检测器。"""

    name = "technical_signal"

    def __init__(self, repo: TradingRepository) -> None:
        super().__init__(repo)

    async def detect(self, candidates: list[SymbolInfo]) -> list[SignalResult]:
        """对候选币进行技术分析信号检测。

        候选币应已由 TechnicalAnalysisFilter 回填 cross_signal 等技术字段。
        """
        results: list[SignalResult] = []
        for info in candidates:
            if info.cross_signal == CrossSignalType.GOLDEN:
                results.append(SignalResult(
                    symbol=info.symbol,
                    signal_type="golden_cross",
                    direction="bullish",
                    severity=3,
                    description=f"{info.symbol} 金叉向上穿越 SMA200",
                    metadata={
                        "cross_signal": info.cross_signal.value,
                        "price_vs_sma200": info.price_vs_sma200_percent,
                        "sma_200": info.sma_200,
                    },
                ))
            elif info.cross_signal == CrossSignalType.DEAD:
                results.append(SignalResult(
                    symbol=info.symbol,
                    signal_type="dead_cross",
                    direction="bearish",
                    severity=3,
                    description=f"{info.symbol} 死叉向下穿越 SMA200",
                    metadata={
                        "cross_signal": info.cross_signal.value,
                        "price_vs_sma200": info.price_vs_sma200_percent,
                        "sma_200": info.sma_200,
                    },
                ))
            if info.is_sideways_bottom:
                results.append(SignalResult(
                    symbol=info.symbol,
                    signal_type="sideways_bottom",
                    direction="neutral",
                    severity=2,
                    description=f"{info.symbol} 底部横盘",
                    metadata={"volatility_10": info.volatility_10},
                ))
        return results
