"""测试 VolumeSurgeDetector 成交量放大检测器。

测试覆盖：
1. 正常路径：最近一根量 / 过去 N 根均值 >= surge_ratio -> volume_surge 信号
2. 正常路径：成交量正常（未达倍数）-> 无信号
3. 边界：刚好等于 surge_ratio -> 产出信号
4. 边界：不足 window 根历史 K 线 -> 无信号
5. severity 封顶：放大倍数极高 -> severity 封顶 5
6. 多候选分别检测
7. 空候选列表 / 无 klines 数据
"""
from __future__ import annotations

from typing import Sequence

import pandas as pd
import pytest

from trading_service.detectors.volume_surge import VolumeSurgeDetector
from trading_service.pickers import SymbolInfo


def make_klines_df(
    candles: Sequence[tuple[int | float, int | float]],
    volumes: Sequence[float] | None = None,
) -> pd.DataFrame:
    """构建含 OHLCV 列的 DataFrame。

    candles: [(open, close), ...] 每根 K 线的开盘价和收盘价。
    volumes: 每根 K 线的成交量；None 时默认全部 100.0。
    """
    n = len(candles)
    if volumes is None:
        volumes = [100.0] * n
    return pd.DataFrame({
        "datetime": list(range(n)),
        "open": [c[0] for c in candles],
        "high": [max(c[0], c[1]) for c in candles],
        "low": [min(c[0], c[1]) for c in candles],
        "close": [c[1] for c in candles],
        "volume": list(volumes),
    })


def make_info(
    symbol: str,
    candles: Sequence[tuple[int | float, int | float]],
    volumes: Sequence[float] | None = None,
) -> SymbolInfo:
    """构造带 klines['1d'] DataFrame 的 SymbolInfo。"""
    info = SymbolInfo(symbol=symbol)
    info.klines["1d"] = make_klines_df(candles, volumes)
    return info


@pytest.fixture
def repo():
    from tests.conftest import InMemoryTradingRepository
    return InMemoryTradingRepository()


@pytest.fixture
def detector(repo):
    """无 client 的检测器（测试用预构建的 klines DataFrame）。"""
    return VolumeSurgeDetector(
        repo=repo, client=None, interval="1d", window=5, surge_ratio=3.0,
    )


class TestVolumeSurgeDetectorNormal:
    """正常路径测试。"""

    @pytest.mark.asyncio
    async def test_volume_surge_detected(self, detector) -> None:
        """✅ 最近一根成交量放大 4 倍 -> volume_surge 信号。"""
        # 前 5 根 volume=100，最后一根 volume=400（4 倍）
        candles = [(10, 11)] * 6
        volumes = [100.0, 100.0, 100.0, 100.0, 100.0, 400.0]
        info = make_info("BTCUSDT", candles, volumes)

        results = await detector.detect([info])

        assert len(results) == 1
        assert results[0].signal_type == "volume_surge"
        assert results[0].direction == "bullish"
        assert results[0].metadata["surge_ratio"] == 4.0
        assert results[0].metadata["current_volume"] == 400.0
        assert results[0].metadata["avg_volume"] == 100.0

    @pytest.mark.asyncio
    async def test_normal_volume_no_signal(self, detector) -> None:
        """✅ 成交量正常（仅 1.5 倍 < 3.0）-> 无信号。"""
        candles = [(10, 11)] * 6
        volumes = [100.0, 100.0, 100.0, 100.0, 100.0, 150.0]
        info = make_info("BTCUSDT", candles, volumes)

        results = await detector.detect([info])

        assert len(results) == 0, "未达 surge_ratio 不应产出信号"


class TestVolumeSurgeDetectorBoundaries:
    """边界条件测试。"""

    @pytest.mark.asyncio
    async def test_exactly_at_threshold(self, detector) -> None:
        """✅ 刚好等于 surge_ratio（3 倍）-> 产出信号。"""
        candles = [(10, 11)] * 6
        volumes = [100.0, 100.0, 100.0, 100.0, 100.0, 300.0]
        info = make_info("BTCUSDT", candles, volumes)

        results = await detector.detect([info])

        assert len(results) == 1, "刚好达到阈值应产出信号"
        assert results[0].metadata["surge_ratio"] == 3.0

    @pytest.mark.asyncio
    async def test_insufficient_history_no_signal(self, detector) -> None:
        """✅ 历史不足 window 根（仅 4 根 < window=5）-> 无信号。"""
        candles = [(10, 11)] * 4
        volumes = [100.0, 100.0, 100.0, 400.0]
        info = make_info("BTCUSDT", candles, volumes)

        results = await detector.detect([info])

        assert len(results) == 0, "历史 K 线不足 window 根不应产出信号"

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


class TestVolumeSurgeDetectorSeverity:
    """severity 封顶测试。"""

    @pytest.mark.asyncio
    async def test_severity_capped_at_5(self, detector) -> None:
        """✅ 放大 10 倍 -> severity 封顶 5。"""
        candles = [(10, 11)] * 6
        volumes = [100.0, 100.0, 100.0, 100.0, 100.0, 1000.0]
        info = make_info("BTCUSDT", candles, volumes)

        results = await detector.detect([info])

        assert results[0].severity == 5, "severity 应封顶 5"
        assert results[0].metadata["surge_ratio"] == 10.0


class TestVolumeSurgeDetectorKlineCloseTime:
    """kline_close_time 周期标识测试。"""

    @pytest.mark.asyncio
    async def test_metadata_has_kline_close_time(self, detector) -> None:
        """✅ metadata 应含 kline_close_time，等于最新已收盘 K 线的 datetime。"""
        candles = [(10, 11)] * 6
        volumes = [100.0, 100.0, 100.0, 100.0, 100.0, 400.0]
        info = make_info("BTCUSDT", candles, volumes)

        results = await detector.detect([info])

        assert len(results) == 1
        assert "kline_close_time" in results[0].metadata
        # make_klines_df 的 datetime 列是 range(n)，最后一根 = n-1 = 5
        assert results[0].metadata["kline_close_time"] == 5

    @pytest.mark.asyncio
    async def test_multiple_candidates(self, detector) -> None:
        """✅ 多个候选分别检测。"""
        surge = make_info(
            "BTCUSDT", [(10, 11)] * 6, [100.0, 100.0, 100.0, 100.0, 100.0, 400.0],
        )
        normal = make_info(
            "ETHUSDT", [(10, 11)] * 6, [100.0, 100.0, 100.0, 100.0, 100.0, 120.0],
        )

        results = await detector.detect([surge, normal])

        assert len(results) == 1
        assert results[0].symbol == "BTCUSDT"


class TestVolumeSurgeDetectorDescription:
    """description 严谨性测试：interval 可配置，表述需带 interval。"""

    @pytest.mark.asyncio
    async def test_volume_surge_description_contains_interval(self, repo) -> None:
        """✅ 4h 周期放量信号 description 应含 "4h"。

        interval 可配置（1d/4h/1h/15m），description 需严谨表达放量周期。
        """
        detector = VolumeSurgeDetector(
            repo=repo, client=None, interval="4h", window=5, surge_ratio=3.0,
        )
        # 6 根 K 线，前 5 根 volume=100，最后一根 volume=500（5 倍放量）
        candles = [(10, 11)] * 6
        volumes = [100.0] * 5 + [500.0]
        info = SymbolInfo(symbol="BTCUSDT")
        info.klines["4h"] = make_klines_df(candles, volumes)

        results = await detector.detect([info])

        assert len(results) == 1
        desc = results[0].description
        assert "4h" in desc, f"description 应含 interval '4h'，实际={desc}"
