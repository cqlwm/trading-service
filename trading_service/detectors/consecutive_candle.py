"""连续涨跌K线检测器：检测连续阳线/阴线天数。

对候选币拉取指定 interval 的 K 线，从最后一根往前数连续阳线（close>=open）
或阴线（close<open）的数量。连续天数 >= min_streak 时产出信号。

信号类型：
- consecutive_rise（连续阳线，direction=bullish）
- consecutive_fall（连续阴线，direction=bearish）

severity = min(streak_days, 5)，连续天数越多严重度越高。
"""

from __future__ import annotations

from trading_service.clients.protocols import KlineClient
from trading_service.detectors.base import SignalDetector, SignalResult
from trading_service.pickers import SymbolInfo
from trading_service.pickers.kline_utils import ensure_klines
from trading_service.repository import TradingRepository


class ConsecutiveCandleDetector(SignalDetector):
    """连续涨跌K线检测器。"""

    name = "consecutive_candle"

    def __init__(
        self,
        repo: TradingRepository,
        client: KlineClient | None = None,
        interval: str = "1d",
        limit: int = 30,
        min_streak: int = 3,
    ) -> None:
        super().__init__(repo)
        self._client = client
        self._interval = interval
        self._limit = limit
        self._min_streak = min_streak

    async def detect(self, candidates: list[SymbolInfo]) -> list[SignalResult]:
        """对候选币检测连续涨跌K线。"""
        results: list[SignalResult] = []
        for info in candidates:
            signal = self._detect_one(info)
            if signal is not None:
                results.append(signal)
        return results

    def _detect_one(self, info: SymbolInfo) -> SignalResult | None:
        """检测单个 symbol 的连续涨跌K线。"""
        df = ensure_klines(info, self._interval, self._client, self._limit)
        if df is None or len(df) < self._min_streak:
            return None

        closes = df["close"].to_numpy(dtype=float)
        opens = df["open"].to_numpy(dtype=float)

        # 从最后一根往前数连续阳线或阴线
        last_is_up = float(closes[-1]) >= float(opens[-1])
        streak = 0
        for i in range(len(closes) - 1, -1, -1):
            is_up = float(closes[i]) >= float(opens[i])
            if is_up == last_is_up:
                streak += 1
            else:
                break

        if streak < self._min_streak:
            return None

        start_price = float(opens[-streak])
        end_price = float(closes[-1])
        change_pct = ((end_price - start_price) / start_price) * 100 if start_price > 0 else 0.0

        # 周期标识：最新已收盘 K 线的收盘时间(ms)，用于去重（同一根 K 线期间只发一次）
        kline_close_time = int(df["datetime"].iloc[-1])

        if last_is_up:
            signal_type = "consecutive_rise"
            direction = "bullish"
            description = f"{info.symbol} 连续 {streak} 天上涨"
        else:
            signal_type = "consecutive_fall"
            direction = "bearish"
            description = f"{info.symbol} 连续 {streak} 天下跌"

        return SignalResult(
            symbol=info.symbol,
            signal_type=signal_type,
            direction=direction,
            severity=min(streak, 5),
            description=description,
            metadata={
                "kline_close_time": kline_close_time,
                "streak_days": streak,
                "direction": direction,
                "start_price": start_price,
                "end_price": end_price,
                "change_pct": round(change_pct, 2),
                "interval": self._interval,
            },
        )
