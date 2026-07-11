"""技术分析信号检测器。

扫描候选币种的技术指标，产出金叉/死叉/横盘底部等信号。
这些信号可被策略消费（如微市值策略根据金叉开仓），
也可不被消费（仅落盘供内容生成）。
"""

from __future__ import annotations

from trading_service.clients import BinanceClient
from trading_service.detectors.base import SignalDetector, SignalResult
from trading_service.pickers import (
    AlphaTokenSource,
    SelectionPipeline,
    TechnicalAnalysisFilter,
    TechnicalAnalyzer,
)
from trading_service.repository import TradingRepository
from trading_service.types import CrossSignalType


class TechnicalSignalDetector(SignalDetector):
    """技术分析信号检测器。"""

    name = "technical_signal"
    cron = "0 */5 * * * *"  # 6字段：秒 分 时 日 月 周 = 每5分钟

    def __init__(self, repo: TradingRepository, client: BinanceClient) -> None:
        super().__init__(repo)
        self._picker = SelectionPipeline(
            source=AlphaTokenSource(client=client),
            filters=[
                TechnicalAnalysisFilter(
                    analyzer=TechnicalAnalyzer(),
                    client=client,
                    kline_interval="4h",
                ),
            ],
        )

    async def detect(self) -> list[SignalResult]:
        """扫描候选币种，产出技术分析信号。"""
        infos = await self._picker.pick()
        results: list[SignalResult] = []
        for info in infos:
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
