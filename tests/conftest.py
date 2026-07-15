"""测试配置与通用夹具。"""
from __future__ import annotations

import uuid
from datetime import datetime

import pytest

from trading_service.exchange import MockExchange
from trading_service.repository import (
    OrderRecord,
    PositionRecord,
    PostRecord,
    SignalRecord,
    StrategyActionRecord,
    StrategyExecutionRecord,
    StrategyScheduleRecord,
    TradingRepository,
)


def pytest_addoption(parser: pytest.Parser) -> None:
    """添加命令行选项。"""
    parser.addoption(
        "--run-integration",
        action="store_true",
        default=False,
        help="运行集成测试（需要网络）",
    )


def pytest_configure(config: pytest.Config) -> None:
    """注册自定义 markers。"""
    config.addinivalue_line(
        "markers",
        "integration: 标记需要外部服务的集成测试",
    )


def pytest_collection_modifyitems(config: pytest.Config, items: list[pytest.Item]) -> None:
    """根据命令行选项跳过测试。"""
    if config.getoption("--run-integration"):
        # 如果指定了 --run-integration，不跳过任何测试
        return
    # 默认跳过 integration 测试
    skip_integration = pytest.mark.skip(reason="需要 --run-integration 选项才运行")
    for item in items:
        if "integration" in item.keywords:
            item.add_marker(skip_integration)


