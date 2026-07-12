"""测试 ConsecutiveCandleDetector 连续涨跌K线检测器。

测试覆盖：
1. 正常路径：3 连阳 -> consecutive_rise 信号
2. 正常路径：3 连阴 -> consecutive_fall 信号
3. 边界：仅 2 连阳（< min_streak）-> 无信号
4. 边界：涨跌交替 -> 无信号
5. 纯增强不丢弃：检测器不修改 candidates
6. severity 封顶：5+ 连阳 -> severity=5
"""
from __future__ import annotations

import pandas as pd
import pytest

from trading_service.detectors.consecutive_candle import ConsecutiveCandleDetector
from trading_service.pickers import SymbolInfo


from typing import Sequence
def make_klines_df(candles: Sequence[tuple[int | float, int | float]]) -> pd.DataFrame:
    """构建含 OHLCV 列的 DataFrame。

    candles: [(open, close), ...] 每根 K 线的开盘价和收盘价。
    """
    n = len(candles)
    return pd.DataFrame({
        "datetime": list(range(n)),
        "open": [c[0] for c in candles],
        "high": [max(c[0], c[1]) for c in candles],
        "low": [min(c[0], c[1]) for c in candles],
        "close": [c[1] for c in candles],
        "volume": [100.0] * n,
    })


def make_info(symbol: str, candles: Sequence[tuple[int | float, int | float]]) -> SymbolInfo:
    """构造带 klines['1d'] DataFrame 的 SymbolInfo。"""
    info = SymbolInfo(symbol=symbol)
    info.klines["1d"] = make_klines_df(candles)
    return info


@pytest.fixture
def repo():
    from tests.conftest import InMemoryTradingRepository
    return InMemoryTradingRepository()


@pytest.fixture
def detector(repo):
    """无 client 的检测器（测试用预构建的 klines DataFrame）。"""
    return ConsecutiveCandleDetector(repo=repo, client=None, interval="1d", min_streak=3)


class TestConsecutiveCandleDetectorNormal:
    """正常路径测试。"""

    @pytest.mark.asyncio
    async def test_consecutive_rise(self, detector) -> None:
        """✅ 3 连阳 -> consecutive_rise 信号。"""
        # (open, close): 3 根阳线（close >= open）
        candles = [(10, 11), (11, 12), (12, 13)]
        info = make_info("BTCUSDT", candles)

        results = await detector.detect([info])

        assert len(results) == 1
        assert results[0].signal_type == "consecutive_rise"
        assert results[0].direction == "bullish"
        assert results[0].severity == 3
        assert results[0].metadata["streak_days"] == 3

    @pytest.mark.asyncio
    async def test_consecutive_fall(self, detector) -> None:
        """✅ 3 连阴 -> consecutive_fall 信号。"""
        # (open, close): 3 根阴线（close < open）
        candles = [(13, 12), (12, 11), (11, 10)]
        info = make_info("ETHUSDT", candles)

        results = await detector.detect([info])

        assert len(results) == 1
        assert results[0].signal_type == "consecutive_fall"
        assert results[0].direction == "bearish"
        assert results[0].severity == 3
        assert results[0].metadata["streak_days"] == 3

    @pytest.mark.asyncio
    async def test_change_pct_calculated(self, detector) -> None:
        """✅ metadata 中 change_pct 正确计算。"""
        candles = [(10, 11), (11, 12), (12, 15)]  # 10 -> 15 = +50%
        info = make_info("SOLUSDT", candles)

        results = await detector.detect([info])

        assert results[0].metadata["change_pct"] == 50.0
        assert results[0].metadata["start_price"] == 10.0
        assert results[0].metadata["end_price"] == 15.0


class TestConsecutiveCandleDetectorBoundaries:
    """边界条件测试。"""

    @pytest.mark.asyncio
    async def test_below_min_streak_no_signal(self, detector) -> None:
        """✅ 仅 2 连阳（< min_streak=3）-> 无信号。"""
        candles = [(10, 11), (11, 12)]  # 只有 2 根
        info = make_info("BTCUSDT", candles)

        results = await detector.detect([info])

        assert len(results) == 0, "不足 min_streak 不应产出信号"

    @pytest.mark.asyncio
    async def test_alternating_no_signal(self, detector) -> None:
        """✅ 涨跌交替 -> 无连续 -> 无信号。"""
        candles = [(10, 11), (11, 10), (10, 11), (11, 10)]
        info = make_info("BTCUSDT", candles)

        results = await detector.detect([info])

        assert len(results) == 0, "涨跌交替不应产出信号"

    @pytest.mark.asyncio
    async def test_streak_after_break_not_counted(self, detector) -> None:
        """✅ 断裂后的连续只数最后一轮。"""
        # 阳-阳-阴-阳-阳-阳：最后一轮 3 连阳
        candles = [(10, 11), (11, 12), (12, 11), (11, 12), (12, 13), (13, 14)]
        info = make_info("BTCUSDT", candles)

        results = await detector.detect([info])

        assert len(results) == 1
        assert results[0].metadata["streak_days"] == 3, "只数最后一轮 3 连阳"

    @pytest.mark.asyncio
    async def test_empty_candidates(self, detector) -> None:
        """✅ 空候选列表返回空。"""
        results = await detector.detect([])
        assert results == []

    @pytest.mark.asyncio
    async def test_no_klines_no_signal(self, detector) -> None:
        """✅ 无 klines 数据的候选不产出信号。"""
        info = SymbolInfo(symbol="BTCUSDT")  # klines={}

        results = await detector.detect([info])

        assert len(results) == 0


class TestConsecutiveCandleDetectorSeverity:
    """severity 封顶测试。"""

    @pytest.mark.asyncio
    async def test_severity_capped_at_5(self, detector) -> None:
        """✅ 7 连阳 -> severity 封顶 5。"""
        candles = [(10, 11), (11, 12), (12, 13), (13, 14), (14, 15), (15, 16), (16, 17)]
        info = make_info("BTCUSDT", candles)

        results = await detector.detect([info])

        assert len(results) == 1
        assert results[0].severity == 5, "severity 应封顶 5"
        assert results[0].metadata["streak_days"] == 7, "实际连续 7 天"


class TestConsecutiveCandleDetectorMultiple:
    """多候选测试。"""

    @pytest.mark.asyncio
    async def test_multiple_candidates(self, detector) -> None:
        """✅ 多个候选分别检测。"""
        rise = make_info("BTCUSDT", [(10, 11), (11, 12), (12, 13)])
        fall = make_info("ETHUSDT", [(13, 12), (12, 11), (11, 10)])
        none = make_info("SOLUSDT", [(10, 11), (11, 10), (10, 11)])

        results = await detector.detect([rise, fall, none])

        assert len(results) == 2
        types = {r.signal_type for r in results}
        assert types == {"consecutive_rise", "consecutive_fall"}
