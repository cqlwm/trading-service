"""策略调度器测试。"""
from __future__ import annotations

from typing import Any

import pytest

from trading_service.scheduler import StrategyScheduler
from trading_service.strategies.base import Strategy, StrategyAction, StrategyConfig
from trading_service.pickers import ISymbolPicker
from trading_service.exchange import MockExchange
from trading_service.types import TradeDirection


class FakePicker(ISymbolPicker):
    """空选币器，测试用。"""
    async def pick(self) -> list[Any]:
        return []


class FakeStrategy(Strategy):
    """可控的测试策略，可配置执行动作或抛异常。"""

    name = "fake"
    cron = "*/1 * * * * *"  # 6字段：秒 分 时 日 月 周 = 每秒（测试用）

    def __init__(self, exchange: MockExchange, should_fail: bool = False) -> None:
        super().__init__(exchange, StrategyConfig(), FakePicker())
        self._should_fail = should_fail
        self.execute_count = 0

    async def execute(self, execution_id: str = "") -> list[StrategyAction]:
        self.execute_count += 1
        if self._should_fail:
            raise RuntimeError("测试故意失败")
        # 通过 exchange 实际开仓，产生动作记录
        self.exchange.open_position(
            symbol="BTCUSDT",
            direction=TradeDirection.LONG,
            size=100.0,
            price=50000.0,
            tag="fake",
            reason_text="测试开仓",
            execution_id=execution_id,
        )
        return [StrategyAction(type="open", symbol="BTCUSDT", reason="测试开仓")]

    def get_status(self) -> dict[str, Any]:
        return {"strategy": "fake", "execute_count": self.execute_count}


class FailingStrategy(Strategy):
    """总是抛异常的策略，测试异常不崩溃。"""

    name = "failing"
    cron = "*/1 * * * * *"  # 6字段

    def __init__(self, exchange: MockExchange) -> None:
        super().__init__(exchange, StrategyConfig(), FakePicker())

    async def execute(self, execution_id: str = "") -> list[StrategyAction]:
        raise RuntimeError("策略执行故意失败")

    def get_status(self) -> dict[str, Any]:
        return {"strategy": "failing"}


@pytest.fixture
def scheduler(exchange: MockExchange) -> StrategyScheduler:
    """创建带 FakeStrategy 的调度器。"""
    strategy = FakeStrategy(exchange)
    repo = exchange.db  # type: ignore[attr-defined]
    return StrategyScheduler(repo=repo, strategies=[strategy])


@pytest.fixture
def failing_scheduler(exchange: MockExchange) -> StrategyScheduler:
    """创建带 FailingStrategy 的调度器，测试异常场景。"""
    strategy = FailingStrategy(exchange)
    repo = exchange.db  # type: ignore[attr-defined]
    return StrategyScheduler(repo=repo, strategies=[strategy])


class TestSchedulerStartStop:
    """测试启动/停止调度。"""

    @pytest.mark.asyncio
    async def test_start_strategy_enables_schedule(self, scheduler: StrategyScheduler) -> None:
        """启动策略后，调度状态应为 enabled。"""
        await scheduler.start()
        try:
            success = scheduler.start_strategy("fake")
            assert success, "启动策略应返回 True"

            schedule = scheduler.get_strategy_schedule("fake")
            assert schedule is not None
            assert schedule["running"] is True
            assert schedule["cron"] == "*/1 * * * * *"
            assert schedule["next_run_at"] is not None, "应有下次执行时间"
        finally:
            await scheduler.shutdown()

    @pytest.mark.asyncio
    async def test_stop_strategy_disables_schedule(self, scheduler: StrategyScheduler) -> None:
        """停止策略后，调度状态应为 disabled。"""
        await scheduler.start()
        try:
            scheduler.start_strategy("fake")
            success = scheduler.stop_strategy("fake")
            assert success, "停止策略应返回 True"

            schedule = scheduler.get_strategy_schedule("fake")
            assert schedule is not None
            assert schedule["running"] is False
            assert schedule["next_run_at"] is None, "停止后不应有下次执行时间"
        finally:
            await scheduler.shutdown()

    @pytest.mark.asyncio
    async def test_start_nonexistent_strategy_returns_false(self, scheduler: StrategyScheduler) -> None:
        """启动不存在的策略应返回 False。"""
        await scheduler.start()
        try:
            success = scheduler.start_strategy("nonexistent")
            assert success is False
        finally:
            await scheduler.shutdown()


