"""测试 PriceChangeDetector 24h暴涨暴跌检测器。

测试覆盖：
1. 正常路径：24h 涨幅 >= threshold -> price_surge 信号
2. 正常路径：24h 跌幅 <= -threshold -> price_plunge 信号
3. 边界：刚好等于 threshold -> 产出信号（>=）
4. 边界：未达 threshold -> 无信号
5. severity 映射：每 10% 一级，封顶 5
6. 多候选分别检测
7. 空候选列表
"""
from __future__ import annotations

import pytest

from trading_service.detectors.price_change import PriceChangeDetector
from trading_service.pickers import SymbolInfo


def make_info(symbol: str, change_pct: float) -> SymbolInfo:
    """构造带 24h 涨跌幅的 SymbolInfo。"""
    return SymbolInfo(symbol=symbol, price_change_pct_24h=change_pct)


@pytest.fixture
def repo():
    from tests.conftest import InMemoryTradingRepository
    return InMemoryTradingRepository()


@pytest.fixture
def detector(repo):
    """阈值 20% 的检测器。"""
    return PriceChangeDetector(repo=repo, threshold=20.0)


class TestPriceChangeDetectorNormal:
    """正常路径测试。"""

    @pytest.mark.asyncio
    async def test_price_surge(self, detector) -> None:
        """✅ 24h 涨幅 35% -> price_surge 信号。"""
        info = make_info("BTCUSDT", 35.0)

        results = await detector.detect([info])

        assert len(results) == 1
        assert results[0].signal_type == "price_surge"
        assert results[0].direction == "bullish"
        assert results[0].metadata["change_pct"] == 35.0
        assert results[0].metadata["threshold"] == 20.0

    @pytest.mark.asyncio
    async def test_price_plunge(self, detector) -> None:
        """✅ 24h 跌幅 28% -> price_plunge 信号。"""
        info = make_info("ETHUSDT", -28.0)

        results = await detector.detect([info])

        assert len(results) == 1
        assert results[0].signal_type == "price_plunge"
        assert results[0].direction == "bearish"
        assert results[0].metadata["change_pct"] == -28.0


class TestPriceChangeDetectorBoundaries:
    """边界条件测试。"""

    @pytest.mark.asyncio
    async def test_exactly_at_threshold(self, detector) -> None:
        """✅ 涨幅刚好 20%（=threshold）-> 产出信号。"""
        info = make_info("BTCUSDT", 20.0)

        results = await detector.detect([info])

        assert len(results) == 1, "刚好达到阈值应产出信号"

    @pytest.mark.asyncio
    async def test_below_threshold_no_signal(self, detector) -> None:
        """✅ 涨幅仅 15%（< threshold）-> 无信号。"""
        info = make_info("BTCUSDT", 15.0)

        results = await detector.detect([info])

        assert len(results) == 0, "未达阈值不应产出信号"

    @pytest.mark.asyncio
    async def test_small_decline_no_signal(self, detector) -> None:
        """✅ 跌幅仅 10%（< threshold）-> 无信号。"""
        info = make_info("BTCUSDT", -10.0)

        results = await detector.detect([info])

        assert len(results) == 0, "跌幅未达阈值不应产出信号"

    @pytest.mark.asyncio
    async def test_empty_candidates(self, detector) -> None:
        """✅ 空候选列表返回空。"""
        results = await detector.detect([])
        assert results == []


class TestPriceChangeDetectorSeverity:
    """severity 映射测试。"""

    @pytest.mark.asyncio
    async def test_severity_per_10pct(self, detector) -> None:
        """✅ 涨幅 35% -> severity=3（35/10=3）。"""
        info = make_info("BTCUSDT", 35.0)

        results = await detector.detect([info])

        assert results[0].severity == 3, "35% 应映射 severity=3"

    @pytest.mark.asyncio
    async def test_severity_capped_at_5(self, detector) -> None:
        """✅ 涨幅 80% -> severity 封顶 5。"""
        info = make_info("BTCUSDT", 80.0)

        results = await detector.detect([info])

        assert results[0].severity == 5, "severity 应封顶 5"


class TestPriceChangeDetectorMultiple:
    """多候选测试。"""

    @pytest.mark.asyncio
    async def test_multiple_candidates(self, detector) -> None:
        """✅ 多个候选分别检测。"""
        surge = make_info("BTCUSDT", 35.0)
        plunge = make_info("ETHUSDT", -25.0)
        normal = make_info("SOLUSDT", 5.0)

        results = await detector.detect([surge, plunge, normal])

        assert len(results) == 2
        types = {r.signal_type for r in results}
        assert types == {"price_surge", "price_plunge"}
