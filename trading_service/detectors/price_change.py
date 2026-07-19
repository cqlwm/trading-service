"""24h 暴涨暴跌检测器：基于 SymbolInfo 现成的 24h 涨跌幅字段。

直接读取 SymbolInfo.price_change_pct_24h，无需拉取 K 线，是最轻量的检测器。
涨幅 >= threshold 产出 price_surge，跌幅 <= -threshold 产出 price_plunge。

信号类型：
- price_surge（direction=bullish）
- price_plunge（direction=bearish）

severity = min(int(abs(change) / 10), 5)，每 10% 一级。
"""

from __future__ import annotations

from datetime import datetime, timezone

from trading_service.detectors.base import SignalDetector, SignalResult
from trading_service.pickers import SymbolInfo
from trading_service.repository import TradingRepository


class PriceChangeDetector(SignalDetector):
    """24h 暴涨暴跌检测器。"""

    name = "price_change"

    def __init__(
        self,
        repo: TradingRepository,
        threshold: float = 20.0,
    ) -> None:
        super().__init__(repo)
        self._threshold = threshold

    async def detect(self, candidates: list[SymbolInfo]) -> list[SignalResult]:
        """对候选币检测 24h 暴涨暴跌。"""
        results: list[SignalResult] = []
        for info in candidates:
            signal = self._detect_one(info)
            if signal is not None:
                results.append(signal)
        return results

    def _detect_one(self, info: SymbolInfo) -> SignalResult | None:
        """检测单个 symbol 的 24h 暴涨暴跌。"""
        change_pct = info.price_change_pct_24h
        if abs(change_pct) < self._threshold:
            return None

        # 周期标识：无 K 线数据，用当天 UTC 0 点时间戳(ms)作伪标识
        # 效果：同一天内多次执行标识相同，跨 UTC 日才变（与 1d K 线语义接近）
        kline_close_time = int(
            datetime.now(timezone.utc)
            .replace(hour=0, minute=0, second=0, microsecond=0)
            .timestamp() * 1000
        )

        if change_pct >= self._threshold:
            return SignalResult(
                symbol=info.symbol,
                signal_type="price_surge",
                direction="bullish",
                severity=min(int(change_pct / 10), 5),
                description=f"{info.symbol} 24h 暴涨 {change_pct:.1f}%",
                metadata={
                    "interval": "ticker",
                    "kline_close_time": kline_close_time,
                    "change_pct": change_pct,
                    "threshold": self._threshold,
                },
            )

        return SignalResult(
            symbol=info.symbol,
            signal_type="price_plunge",
            direction="bearish",
            severity=min(int(abs(change_pct) / 10), 5),
            description=f"{info.symbol} 24h 暴跌 {change_pct:.1f}%",
            metadata={
                "interval": "ticker",
                "kline_close_time": kline_close_time,
                "change_pct": change_pct,
                "threshold": self._threshold,
            },
        )
