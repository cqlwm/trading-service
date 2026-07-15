"""测试 BreakoutDetector 突破新高/新低检测器。

测试覆盖：
1. 正常路径：close 突破过去 N 根 high -> breakout_high 信号
2. 正常路径：close 跌破过去 N 根 low -> breakout_low 信号
3. 边界：close 刚好等于前高 -> 产出信号（>=）
4. 边界：close 未触及前高 -> 无信号
5. 边界：历史不足 window 根 -> 无信号
6. 多候选分别检测
7. 空候选列表 / 无 klines 数据
"""
from __future__ import annotations

from typing import Sequence

import pandas as pd
import pytest

from trading_service.detectors.breakout import BreakoutDetector
from trading_service.pickers import SymbolInfo


def make_klines_df(
    highs: Sequence[int | float],
    lows: Sequence[int | float],
    closes: Sequence[int | float],
) -> pd.DataFrame:
    """构建含 OHLCV 列的 DataFrame，只关心 high/low/close。

    highs/lows/closes: 各根 K 线的最高价/最低价/收盘价。
    open 取 close 前一根（首根取自身），volume 固定 100。
    """
    n = len(closes)
    opens = [closes[i - 1] if i > 0 else closes[0] for i in range(n)]
    return pd.DataFrame({
        "datetime": list(range(n)),
        "open": opens,
        "high": list(highs),
        "low": list(lows),
        "close": list(closes),
        "volume": [100.0] * n,
    })


def make_info(
    symbol: str,
    highs: Sequence[int | float],
    lows: Sequence[int | float],
    closes: Sequence[int | float],
) -> SymbolInfo:
    """构造带 klines['1d'] DataFrame 的 SymbolInfo。"""
    info = SymbolInfo(symbol=symbol)
    info.klines["1d"] = make_klines_df(highs, lows, closes)
    return info


@pytest.fixture
def repo():
    from tests.conftest import InMemoryTradingRepository
    return InMemoryTradingRepository()


@pytest.fixture
def detector(repo):
    """无 client 的检测器（测试用预构建的 klines DataFrame）。"""
    return BreakoutDetector(repo=repo, client=None, interval="1d", window=5)


class TestBreakoutDetectorNormal:
    """正常路径测试。"""

    @pytest.mark.asyncio
    async def test_breakout_high(self, detector) -> None:
        """✅ close 突破过去 5 根 high -> breakout_high 信号。"""
        # 前 5 根 high 依次 10-14，最后一根 close=20 突破前高 14
        highs = [10.0, 11.0, 12.0, 13.0, 14.0, 14.0]
        lows = [9.0, 10.0, 11.0, 12.0, 13.0, 13.0]
        closes = [10.0, 11.0, 12.0, 13.0, 14.0, 20.0]
        info = make_info("BTCUSDT", highs, lows, closes)

        results = await detector.detect([info])

        assert len(results) == 1
        assert results[0].signal_type == "breakout_high"
        assert results[0].direction == "bullish"
        assert results[0].metadata["breakout_price"] == 20.0
        assert results[0].metadata["prev_high"] == 14.0

    @pytest.mark.asyncio
    async def test_breakout_low(self, detector) -> None:
        """✅ close 跌破过去 5 根 low -> breakout_low 信号。"""
        # 前 5 根 low 依次 11-15，最后一根 close=5 跌破前低 11
        highs = [12.0, 13.0, 14.0, 15.0, 16.0, 16.0]
        lows = [11.0, 12.0, 13.0, 14.0, 15.0, 11.0]
        closes = [12.0, 13.0, 14.0, 15.0, 16.0, 5.0]
        info = make_info("ETHUSDT", highs, lows, closes)

        results = await detector.detect([info])

        assert len(results) == 1
        assert results[0].signal_type == "breakout_low"
        assert results[0].direction == "bearish"
        assert results[0].metadata["breakout_price"] == 5.0
        assert results[0].metadata["prev_low"] == 11.0


class TestBreakoutDetectorBoundaries:
    """边界条件测试。"""

    @pytest.mark.asyncio
    async def test_exactly_at_prev_high(self, detector) -> None:
        """✅ close 刚好等于前高（>=）-> 产出信号。"""
        highs = [10.0, 11.0, 12.0, 13.0, 14.0, 14.0]
        lows = [9.0] * 6
        closes = [10.0, 11.0, 12.0, 13.0, 14.0, 14.0]
        info = make_info("BTCUSDT", highs, lows, closes)

        results = await detector.detect([info])

        assert len(results) == 1, "close 等于前高应视为突破（>=）"

    @pytest.mark.asyncio
    async def test_below_prev_high_no_signal(self, detector) -> None:
        """✅ close 未触及前高 -> 无信号。"""
        highs = [10.0, 11.0, 12.0, 13.0, 14.0, 14.0]
        lows = [9.0] * 6
        closes = [10.0, 11.0, 12.0, 13.0, 14.0, 13.5]
        info = make_info("BTCUSDT", highs, lows, closes)

        results = await detector.detect([info])

        assert len(results) == 0, "close 未突破前高不应产出信号"

    @pytest.mark.asyncio
    async def test_insufficient_history_no_signal(self, detector) -> None:
        """✅ 历史不足 window 根（仅 4 根 < window=5）-> 无信号。"""
        highs = [10.0, 11.0, 12.0, 13.0]
        lows = [9.0, 10.0, 11.0, 12.0]
        closes = [10.0, 11.0, 12.0, 20.0]
        info = make_info("BTCUSDT", highs, lows, closes)

        results = await detector.detect([info])

        assert len(results) == 0, "历史不足不应产出信号"

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


class TestBreakoutDetectorMultiple:
    """多候选测试。"""

    @pytest.mark.asyncio
    async def test_multiple_candidates(self, detector) -> None:
        """✅ 多个候选分别检测。"""
        # BTC 突破新高
        btc = make_info(
            "BTCUSDT",
            [10.0, 11.0, 12.0, 13.0, 14.0, 14.0],
            [9.0, 10.0, 11.0, 12.0, 13.0, 13.0],
            [10.0, 11.0, 12.0, 13.0, 14.0, 20.0],
        )
        # ETH 无突破
        eth = make_info(
            "ETHUSDT",
            [10.0, 11.0, 12.0, 13.0, 14.0, 14.0],
            [9.0, 10.0, 11.0, 12.0, 13.0, 13.0],
            [10.0, 11.0, 12.0, 13.0, 14.0, 13.5],
        )

        results = await detector.detect([btc, eth])

        assert len(results) == 1
        assert results[0].symbol == "BTCUSDT"
