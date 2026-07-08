from __future__ import annotations

import logging
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any

from trading_service.store import (
    OrderRecord,
    PositionRecord,
    SignalRecord,
    TradingStore,
)
from trading_service.types import OrderType, TradeDirection

logger = logging.getLogger(__name__)


@dataclass
class CloseResult:
    """平仓结果。"""

    position_id: str
    close_price: float
    pnl_pct: float
    reason: str


@dataclass
class StoryEvent:
    """交易故事事件。"""

    timestamp: datetime
    event_type: str  # "signal" | "order" | "close"
    data: SignalRecord | OrderRecord | CloseResult


@dataclass
class Order:
    """订单。"""

    id: str
    position_id: str
    symbol: str
    direction: TradeDirection
    size: float
    price: float
    reason: str
    order_type: OrderType
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))

    @classmethod
    def from_record(cls, record: OrderRecord) -> Order:
        return cls(
            id=record.id,
            position_id=record.position_id,
            symbol=record.symbol,
            direction=TradeDirection(record.direction),
            size=record.size,
            price=record.price,
            reason=record.reason,
            order_type=OrderType(record.order_type),
            created_at=record.created_at,
        )


@dataclass
class Position:
    """持仓。"""

    id: str
    symbol: str
    direction: TradeDirection
    entry_price: float
    total_size: float
    status: str = "open"
    exit_price: float | None = None
    tag: str = ""
    tp_hit: int = 0
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    closed_at: datetime | None = None
    orders: list[Order] = field(default_factory=list)

    @classmethod
    def from_record(
        cls, record: PositionRecord, orders: list[OrderRecord] | None = None
    ) -> Position:
        pos = cls(
            id=record.id,
            symbol=record.symbol,
            direction=TradeDirection(record.direction),
            entry_price=record.entry_price,
            total_size=record.total_size,
            status=record.status,
            exit_price=record.exit_price,
            tag=record.tag,
            tp_hit=record.tp_hit,
            created_at=record.created_at,
            closed_at=record.closed_at,
        )
        if orders:
            pos.orders = [Order.from_record(o) for o in orders]
        return pos

    def to_record(self) -> PositionRecord:
        return PositionRecord(
            id=self.id,
            symbol=self.symbol,
            direction=self.direction.value,
            entry_price=self.entry_price,
            total_size=self.total_size,
            status=self.status,
            exit_price=self.exit_price,
            tag=self.tag,
            tp_hit=self.tp_hit,
            created_at=self.created_at,
            closed_at=self.closed_at,
        )

    def pnl_pct(self, current_price: float) -> float:
        """计算当前盈亏百分比。"""
        if self.direction == TradeDirection.LONG:
            return (current_price - self.entry_price) / self.entry_price * 100
        return (self.entry_price - current_price) / self.entry_price * 100

    @property
    def final_pnl_pct(self) -> float | None:
        """最终盈亏百分比（已平仓）。"""
        if self.exit_price is None:
            return None
        return self.pnl_pct(self.exit_price)


class MockExchange:
    """模拟交易所 - 核心业务逻辑。"""

    def __init__(self, db: TradingStore) -> None:
        self.db = db

    def _new_id(self) -> str:
        return uuid.uuid4().hex[:12]

    def get_position(self, position_id: str) -> Position | None:
        """获取单个持仓。"""
        record = self.db.get_position(position_id)
        if record is None:
            return None
        orders = self.db.get_orders_by_position(position_id)
        return Position.from_record(record, orders)

    def get_positions(
        self, status: str | None = None, tag: str | None = None
    ) -> list[Position]:
        """获取持仓列表。"""
        records = self.db.get_positions(status=status, tag=tag)
        positions: list[Position] = []
        for r in records:
            orders = self.db.get_orders_by_position(r.id)
            positions.append(Position.from_record(r, orders))
        return positions

    def get_position_context(self, position_id: str) -> dict[str, Any] | None:
        """获取持仓上下文（用于 API 响应）。"""
        pos = self.get_position(position_id)
        if pos is None:
            return None
        return {
            "id": pos.id,
            "symbol": pos.symbol,
            "direction": pos.direction.value,
            "entry_price": pos.entry_price,
            "total_size": pos.total_size,
            "status": pos.status,
            "exit_price": pos.exit_price,
            "tag": pos.tag,
            "tp_hit": pos.tp_hit,
            "layers": len([o for o in pos.orders if o.order_type == OrderType.ADD]) + 1,
            "created_at": pos.created_at.isoformat(),
            "closed_at": pos.closed_at.isoformat() if pos.closed_at else None,
            "orders": [
                {
                    "id": o.id,
                    "order_type": o.order_type.value,
                    "size": o.size,
                    "price": o.price,
                    "reason": o.reason,
                    "direction": o.direction.value,
                    "created_at": o.created_at.isoformat(),
                }
                for o in pos.orders
            ],
        }

    def close_position(self, position_id: str, reason: str = "manual") -> CloseResult | None:
        """手动平仓。"""
        pos = self.get_position(position_id)
        if pos is None or pos.status != "open":
            return None

        # 简化：用入场价作为平仓价（实际应该获取市场价）
        close_price = pos.entry_price
        pnl_pct = pos.pnl_pct(close_price)

        pos.status = "closed"
        pos.exit_price = close_price
        pos.closed_at = datetime.now(timezone.utc)
        self.db.save_position(pos.to_record())

        return CloseResult(
            position_id=position_id,
            close_price=close_price,
            pnl_pct=pnl_pct,
            reason=reason,
        )

    def get_orders_filtered(
        self,
        symbol: str | None = None,
        order_type: str | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> list[Order]:
        """过滤查询订单。"""
        records = self.db.get_orders_filtered(
            symbol=symbol, order_type=order_type, limit=limit, offset=offset
        )
        return [Order.from_record(r) for r in records]

    def get_signals_filtered(
        self,
        symbol: str | None = None,
        severity_min: int | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> list[SignalRecord]:
        """过滤查询信号。"""
        return self.db.get_signals_filtered(
            symbol=symbol, severity_min=severity_min, limit=limit, offset=offset
        )

    def get_timeline(
        self, limit: int = 50, offset: int = 0
    ) -> list[StoryEvent]:
        """获取全局交易活动时间线。"""
        events: list[StoryEvent] = []

        # 获取最近的信号和订单
        signals = self.db.get_signals_filtered(limit=limit, offset=offset)
        orders = self.db.get_orders_filtered(limit=limit, offset=offset)

        for s in signals:
            events.append(StoryEvent(timestamp=s.created_at, event_type="signal", data=s))
        for o in orders:
            events.append(StoryEvent(timestamp=o.created_at, event_type="order", data=o))

        # 按时间排序
        events.sort(key=lambda e: e.timestamp, reverse=True)
        return events[:limit]

    def get_trade_story(self, symbol: str) -> list[StoryEvent]:
        """获取某个 Symbol 的交易故事。"""
        events: list[StoryEvent] = []

        signals = self.db.get_signals_filtered(symbol=symbol, limit=100)
        orders = self.db.get_orders_filtered(symbol=symbol, limit=100)

        for s in signals:
            events.append(StoryEvent(timestamp=s.created_at, event_type="signal", data=s))
        for o in orders:
            events.append(StoryEvent(timestamp=o.created_at, event_type="order", data=o))

        events.sort(key=lambda e: e.timestamp)
        return events

    async def fetch_prices(self, symbols: list[str]) -> dict[str, float]:
        """获取最新价格（占位实现 - 实际通过 news-service API 获取）。"""
        # TODO: 通过 news-service API 获取价格
        return {s: 0.0 for s in symbols}
