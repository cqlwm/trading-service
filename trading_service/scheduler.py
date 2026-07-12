"""策略定时调度器。

基于 APScheduler AsyncIOScheduler，统一管理所有策略的定时执行。
调度状态持久化到数据库，服务重启后自动恢复关闭前的运行状态。

信号检测器作为策略组件运行，调度器只负责调度策略。
"""

from __future__ import annotations

import logging
import uuid
from datetime import datetime, timezone
from typing import TYPE_CHECKING, Any

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger

from trading_service.repository import (
    StrategyActionRecord,
    StrategyExecutionRecord,
    StrategyScheduleRecord,
    TradingRepository,
)
from trading_service.strategies.base import Strategy, StrategyAction

if TYPE_CHECKING:
    from trading_service.content.post_generator import PostGenerator

logger = logging.getLogger(__name__)


def _parse_cron(expr: str) -> CronTrigger:
    """解析 cron 表达式为 CronTrigger。

    支持标准 5 字段（分 时 日 月 周）和扩展 6 字段（秒 分 时 日 月 周）。
    空表达式会抛 ValueError。
    """
    fields = expr.split()
    if len(fields) == 5:
        # 标准 crontab：分 时 日 月 周
        return CronTrigger(
            minute=fields[0],
            hour=fields[1],
            day=fields[2],
            month=fields[3],
            day_of_week=fields[4],
        )
    if len(fields) == 6:
        # 扩展：秒 分 时 日 月 周
        return CronTrigger(
            second=fields[0],
            minute=fields[1],
            hour=fields[2],
            day=fields[3],
            month=fields[4],
            day_of_week=fields[5],
        )
    raise ValueError(
        f"不支持的 cron 表达式字段数: {len(fields)}（支持 5 或 6 字段）: {expr}"
    )