class InMemoryTradingRepository(TradingRepository):
    """内存版 Repository 实现，用于快速测试。"""

    def __init__(self) -> None:
        self.positions: dict[str, PositionRecord] = {}
        self.orders: dict[str, OrderRecord] = {}
        self.signals: dict[str, SignalRecord] = {}
        self.actions: dict[str, StrategyActionRecord] = {}
        self.posts: dict[str, PostRecord] = {}
        self._in_transaction = False
        self._temp_positions: dict[str, PositionRecord] = {}
        self._temp_orders: dict[str, OrderRecord] = {}
        self._temp_actions: dict[str, StrategyActionRecord] = {}
        self._temp_posts: dict[str, PostRecord] = {}

    def _new_id(self) -> str:
        return uuid.uuid4().hex[:12]

    def begin(self) -> None:
        self._in_transaction = True
        self._temp_positions = {}
        self._temp_orders = {}
        self._temp_actions = {}
        self._temp_posts = {}

    def commit(self) -> None:
        if self._in_transaction:
            self.positions.update(self._temp_positions)
            self.orders.update(self._temp_orders)
            self.actions.update(self._temp_actions)
            self.posts.update(self._temp_posts)
            self._in_transaction = False
            self._temp_positions = {}
            self._temp_orders = {}
            self._temp_actions = {}
            self._temp_posts = {}

    def rollback(self) -> None:
        if self._in_transaction:
            self._in_transaction = False
            self._temp_positions = {}
            self._temp_orders = {}
            self._temp_actions = {}
            self._temp_posts = {}

    def save_position(self, position: PositionRecord) -> None:
        if self._in_transaction:
            self._temp_positions[position.id] = position
        else:
            self.positions[position.id] = position

    def get_position(self, position_id: str) -> PositionRecord | None:
        if self._in_transaction and position_id in self._temp_positions:
            return self._temp_positions[position_id]
        return self.positions.get(position_id)

    def list_positions(
        self,
        symbol: str | None = None,
        status: str | None = None,
        tag: str | None = None,
    ) -> list[PositionRecord]:
        results = list(self.positions.values())
        if self._in_transaction:
            results = list(self.positions.values()) + list(self._temp_positions.values())
        if symbol:
            results = [r for r in results if r.symbol == symbol]
        if status:
            results = [r for r in results if r.status == status]
        if tag:
            results = [r for r in results if r.tag == tag]
        return results

    def get_positions(
        self,
        symbol: str | None = None,
        status: str | None = None,
        tag: str | None = None,
    ) -> list[PositionRecord]:
        return self.list_positions(symbol=symbol, status=status, tag=tag)

    def count_positions(
        self,
        status: str | None = None,
        tag: str | None = None,
    ) -> int:
        return len(self.list_positions(status=status, tag=tag))

    def save_order(self, order: OrderRecord) -> None:
        if self._in_transaction:
            self._temp_orders[order.id] = order
        else:
            self.orders[order.id] = order

    def get_orders_by_position(self, position_id: str) -> list[OrderRecord]:
        results: list[OrderRecord] = []
        for o in self.orders.values():
            if o.position_id == position_id:
                results.append(o)
        if self._in_transaction:
            for o in self._temp_orders.values():
                if o.position_id == position_id:
                    results.append(o)
        return results

    def list_orders(
        self,
        symbol: str | None = None,
        order_type: str | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> list[OrderRecord]:
        results = list(self.orders.values())
        if self._in_transaction:
            results = results + list(self._temp_orders.values())
        if symbol:
            results = [r for r in results if r.symbol == symbol]
        if order_type:
            results = [r for r in results if r.order_type == order_type]
        return results[offset:offset + limit]

    def get_orders_filtered(
        self,
        symbol: str | None = None,
        order_type: str | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> list[OrderRecord]:
        results = self.list_orders(symbol=symbol, order_type=order_type, limit=limit + offset)
        return results[offset:offset + limit]

    def count_orders(
        self,
        symbol: str | None = None,
        order_type: str | None = None,
    ) -> int:
        results = list(self.orders.values())
        if symbol:
            results = [r for r in results if r.symbol == symbol]
        if order_type:
            results = [r for r in results if r.order_type == order_type]
        return len(results)

    def save_signal(self, signal: SignalRecord) -> None:
        self.signals[signal.id] = signal

    def list_signals(
        self,
        symbol: str | None = None,
        signal_type: str | None = None,
        severity_min: int | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> list[SignalRecord]:
        results = list(self.signals.values())
        if symbol:
            results = [r for r in results if r.symbol == symbol]
        if signal_type:
            results = [r for r in results if r.signal_type == signal_type]
        if severity_min:
            results = [r for r in results if r.severity >= severity_min]
        return results[offset:offset + limit]

    def get_signals_filtered(
        self,
        symbol: str | None = None,
        signal_type: str | None = None,
        severity_min: int | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> list[SignalRecord]:
        results = self.list_signals(symbol=symbol, signal_type=signal_type, severity_min=severity_min, limit=limit + offset)
        return results[offset:offset + limit]

    def count_signals(
        self,
        symbol: str | None = None,
        signal_type: str | None = None,
        severity_min: int | None = None,
    ) -> int:
        results = list(self.signals.values())
        if symbol:
            results = [r for r in results if r.symbol == symbol]
        if signal_type:
            results = [r for r in results if r.signal_type == signal_type]
        if severity_min:
            results = [r for r in results if r.severity >= severity_min]
        return len(results)

    # ---- 策略调度 ----

    def __post_init_storage(self) -> None:
        if not hasattr(self, "schedules"):
            self.schedules: dict[str, StrategyScheduleRecord] = {}
        if not hasattr(self, "executions"):
            self.executions: dict[str, StrategyExecutionRecord] = {}

    def save_schedule(self, schedule: StrategyScheduleRecord) -> None:
        self.__post_init_storage()
        self.schedules[schedule.strategy_name] = schedule

    def get_schedule(self, strategy_name: str) -> StrategyScheduleRecord | None:
        self.__post_init_storage()
        return self.schedules.get(strategy_name)

    def list_schedules(self) -> list[StrategyScheduleRecord]:
        self.__post_init_storage()
        return list(self.schedules.values())

    def save_execution(self, execution: StrategyExecutionRecord) -> None:
        self.__post_init_storage()
        self.executions[execution.id] = execution

    def list_executions(
        self,
        strategy_name: str,
        limit: int = 20,
        offset: int = 0,
    ) -> list[StrategyExecutionRecord]:
        self.__post_init_storage()
        results = [
            e for e in self.executions.values() if e.strategy_name == strategy_name
        ]
        results.sort(key=lambda e: e.started_at, reverse=True)
        return results[offset:offset + limit]

    def save_action(self, action: StrategyActionRecord) -> None:
        if self._in_transaction:
            self._temp_actions[action.id] = action
        else:
            self.actions[action.id] = action

    def list_actions_by_execution(self, execution_id: str) -> list[StrategyActionRecord]:
        results = list(self.actions.values())
        if self._in_transaction:
            results = results + list(self._temp_actions.values())
        results = [a for a in results if a.execution_id == execution_id]
        results.sort(key=lambda a: a.created_at)
        return results

    def list_actions_by_position(self, position_id: str) -> list[StrategyActionRecord]:
        results = list(self.actions.values())
        if self._in_transaction:
            results = results + list(self._temp_actions.values())
        results = [a for a in results if a.position_id == position_id]
        results.sort(key=lambda a: a.created_at)
        return results

    def list_actions_by_symbol(self, symbol: str, limit: int = 50) -> list[StrategyActionRecord]:
        results = [a for a in self.actions.values() if a.symbol == symbol]
        results.sort(key=lambda a: a.created_at)
        return results[:limit]

    def list_actions(
        self,
        strategy_name: str | None = None,
        action_type: str | None = None,
        since: datetime | None = None,
        limit: int = 200,
    ) -> list[StrategyActionRecord]:
        results = list(self.actions.values())
        if strategy_name is not None:
            results = [a for a in results if a.strategy_name == strategy_name]
        if action_type is not None:
            results = [a for a in results if a.action_type == action_type]
        if since is not None:
            results = [a for a in results if a.created_at >= since]
        results.sort(key=lambda a: a.created_at, reverse=True)
        return results[:limit]

    def save_post(self, post: PostRecord) -> None:
        if self._in_transaction:
            self._temp_posts[post.id] = post
        else:
            self.posts[post.id] = post

    def list_posts_by_execution(self, execution_id: str) -> list[PostRecord]:
        results = list(self.posts.values())
        if self._in_transaction:
            results = results + list(self._temp_posts.values())
        results = [p for p in results if p.execution_id == execution_id]
        results.sort(key=lambda p: p.created_at)
        return results

    def list_posts_by_symbol(self, symbol: str, limit: int = 50) -> list[PostRecord]:
        results = list(self.posts.values())
        if self._in_transaction:
            results = results + list(self._temp_posts.values())
        results = [p for p in results if p.symbol == symbol]
        results.sort(key=lambda p: p.created_at)
        return results[:limit]

    def get_post(self, post_id: str) -> PostRecord | None:
        if self._in_transaction and post_id in self._temp_posts:
            return self._temp_posts[post_id]
        return self.posts.get(post_id)

    def update_post_publish_result(
        self,
        post_id: str,
        published_at: datetime | None,
        share_link: str | None,
        publish_error: str | None,
    ) -> None:
        """更新贴文的发布状态（内存实现）。"""
        post = self.posts.get(post_id)
        if post is None and self._in_transaction:
            post = self._temp_posts.get(post_id)
        if post is None:
            return
        post.published_at = published_at
        post.share_link = share_link or ""
        post.publish_error = publish_error or ""


@pytest.fixture
def exchange() -> MockExchange:
    """创建一个内存版的 MockExchange。"""
    repo = InMemoryTradingRepository()
    return MockExchange(repo)
