"""突破新高/新低检测器：检测 close 是否突破过去 N 根 K 线的极值。

对候选币拉取指定 interval 的 K 线，取最后一根 close 与过去 window 根的
最高价/最低价比较。突破前高产出 breakout_high，跌破前低产出 breakout_low。

信号类型：
- breakout_high（direction=bullish）
- breakout_low（direction=bearish）

severity 固定 3，突破是中等重要信号。
"""

from __future__ import annotations

from trading_service.clients.protocols import KlineClient
from trading_service.detectors.base import SignalDetector, SignalResult
from trading_service.pickers import SymbolInfo
from trading_service.pickers.kline_utils import ensure_klines
from trading_service.repository import TradingRepository


class BreakoutDetector(SignalDetector):
    """突破新高/新低检测器。"""

    name = "breakout"

    def __init__(
        self,
        repo: TradingRepository,
        client: KlineClient | None = None,
        interval: str = "1d",
        limit: int = 30,
        window: int = 20,
    ) -> None:
        super().__init__(repo)
        self._client = client
        self._interval = interval
        self._limit = limit
        self._window = window

    async def detect(self, candidates: list[SymbolInfo]) -> list[SignalResult]:
        """对候选币检测突破新高/新低。"""
        results: list[SignalResult] = []
        for info in candidates:
            signal = self._detect_one(info)
            if signal is not None:
                results.append(signal)
        return results

    def _detect_one(self, info: SymbolInfo) -> SignalResult | None:
        """检测单个 symbol 的突破新高/新低。"""
        df = ensure_klines(info, self._interval, self._client, self._limit)
        if df is None or len(df) < self._window + 1:
            return None

        highs = df["high"].to_numpy(dtype=float)
        lows = df["low"].to_numpy(dtype=float)
        closes = df["close"].to_numpy(dtype=float)

        current_close = float(closes[-1])
        prev_high = float(highs[-(self._window + 1):-1].max())
        prev_low = float(lows[-(self._window + 1):-1].min())

        # 周期标识：最新已收盘 K 线的收盘时间(ms)，用于去重（同一根 K 线期间只发一次）
        kline_close_time = int(df["datetime"].iloc[-1])

        if current_close >= prev_high:
            return SignalResult(
                symbol=info.symbol,
                signal_type="breakout_high",
                direction="bullish",
                severity=3,
                description=f"{info.symbol} 突破 {self._window} 日新高",
                metadata={
                    "kline_close_time": kline_close_time,
                    "breakout_price": current_close,
                    "prev_high": prev_high,
                    "window": self._window,
                    "interval": self._interval,
                },
            )

        if current_close <= prev_low:
            return SignalResult(
                symbol=info.symbol,
                signal_type="breakout_low",
                direction="bearish",
                severity=3,
                description=f"{info.symbol} 跌破 {self._window} 日新低",
                metadata={
                    "kline_close_time": kline_close_time,
                    "breakout_price": current_close,
                    "prev_low": prev_low,
                    "window": self._window,
                    "interval": self._interval,
                },
            )

        return None