class TestSchedulerPersistRestore:
    """测试调度状态持久化与恢复。"""

    @pytest.mark.asyncio
    async def test_enabled_strategy_restored_on_restart(self, exchange: MockExchange) -> None:
        """服务重启后，之前 enabled 的策略应自动恢复。"""
        repo = exchange.db  # type: ignore[attr-defined]

        # 第一轮：启动调度器，启动策略，然后关闭
        scheduler1 = StrategyScheduler(repo=repo, strategies=[FakeStrategy(exchange)])
        await scheduler1.start()
        scheduler1.start_strategy("fake")
        schedule1 = scheduler1.get_strategy_schedule("fake")
        assert schedule1 is not None
        assert schedule1["running"] is True
        await scheduler1.shutdown()

        # 第二轮：新建调度器（模拟重启），应自动恢复 fake 策略
        scheduler2 = StrategyScheduler(repo=repo, strategies=[FakeStrategy(exchange)])
        await scheduler2.start()
        try:
            schedule2 = scheduler2.get_strategy_schedule("fake")
            assert schedule2 is not None
            assert schedule2["running"] is True, "重启后策略应自动恢复为运行状态"
            assert schedule2["next_run_at"] is not None
        finally:
            await scheduler2.shutdown()

    @pytest.mark.asyncio
    async def test_disabled_strategy_not_restored(self, exchange: MockExchange) -> None:
        """停止的策略重启后不应恢复。"""
        repo = exchange.db  # type: ignore[attr-defined]

        scheduler1 = StrategyScheduler(repo=repo, strategies=[FakeStrategy(exchange)])
        await scheduler1.start()
        scheduler1.start_strategy("fake")
        scheduler1.stop_strategy("fake")
        await scheduler1.shutdown()

        scheduler2 = StrategyScheduler(repo=repo, strategies=[FakeStrategy(exchange)])
        await scheduler2.start()
        try:
            schedule = scheduler2.get_strategy_schedule("fake")
            assert schedule is not None
            assert schedule["running"] is False, "停止的策略重启后不应恢复"
        finally:
            await scheduler2.shutdown()


class TestSchedulerExecutionRecord:
    """测试执行记录写入。"""

    @pytest.mark.asyncio
    async def test_successful_execution_writes_record(self, scheduler: StrategyScheduler) -> None:
        """成功执行后应写入执行记录。"""
        await scheduler.start()
        try:
            # 手动触发一次执行
            await scheduler._execute_strategy("fake")

            executions = scheduler.list_executions("fake")
            assert len(executions) == 1, "应有 1 条执行记录"
            record = executions[0]
            assert record.success is True
            assert record.action_count == 1
            assert record.finished_at is not None
            assert record.error is None
        finally:
            await scheduler.shutdown()

    @pytest.mark.asyncio
    async def test_execution_id_links_to_action_records(self, scheduler: StrategyScheduler) -> None:
        """执行记录的 id 应该与动作记录的 execution_id 关联。"""
        await scheduler.start()
        try:
            await scheduler._execute_strategy("fake")

            executions = scheduler.list_executions("fake")
            assert len(executions) == 1
            execution_id = executions[0].id

            actions = scheduler.list_actions_by_execution(execution_id)
            assert len(actions) == 1, "应有 1 条动作记录"
            assert actions[0].execution_id == execution_id
            assert actions[0].symbol == "BTCUSDT"
            assert actions[0].action_type == "open"
        finally:
            await scheduler.shutdown()

    @pytest.mark.asyncio
    async def test_failed_execution_writes_record_with_error(
        self, failing_scheduler: StrategyScheduler
    ) -> None:
        """执行失败也应写入记录，包含错误信息。"""
        await failing_scheduler.start()
        try:
            # 手动触发执行，应不崩溃
            await failing_scheduler._execute_strategy("failing")

            executions = failing_scheduler.list_executions("failing")
            assert len(executions) == 1, "失败的执行也应有记录"
            record = executions[0]
            assert record.success is False
            assert record.action_count == 0
            assert record.error is not None
            assert "故意失败" in record.error
        finally:
            await failing_scheduler.shutdown()

    @pytest.mark.asyncio
    async def test_last_run_at_updated_after_execution(self, scheduler: StrategyScheduler) -> None:
        """执行后 last_run_at 应更新。"""
        await scheduler.start()
        try:
            schedule_before = scheduler.get_strategy_schedule("fake")
            assert schedule_before is not None
            assert schedule_before["last_run_at"] is None, "执行前 last_run_at 应为 None"

            await scheduler._execute_strategy("fake")

            schedule_after = scheduler.get_strategy_schedule("fake")
            assert schedule_after is not None
            assert schedule_after["last_run_at"] is not None, "执行后 last_run_at 应有值"
        finally:
            await scheduler.shutdown()


