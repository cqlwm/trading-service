"""信号检测器测试。

验证检测器的信号产出、调度器执行检测器、信号落盘。
"""
from __future__ import annotations

import pytest

from trading_service.detectors.base import SignalDetector, SignalResult
from trading_service.exchange import MockExchange
from trading_service.repository import TradingRepository


class FakeDetector(SignalDetector):
    """可控的测试检测器。"""

    name = "fake_detector"
    cron = "*/1 * * * * *"

    def __init__(self, repo: TradingRepository, signals: list[SignalResult] | None = None) -> None:
        super().__init__(repo)
        self._signals = signals or []
        self.detect_count = 0

    async def detect(self) -> list[SignalResult]:
        self.detect_count += 1
        return list(self._signals)


class FailingDetector(SignalDetector):
    """总是抛异常的检测器。"""

    name = "failing_detector"
    cron = "*/1 * * * * *"

    async def detect(self) -> list[SignalResult]:
        raise RuntimeError("检测器故意失败")


@pytest.fixture
def exchange() -> MockExchange:
    from tests.conftest import InMemoryTradingRepository
    return MockExchange(InMemoryTradingRepository())


class TestSignalDetectorBase:
    """测试信号检测器基类。"""

    def test_detector_status(self, exchange: MockExchange) -> None:
        """get_status 应返回检测器名称和 cron。"""
        detector = FakeDetector(exchange.db)
        status = detector.get_status()
        assert status["name"] == "fake_detector"
        assert status["cron"] == "*/1 * * * * *"

    @pytest.mark.asyncio
    async def test_detect_returns_results(self, exchange: MockExchange) -> None:
        """detect 应返回 SignalResult 列表。"""
        signals = [
            SignalResult(symbol="BTCUSDT", signal_type="golden_cross", direction="bullish", severity=3),
            SignalResult(symbol="ETHUSDT", signal_type="dead_cross", direction="bearish", severity=3),
        ]
        detector = FakeDetector(exchange.db, signals)
        results = await detector.detect()
        assert len(results) == 2
        assert results[0].symbol == "BTCUSDT"
        assert results[0].signal_type == "golden_cross"

    @pytest.mark.asyncio
    async def test_detect_empty_results(self, exchange: MockExchange) -> None:
        """无信号时 detect 返回空列表。"""
        detector = FakeDetector(exchange.db)
        results = await detector.detect()
        assert len(results) == 0


class TestSchedulerDetectorExecution:
    """测试调度器执行检测器。"""

    @pytest.mark.asyncio
    async def test_detector_execution_writes_signals(self, exchange: MockExchange) -> None:
        """调度器执行检测器后，信号应落盘到 trading_signals。"""
        from trading_service.scheduler import StrategyScheduler

        signals = [
            SignalResult(symbol="BTCUSDT", signal_type="golden_cross", direction="bullish", severity=3,
                         description="BTC 金叉", metadata={"sma_200": 50000}),
        ]
        detector = FakeDetector(exchange.db, signals)
        scheduler = StrategyScheduler(repo=exchange.db, strategies=[], detectors=[detector])

        await scheduler._execute_detector("fake_detector")

        saved = exchange.db.list_signals(limit=10)
        assert len(saved) == 1, "应有 1 条信号落盘"
        assert saved[0].symbol == "BTCUSDT"
        assert saved[0].signal_type == "golden_cross"
        assert saved[0].direction == "bullish"
        assert saved[0].severity == 3
        assert saved[0].description == "BTC 金叉"

    @pytest.mark.asyncio
    async def test_detector_failure_does_not_crash(self, exchange: MockExchange) -> None:
        """检测器异常不应崩溃。"""
        from trading_service.scheduler import StrategyScheduler

        detector = FailingDetector(exchange.db)
        scheduler = StrategyScheduler(repo=exchange.db, strategies=[], detectors=[detector])

        # 不应抛异常
        await scheduler._execute_detector("failing_detector")

        # 不应有信号落盘
        saved = exchange.db.list_signals(limit=10)
        assert len(saved) == 0

    @pytest.mark.asyncio
    async def test_execute_detector_manually(self, exchange: MockExchange) -> None:
        """手动执行检测器返回信号数量。"""
        from trading_service.scheduler import StrategyScheduler

        signals = [
            SignalResult(symbol="BTCUSDT", signal_type="golden_cross", direction="bullish"),
            SignalResult(symbol="ETHUSDT", signal_type="golden_cross", direction="bullish"),
        ]
        detector = FakeDetector(exchange.db, signals)
        scheduler = StrategyScheduler(repo=exchange.db, strategies=[], detectors=[detector])

        count = await scheduler.execute_detector_manually("fake_detector")
        assert count == 2, "应返回 2 条信号"
        saved = exchange.db.list_signals(limit=10)
        assert len(saved) == 2

    @pytest.mark.asyncio
    async def test_detector_start_stop(self, exchange: MockExchange) -> None:
        """检测器 start/stop 应持久化调度状态。"""
        from trading_service.scheduler import StrategyScheduler

        detector = FakeDetector(exchange.db)
        scheduler = StrategyScheduler(repo=exchange.db, strategies=[], detectors=[detector])
        await scheduler.start()
        try:
            success = scheduler.start_detector("fake_detector")
            assert success is True

            schedule = scheduler.get_detector_schedule("fake_detector")
            assert schedule is not None
            assert schedule["running"] is True
            assert schedule["cron"] == "*/1 * * * * *"
            assert schedule["next_run_at"] is not None

            scheduler.stop_detector("fake_detector")
            schedule = scheduler.get_detector_schedule("fake_detector")
            assert schedule is not None
            assert schedule["running"] is False
        finally:
            await scheduler.shutdown()

    @pytest.mark.asyncio
    async def test_list_all_detectors(self, exchange: MockExchange) -> None:
        """list_all_detectors 应返回所有检测器状态。"""
        from trading_service.scheduler import StrategyScheduler

        d1 = FakeDetector(exchange.db)
        d2 = FailingDetector(exchange.db)
        scheduler = StrategyScheduler(repo=exchange.db, strategies=[], detectors=[d1, d2])
        await scheduler.start()
        try:
            detectors = scheduler.list_all_detectors()
            assert len(detectors) == 2
            names = {d["detector_name"] for d in detectors}
            assert names == {"fake_detector", "failing_detector"}
        finally:
            await scheduler.shutdown()

    @pytest.mark.asyncio
    async def test_start_nonexistent_detector_returns_false(self, exchange: MockExchange) -> None:
        """启动不存在的检测器应返回 False。"""
        from trading_service.scheduler import StrategyScheduler

        scheduler = StrategyScheduler(repo=exchange.db, strategies=[], detectors=[])
        assert scheduler.start_detector("nonexistent") is False