class StrategyScheduler:
    """统一策略调度器。

    管理所有注册策略的定时执行，支持启动/停止/状态查询/执行历史。
    信号检测器作为策略组件，由策略在 execute() 内部调用，调度器不直接管理。
    策略执行后可选触发贴文生成（PostGenerator）。
    """

    def __init__(
        self,
        repo: TradingRepository,
        strategies: list[Strategy],
        post_generator: PostGenerator | None = None,
    ) -> None:
        self._repo = repo
        self._strategies: dict[str, Strategy] = {s.name: s for s in strategies if s.name}
        self._scheduler = AsyncIOScheduler()
        self._post_generator = post_generator

    def _now(self) -> str:
        return datetime.now(timezone.utc).isoformat()

    def _new_id(self) -> str:
        return uuid.uuid4().hex[:12]

    def _job_id(self, strategy_name: str) -> str:
        return f"strategy_{strategy_name}"

    async def start(self) -> None:
        """启动调度器，并从数据库恢复 enabled 的策略。"""
        if self._scheduler.running:
            return

        self._scheduler.start()
        logger.info("策略调度器已启动")

        # 恢复关闭前 enabled 的策略
        for record in self._repo.list_schedules():
            if record.enabled and record.strategy_name in self._strategies:
                strategy = self._strategies[record.strategy_name]
                self._add_job(strategy)
                logger.info(f"恢复策略调度: {strategy.name} (cron={strategy.cron})")

    async def shutdown(self) -> None:
        """优雅停止调度器。"""
        if self._scheduler.running:
            self._scheduler.shutdown(wait=False)
            logger.info("策略调度器已停止")

    def _add_job(self, strategy: Strategy) -> None:
        """添加策略的定时任务。"""
        trigger = _parse_cron(strategy.cron)
        self._scheduler.add_job(
            self._execute_strategy,
            trigger,
            id=self._job_id(strategy.name),
            replace_existing=True,
            args=[strategy.name],
        )

    def _remove_job(self, strategy_name: str) -> None:
        """移除策略的定时任务。"""
        job_id = self._job_id(strategy_name)
        if self._scheduler.get_job(job_id):
            self._scheduler.remove_job(job_id)

    def start_strategy(self, strategy_name: str) -> bool:
        """启动策略的定时调度。

        Returns:
            True 表示成功启动，False 表示策略不存在。
        """
        strategy = self._strategies.get(strategy_name)
        if strategy is None:
            return False

        self._add_job(strategy)
        self._persist_schedule(strategy_name, enabled=True)
        logger.info(f"策略调度已启动: {strategy_name} (cron={strategy.cron})")
        return True

    def stop_strategy(self, strategy_name: str) -> bool:
        """停止策略的定时调度。

        Returns:
            True 表示成功停止，False 表示策略不存在。
        """
        if strategy_name not in self._strategies:
            return False

        self._remove_job(strategy_name)
        self._persist_schedule(strategy_name, enabled=False)
        logger.info(f"策略调度已停止: {strategy_name}")
        return True

    def _persist_schedule(self, strategy_name: str, enabled: bool) -> None:
        """持久化策略调度状态。"""
        strategy = self._strategies[strategy_name]
        existing = self._repo.get_schedule(strategy_name)
        now = datetime.now(timezone.utc)
        self._repo.save_schedule(StrategyScheduleRecord(
            strategy_name=strategy_name,
            cron=strategy.cron,
            enabled=enabled,
            created_at=existing.created_at if existing else now,
            updated_at=now,
        ))

    def get_strategy_schedule(self, strategy_name: str) -> dict[str, Any] | None:
        """获取策略调度状态。"""
        strategy = self._strategies.get(strategy_name)
        if strategy is None:
            return None

        record = self._repo.get_schedule(strategy_name)
        running = record is not None and record.enabled and self._scheduler.get_job(self._job_id(strategy_name)) is not None

        # 下次执行时间
        job = self._scheduler.get_job(self._job_id(strategy_name))
        next_run_at = job.next_run_time.isoformat() if job and job.next_run_time else None

        # 上次执行时间
        executions = self._repo.list_executions(strategy_name, limit=1)
        last_run_at = executions[0].started_at.isoformat() if executions else None

        return {
            "strategy_name": strategy_name,
            "running": running,
            "cron": strategy.cron,
            "next_run_at": next_run_at,
            "last_run_at": last_run_at,
        }

    async def _execute_strategy(self, strategy_name: str) -> None:
        """执行策略并记录结果（调度器回调）。"""
        strategy = self._strategies.get(strategy_name)
        if strategy is None:
            logger.warning(f"调度执行找不到策略: {strategy_name}")
            return

        execution_id = self._new_id()
        started_at = datetime.now(timezone.utc)

        logger.info(f"策略 {strategy_name} 定时执行开始 (execution_id={execution_id})")

        try:
            actions = await strategy.execute(execution_id=execution_id)
            finished_at = datetime.now(timezone.utc)
            self._repo.save_execution(StrategyExecutionRecord(
                id=execution_id,
                strategy_name=strategy_name,
                started_at=started_at,
                finished_at=finished_at,
                success=True,
                action_count=len(actions),
            ))
            logger.info(
                f"策略 {strategy_name} 定时执行完成: {len(actions)} 项操作"
            )

            # 贴文生成：有动作变动时触发，失败不影响策略执行
            if actions and self._post_generator:
                try:
                    self._post_generator.generate_for_execution(execution_id)
                except Exception as e:
                    logger.warning(f"贴文生成失败（不影响策略执行）: {e}")
        except Exception as e:
            finished_at = datetime.now(timezone.utc)
            self._repo.save_execution(StrategyExecutionRecord(
                id=execution_id,
                strategy_name=strategy_name,
                started_at=started_at,
                finished_at=finished_at,
                success=False,
                action_count=0,
                error=str(e),
            ))
            logger.error(f"策略 {strategy_name} 定时执行失败: {e}", exc_info=True)

    async def execute_strategy_manually(
        self, strategy_name: str
    ) -> tuple[str, list[StrategyAction]]:
        """手动执行策略，创建执行记录。返回 (execution_id, actions)。

        与 _execute_strategy 逻辑相同，但同步返回结果。
        手动执行也产生 execution record + action records。
        """
        strategy = self._strategies.get(strategy_name)
        if strategy is None:
            raise ValueError(f"策略不存在: {strategy_name}")

        execution_id = self._new_id()
        started_at = datetime.now(timezone.utc)

        logger.info(f"策略 {strategy_name} 手动执行开始 (execution_id={execution_id})")

        try:
            actions = await strategy.execute(execution_id=execution_id)
            finished_at = datetime.now(timezone.utc)
            self._repo.save_execution(StrategyExecutionRecord(
                id=execution_id,
                strategy_name=strategy_name,
                started_at=started_at,
                finished_at=finished_at,
                success=True,
                action_count=len(actions),
            ))
            logger.info(
                f"策略 {strategy_name} 手动执行完成: {len(actions)} 项操作"
            )

            # 贴文生成：有动作变动时触发，失败不影响策略执行
            if actions and self._post_generator:
                try:
                    self._post_generator.generate_for_execution(execution_id)
                except Exception as e:
                    logger.warning(f"贴文生成失败（不影响策略执行）: {e}")

            return execution_id, actions
        except Exception as e:
            finished_at = datetime.now(timezone.utc)
            self._repo.save_execution(StrategyExecutionRecord(
                id=execution_id,
                strategy_name=strategy_name,
                started_at=started_at,
                finished_at=finished_at,
                success=False,
                action_count=0,
                error=str(e),
            ))
            logger.error(f"策略 {strategy_name} 手动执行失败: {e}", exc_info=True)
            raise

    def list_executions(self, strategy_name: str, limit: int = 20, offset: int = 0) -> list[StrategyExecutionRecord]:
        """查询策略执行历史。"""
        return self._repo.list_executions(strategy_name, limit=limit, offset=offset)

    def list_actions_by_execution(self, execution_id: str) -> list[StrategyActionRecord]:
        """查询某次执行的所有动作记录。"""
        return self._repo.list_actions_by_execution(execution_id)

    def list_all_schedules(self) -> list[dict[str, Any]]:
        """列出所有策略的调度状态。"""
        result = []
        for name in self._strategies:
            schedule = self.get_strategy_schedule(name)
            if schedule:
                result.append(schedule)
        return result
