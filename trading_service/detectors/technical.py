"""技术分析信号检测器。

接收策略选好的候选币（已含技术分析字段），产出金叉/死叉/横盘信号。
不再自己组装 SelectionPipeline，由策略传入候选币。

优先从 DataFrame 读取指标，回退到旧字段。
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

        候选币应已由 TechnicalAnalysisFilter 构建 klines DataFrame。
        优先读 DataFrame，回退到旧字段。
        """
        results: list[SignalResult] = []
        for info in candidates:
            cross, price_vs_sma, sma_200, is_sideways, volatility = self._read_indicators(info)

            if cross == CrossSignalType.GOLDEN.value:
                results.append(SignalResult(
                    symbol=info.symbol,
                    signal_type="golden_cross",
                    direction="bullish",
                    severity=3,
                    description=f"{info.symbol} 金叉向上穿越 SMA200",
                    metadata={
                        "cross_signal": cross,
                        "price_vs_sma200": price_vs_sma,
                        "sma_200": sma_200,
                    },
                ))
            elif cross == CrossSignalType.DEAD.value:
                results.append(SignalResult(
                    symbol=info.symbol,
                    signal_type="dead_cross",
                    direction="bearish",
                    severity=3,
                    description=f"{info.symbol} 死叉向下穿越 SMA200",
                    metadata={
                        "cross_signal": cross,
                        "price_vs_sma200": price_vs_sma,
                        "sma_200": sma_200,
                    },
                ))
            if is_sideways:
                results.append(SignalResult(
                    symbol=info.symbol,
                    signal_type="sideways_bottom",
                    direction="neutral",
                    severity=2,
                    description=f"{info.symbol} 底部横盘",
                    metadata={"volatility_10": volatility},
                ))
        return results

    @staticmethod
    def _read_indicators(
        info: SymbolInfo,
    ) -> tuple[str | None, float | None, float | None, bool, float | None]:
        """从 DataFrame 或旧字段读取指标值。

        返回 (cross_signal, price_vs_sma200_percent, sma_200, is_sideways_bottom, volatility_10)
        """
        cross: str | None = None
        price_vs_sma: float | None = None
        sma_200: float | None = None
        is_sideways: bool = False
        volatility: float | None = None

        # 优先读 DataFrame
        if info.klines is not None and len(info.klines) > 0:
            latest = info.klines.iloc[-1]
            cross_val = latest.get("cross_signal")
            cross = cross_val if isinstance(cross_val, str) else None
            price_val = latest.get("price_vs_sma200_percent")
            price_vs_sma = float(price_val) if price_val is not None and not (isinstance(price_val, float) and price_val != price_val) else None  # NaN check
            sma_val = latest.get("sma_200")
            sma_200 = float(sma_val) if sma_val is not None and not (isinstance(sma_val, float) and sma_val != sma_val) else None
            sideways_val = latest.get("is_sideways_bottom")
            is_sideways = bool(sideways_val) if sideways_val is not None else False
            vol_val = latest.get("volatility_10")
            volatility = float(vol_val) if vol_val is not None and not (isinstance(vol_val, float) and vol_val != vol_val) else None

        # 回退到旧字段
        if cross is None and info.cross_signal is not None:
            cross = info.cross_signal.value
        if price_vs_sma is None:
            price_vs_sma = info.price_vs_sma200_percent
        if sma_200 is None:
            sma_200 = info.sma_200
        if not is_sideways:
            is_sideways = info.is_sideways_bottom
        if volatility is None:
            volatility = info.volatility_10

        return cross, price_vs_sma, sma_200, is_sideways, volatility
