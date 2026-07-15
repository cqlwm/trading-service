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
    market_cap: float = 0.0  # 开仓时定格的代币市值快照（合约口径）
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
    """策略执行历史记录（轮次级 -- 过程层）。"""

    id: str
    strategy_name: str
    started_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    finished_at: datetime | None = None
    success: bool = False
    action_count: int = 0
    error: str | None = None


@dataclass
class StrategyActionRecord:
    """策略动作记录（动作级 -- 决策层），记录每个操作的决策上下文。

    通过 position_id / order_id 与仓位、订单关联，
    通过 execution_id 与轮次记录关联。
    strategy_name 等于 position.tag，用于策略隔离。
    """

    id: str
    execution_id: str = ""
    strategy_name: str = ""
    action_type: str = ""  # "open" | "add" | "close" | "skip" | "content"
    symbol: str = ""
    position_id: str = ""
    order_id: str = ""
    reason_text: str = ""
    reason_data: dict[str, object] = field(default_factory=dict)
    signal_ids: list[str] = field(default_factory=list)  # 基于哪些信号（可多个）
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))


@dataclass
class PostRecord:
    """贴文记录（内容层），LLM 生成的社交媒体贴文及其 prompt。

    通过 execution_id 关联到策略执行轮次，与 StrategyActionRecord 同级。
    一次执行可能产多篇贴文（交易型按 symbol 分组），一对多关系。
    prompt 是发给 LLM 的完整提示词，post_text 是 LLM 返回的正文。

    发布状态字段（postx 发布到 Binance Square）：
    - published_at: 发布成功时间，None 表示尚未发布
    - share_link: Binance Square 返回的分享链接
    - publish_error: 发布失败的错误信息（用于排查和重试）
    """

    id: str
    execution_id: str = ""
    action_type: str = ""  # "content" | "trading"
    symbol: str = ""
    strategy_name: str = ""
    style: str = ""  # PostStyle.action_type 标识（"content" / "trading"）
    prompt: str = ""  # 完整 LLM prompt
    post_text: str = ""  # LLM 生成的正文
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    # 发布状态（postx 发布到 Binance Square）
    published_at: datetime | None = None
    share_link: str = ""
    publish_error: str = ""


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
        signal_type: str | None = None,
        severity_min: int | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> list[SignalRecord]:
        """列出信号"""

    def get_signals_filtered(
        self,
        symbol: str | None = None,
        signal_type: str | None = None,
        severity_min: int | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> list[SignalRecord]:
        """列出信号（别名，向后兼容）"""
        return self.list_signals(symbol, signal_type, severity_min, limit, offset)

    @abstractmethod
    def count_signals(
        self,
        symbol: str | None = None,
        signal_type: str | None = None,
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

    @abstractmethod
    def save_action(self, action: StrategyActionRecord) -> None:
        """保存策略动作记录。"""

    @abstractmethod
    def list_actions_by_execution(self, execution_id: str) -> list[StrategyActionRecord]:
        """列出某次执行的所有动作记录。"""

    @abstractmethod
    def list_actions(
        self,
        strategy_name: str | None = None,
        action_type: str | None = None,
        since: datetime | None = None,
        limit: int = 200,
    ) -> list[StrategyActionRecord]:
        """通用动作查询：按策略/类型/时间过滤，按 created_at 倒序返回。

        用于内容型策略的冷却去重：拉取近 N 小时内某策略的 content 动作，
        构建 (symbol, reason_data["signal_type"]) 冷却指纹集合。
        倒序保证 limit 截断后保留的是最新的动作。
        """

    @abstractmethod
    def list_actions_by_position(self, position_id: str) -> list[StrategyActionRecord]:
        """列出某个仓位的所有动作记录（交易故事线，按时间正序）。"""

    @abstractmethod
    def list_actions_by_symbol(self, symbol: str, limit: int = 50) -> list[StrategyActionRecord]:
        """列出某个币种的所有动作记录（币种故事线，按时间正序）。"""

    @abstractmethod
    def save_post(self, post: PostRecord) -> None:
        """保存贴文记录。"""

    @abstractmethod
    def list_posts_by_execution(self, execution_id: str) -> list[PostRecord]:
        """列出某次执行的所有贴文记录（按时间正序）。"""

    @abstractmethod
    def list_posts_by_symbol(self, symbol: str, limit: int = 50) -> list[PostRecord]:
        """列出某个币种的所有贴文记录（按时间正序）。"""

    @abstractmethod
    def get_post(self, post_id: str) -> PostRecord | None:
        """根据 ID 获取贴文记录。"""

    @abstractmethod
    def update_post_publish_result(
        self,
        post_id: str,
        published_at: datetime | None,
        share_link: str | None,
        publish_error: str | None,
    ) -> None:
        """更新贴文的发布状态（postx 发布到 Binance Square）。

        发布成功时传入 published_at + share_link（publish_error 置空）；
        发布失败时传入 publish_error（published_at/share_link 置空）。
        """

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
