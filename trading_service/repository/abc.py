"""Repository 抽象基类"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime, timezone


@dataclass
class PositionRecord:
    """持仓记录。"""

    id: str
    symbol: str
    direction: str
    entry_price: float
    total_size: float
    status: str = "open"
    exit_price: float | None = None
    tag: str = ""
    tp_hit: int = 0
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    closed_at: datetime | None = None


@dataclass
class OrderRecord:
    """订单记录。"""

    id: str
    symbol: str
    direction: str
    size: float
    price: float
    order_type: str
    position_id: str = ""
    reason: str = ""
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))


@dataclass
class SignalRecord:
    """信号记录。"""

    id: str
    symbol: str
    signal_type: str
    direction: str
    severity: int = 0
    description: str = ""
    metadata_json: dict[str, object] = field(default_factory=dict)
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))


@dataclass
class StrategyScheduleRecord:
    """策略调度配置记录。"""

    strategy_name: str
    cron: str = ""
    enabled: bool = False
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))


@dataclass
class StrategyExecutionRecord:
    """策略执行历史记录。"""

    id: str
    strategy_name: str
    started_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    finished_at: datetime | None = None
    success: bool = False
    action_count: int = 0
    actions_json: list[dict[str, str]] = field(default_factory=list)
    error: str | None = None


class TradingRepository(ABC):
    """交易数据 Repository 接口（工作单元模式）"""

    @abstractmethod
    def save_position(self, position: PositionRecord) -> None:
        """保存持仓"""

    @abstractmethod
    def get_position(self, position_id: str) -> PositionRecord | None:
        """根据 ID 获取持仓"""

    @abstractmethod
    def list_positions(
        self,
        symbol: str | None = None,
        status: str | None = None,
        tag: str | None = None,
    ) -> list[PositionRecord]:
        """列出持仓"""

    def get_positions(
        self,
        symbol: str | None = None,
        status: str | None = None,
        tag: str | None = None,
    ) -> list[PositionRecord]:
        """列出持仓（别名，向后兼容）"""
        return self.list_positions(symbol, status, tag)

    @abstractmethod
    def count_positions(
        self,
        status: str | None = None,
        tag: str | None = None,
    ) -> int:
        """统计持仓总数。"""

    @abstractmethod
    def save_order(self, order: OrderRecord) -> None:
        """保存订单"""

    @abstractmethod
    def get_orders_by_position(self, position_id: str) -> list[OrderRecord]:
        """获取持仓的所有订单"""

    @abstractmethod
    def list_orders(
        self,
        symbol: str | None = None,
        order_type: str | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> list[OrderRecord]:
        """列出订单"""

    def get_orders_filtered(
        self,
        symbol: str | None = None,
        order_type: str | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> list[OrderRecord]:
        """列出订单（别名，向后兼容）"""
        return self.list_orders(symbol, order_type, limit, offset)

    @abstractmethod
    def count_orders(
        self,
        symbol: str | None = None,
        order_type: str | None = None,
    ) -> int:
        """统计订单总数。"""

    @abstractmethod
    def save_signal(self, signal: SignalRecord) -> None:
        """保存信号"""

    @abstractmethod
    def list_signals(
        self,
        symbol: str | None = None,
        severity_min: int | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> list[SignalRecord]:
        """列出信号"""

    def get_signals_filtered(
        self,
        symbol: str | None = None,
        severity_min: int | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> list[SignalRecord]:
        """列出信号（别名，向后兼容）"""
        return self.list_signals(symbol, severity_min, limit, offset)

    @abstractmethod
    def count_signals(
        self,
        symbol: str | None = None,
        severity_min: int | None = None,
    ) -> int:
        """统计信号总数。"""

    # ---- 策略调度 ----

    @abstractmethod
    def save_schedule(self, schedule: StrategyScheduleRecord) -> None:
        """保存策略调度配置（upsert）。"""

    @abstractmethod
    def get_schedule(self, strategy_name: str) -> StrategyScheduleRecord | None:
        """获取策略调度配置。"""

    @abstractmethod
    def list_schedules(self) -> list[StrategyScheduleRecord]:
        """列出所有策略调度配置。"""

    @abstractmethod
    def save_execution(self, execution: StrategyExecutionRecord) -> None:
        """保存策略执行记录。"""

    @abstractmethod
    def list_executions(
        self,
        strategy_name: str,
        limit: int = 20,
        offset: int = 0,
    ) -> list[StrategyExecutionRecord]:
        """列出策略执行历史（按时间倒序）。"""

    def transaction(self) -> "TransactionContext":
        """事务上下文管理器。
        
        with repo.transaction():
            repo.save_position(...)
            repo.save_order(...)
        """
        return TransactionContext(self)

    @abstractmethod
    def begin(self) -> None:
        """开始事务"""

    @abstractmethod
    def commit(self) -> None:
        """提交事务"""

    @abstractmethod
    def rollback(self) -> None:
        """回滚事务"""


class TransactionContext:
    """事务上下文管理器。"""

    def __init__(self, repo: TradingRepository) -> None:
        self.repo = repo

    def __enter__(self) -> "TransactionContext":
        self.repo.begin()
        return self

    def __exit__(self, exc_type: object, exc_val: object, exc_tb: object) -> None:
        if exc_type is not None:
            self.repo.rollback()
        else:
            self.repo.commit()
