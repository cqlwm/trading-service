"""技术分析信号检测器。

接收策略选好的候选币（已含 klines DataFrame），产出金叉/死叉/横盘信号。
不再自己组装 SelectionPipeline，由策略传入候选币。

从 klines["4h"] 最后一行读取指标。若 4h 数据缺失且注入了 client，则 lazy-fetch 并缓存。
"""

from __future__ import annotations

from trading_service.clients.protocols import KlineClient
from trading_service.detectors.base import SignalDetector, SignalResult
from trading_service.pickers import SymbolInfo
from trading_service.pickers.kline_utils import ensure_klines
from trading_service.repository import TradingRepository
from trading_service.types import CrossSignalType

# 检测器默认读取的时间框架
_DEFAULT_INTERVAL = "4h"


class TechnicalSignalDetector(SignalDetector):
    """技术分析信号检测器。"""

    name = "technical_signal"

    def __init__(self, repo: TradingRepository, client: KlineClient | None = None) -> None:
        super().__init__(repo)
        self._client = client

    async def detect(self, candidates: list[SymbolInfo]) -> list[SignalResult]:
        """对候选币进行技术分析信号检测。

        候选币应已由 TechnicalAnalysisFilter 构建 klines["4h"] DataFrame。
        若 4h 数据缺失且注入了 client，则 lazy-fetch 并缓存。
        从 DataFrame 最后一行读取指标。
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

    def _read_indicators(
        self, info: SymbolInfo,
    ) -> tuple[str | None, float | None, float | None, bool, float | None]:
        """从 klines["4h"] 最后一行读取指标值。

        若 4h 数据缺失且注入了 client，则 lazy-fetch 并缓存。
        返回 (cross_signal, price_vs_sma200_percent, sma_200, is_sideways_bottom, volatility_10)
        """
        df = ensure_klines(info, _DEFAULT_INTERVAL, self._client)
        if df is None or len(df) == 0:
            return None, None, None, False, None

        latest = df.iloc[-1]

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

        return cross, price_vs_sma, sma_200, is_sideways, volatility