class TestSchedulerScheduleStatus:
    """测试调度状态查询。"""

    @pytest.mark.asyncio
    async def test_schedule_status_before_start(self, scheduler: StrategyScheduler) -> None:
        """未启动前，调度状态应为 running=False。"""
        await scheduler.start()
        try:
            schedule = scheduler.get_strategy_schedule("fake")
            assert schedule is not None
            assert schedule["running"] is False
            assert schedule["cron"] == "*/1 * * * * *"
            assert schedule["next_run_at"] is None
            assert schedule["last_run_at"] is None
        finally:
            await scheduler.shutdown()

    @pytest.mark.asyncio
    async def test_list_all_schedules(self, exchange: MockExchange) -> None:
        """list_all_schedules 应返回所有策略的调度状态。"""
        repo = exchange.db  # type: ignore[attr-defined]
        strategies = [FakeStrategy(exchange), FailingStrategy(exchange)]
        scheduler = StrategyScheduler(repo=repo, strategies=strategies)
        await scheduler.start()
        try:
            schedules = scheduler.list_all_schedules()
            assert len(schedules) == 2
            names = {s["strategy_name"] for s in schedules}
            assert names == {"fake", "failing"}
        finally:
            await scheduler.shutdown()


class FakePostGenerator:
    """内存版贴文生成器，记录调用。"""

    def __init__(self) -> None:
        self.calls: list[str] = []

    async def generate_for_execution(self, execution_id: str) -> list:
        self.calls.append(execution_id)
        return []


class TestSchedulerPostGeneration:
    """测试调度器执行后触发贴文生成。"""

    @pytest.mark.asyncio
    async def test_post_generator_called_on_actions(self, exchange: MockExchange) -> None:
        """✅ 有动作时调用 post_generator.generate_for_execution。"""
        strategy = FakeStrategy(exchange)
        repo = exchange.db  # type: ignore[attr-defined]
        post_gen = FakePostGenerator()
        scheduler = StrategyScheduler(
            repo=repo, strategies=[strategy], post_generator=post_gen,  # type: ignore[arg-type]
        )
        await scheduler.start()
        try:
            await scheduler._execute_strategy("fake")

            assert len(post_gen.calls) == 1, "应调用一次贴文生成"
        finally:
            await scheduler.shutdown()

    @pytest.mark.asyncio
    async def test_post_generator_not_called_on_no_actions(self, exchange: MockExchange) -> None:
        """✅ 无动作时不调用 post_generator。"""
        # FailingStrategy 抛异常 -> 无动作
        strategy = FailingStrategy(exchange)
        repo = exchange.db  # type: ignore[attr-defined]
        post_gen = FakePostGenerator()
        scheduler = StrategyScheduler(
            repo=repo, strategies=[strategy], post_generator=post_gen,  # type: ignore[arg-type]
        )
        await scheduler.start()
        try:
            await scheduler._execute_strategy("failing")

            assert len(post_gen.calls) == 0, "无动作时不应调用贴文生成"
        finally:
            await scheduler.shutdown()

    @pytest.mark.asyncio
    async def test_post_generator_none_does_not_crash(self, scheduler: StrategyScheduler) -> None:
        """✅ post_generator 为 None 时不崩溃。"""
        await scheduler.start()
        try:
            await scheduler._execute_strategy("fake")
            # 不崩溃即通过
        finally:
            await scheduler.shutdown()

    @pytest.mark.asyncio
    async def test_post_generator_called_on_manual_execute(self, exchange: MockExchange) -> None:
        """✅ 手动执行（execute_strategy_manually）有动作时也触发贴文生成。"""
        strategy = FakeStrategy(exchange)
        repo = exchange.db  # type: ignore[attr-defined]
        post_gen = FakePostGenerator()
        scheduler = StrategyScheduler(
            repo=repo, strategies=[strategy], post_generator=post_gen,  # type: ignore[arg-type]
        )
        await scheduler.start()
        try:
            execution_id, actions = await scheduler.execute_strategy_manually("fake")

            assert len(actions) == 1, "应有一个动作"
            assert len(post_gen.calls) == 1, "手动执行也应触发贴文生成"
            assert post_gen.calls[0] == execution_id
        finally:
            await scheduler.shutdown()

    @pytest.mark.asyncio
    async def test_post_generator_not_called_on_manual_execute_no_actions(
        self, exchange: MockExchange
    ) -> None:
        """✅ 手动执行无动作时不触发贴文生成。"""
        strategy = FailingStrategy(exchange)
        repo = exchange.db  # type: ignore[attr-defined]
        post_gen = FakePostGenerator()
        scheduler = StrategyScheduler(
            repo=repo, strategies=[strategy], post_generator=post_gen,  # type: ignore[arg-type]
        )
        await scheduler.start()
        try:
            with pytest.raises(RuntimeError):
                await scheduler.execute_strategy_manually("failing")

            assert len(post_gen.calls) == 0, "执行失败无动作时不应触发贴文生成"
        finally:
            await scheduler.shutdown()
