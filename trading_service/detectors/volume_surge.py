"""成交量放大检测器：检测最近一根 K 线成交量相对历史均值的放大倍数。

对候选币拉取指定 interval 的 K 线，取最后一根的 volume 与过去 window 根的均值比较。
放大倍数 >= surge_ratio 时产出信号，放量视为市场关注度激增。

信号类型：
- volume_surge（direction=bullish）

severity = min(int(surge_ratio), 5)，放大倍数越大严重度越高。
"""

from __future__ import annotations

from trading_service.clients.protocols import KlineClient
from trading_service.detectors.base import SignalDetector, SignalResult
from trading_service.pickers import SymbolInfo
from trading_service.pickers.kline_utils import ensure_klines
from trading_service.repository import TradingRepository


class VolumeSurgeDetector(SignalDetector):
    """成交量放大检测器。"""

    name = "volume_surge"

    def __init__(
        self,
        repo: TradingRepository,
        client: KlineClient | None = None,
        interval: str = "1d",
        limit: int = 30,
        window: int = 20,
        surge_ratio: float = 3.0,
    ) -> None:
        super().__init__(repo)
        self._client = client
        self._interval = interval
        self._limit = limit
        self._window = window
        self._surge_ratio = surge_ratio

    async def detect(self, candidates: list[SymbolInfo]) -> list[SignalResult]:
        """对候选币检测成交量放大。"""
        results: list[SignalResult] = []
        for info in candidates:
            signal = self._detect_one(info)
            if signal is not None:
                results.append(signal)
        return results

    def _detect_one(self, info: SymbolInfo) -> SignalResult | None:
        """检测单个 symbol 的成交量放大。"""
        df = ensure_klines(info, self._interval, self._client, self._limit)
        if df is None or len(df) < self._window + 1:
            return None

        volumes = df["volume"].to_numpy(dtype=float)
        current_volume = float(volumes[-1])
        history_volumes = volumes[-(self._window + 1):-1]
        avg_volume = float(history_volumes.mean())

        if avg_volume <= 0:
            return None

        ratio = current_volume / avg_volume
        if ratio < self._surge_ratio:
            return None

        # 周期标识：最新已收盘 K 线的收盘时间(ms)，用于去重（同一根 K 线期间只发一次）
        kline_close_time = int(df["datetime"].iloc[-1])

        return SignalResult(
            symbol=info.symbol,
            signal_type="volume_surge",
            direction="bullish",
            severity=min(int(ratio), 5),
            description=f"{info.symbol} {self._interval} K线周期, 成交量放大 {ratio:.2f} 倍",
            metadata={
                "kline_close_time": kline_close_time,
                "current_volume": current_volume,
                "avg_volume": round(avg_volume, 2),
                "surge_ratio": round(ratio, 2),
                "window": self._window,
                "interval": self._interval,
            },
        )
