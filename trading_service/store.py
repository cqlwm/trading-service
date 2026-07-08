from __future__ import annotations

import json
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import create_engine, delete, select
from sqlalchemy.orm import Session

from trading_service.models import Base, OrderModel, PositionModel, SignalModel


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
    metadata: dict[str, Any] = field(default_factory=dict)
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))


class TradingStore(ABC):
    """交易数据存储接口。"""

    @abstractmethod
    def save_position(self, position: PositionRecord) -> None:
        """保存持仓。"""

    @abstractmethod
    def get_position(self, position_id: str) -> PositionRecord | None:
        """获取持仓。"""

    @abstractmethod
    def list_positions(
        self,
        symbol: str | None = None,
        status: str | None = None,
        tag: str | None = None,
    ) -> list[PositionRecord]:
        """列出持仓。"""

    @abstractmethod
    def save_order(self, order: OrderRecord) -> None:
        """保存订单。"""

    @abstractmethod
    def get_orders_by_position(self, position_id: str) -> list[OrderRecord]:
        """获取持仓的所有订单。"""

    @abstractmethod
    def list_orders(
        self,
        symbol: str | None = None,
        order_type: str | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> list[OrderRecord]:
        """列出订单。"""

    @abstractmethod
    def save_signal(self, signal: SignalRecord) -> None:
        """保存信号。"""

    @abstractmethod
    def list_signals(
        self,
        symbol: str | None = None,
        severity_min: int | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> list[SignalRecord]:
        """过滤查询信号。"""


# 添加缺失的 dataclasses import
import sys
from dataclasses import field as _field

# 修复 dataclasses field 导入
PositionRecord.__dataclass_fields__["created_at"].default_factory = lambda: datetime.now(timezone.utc)
if "created_at" not in PositionRecord.__annotations__:
    PositionRecord.__annotations__["created_at"] = datetime


class SqlalchemyTradingStore(TradingStore):
    """SQLAlchemy 实现的交易数据存储。"""

    def __init__(self, db_path: str) -> None:
        self.db_url = f"sqlite:///{db_path}"
        self.engine = create_engine(self.db_url, echo=False)

    def _dt_to_str(self, dt: datetime) -> str:
        return dt.isoformat()

    def _str_to_dt(self, s: str | None) -> datetime | None:
        if s is None:
            return None
        return datetime.fromisoformat(s)

    def save_position(self, position: PositionRecord) -> None:
        with Session(self.engine) as session:
            # 查询是否存在
            existing = session.get(PositionModel, position.id)
            if existing:
                existing.symbol = position.symbol
                existing.direction = position.direction
                existing.entry_price = position.entry_price
                existing.total_size = position.total_size
                existing.status = position.status
                existing.exit_price = position.exit_price
                existing.tag = position.tag
                existing.tp_hit = position.tp_hit
                existing.created_at = self._dt_to_str(position.created_at)
                existing.closed_at = self._dt_to_str(position.closed_at) if position.closed_at else None
            else:
                model = PositionModel(
                    id=position.id,
                    symbol=position.symbol,
                    direction=position.direction,
                    entry_price=position.entry_price,
                    total_size=position.total_size,
                    status=position.status,
                    exit_price=position.exit_price,
                    tag=position.tag,
                    tp_hit=position.tp_hit,
                    created_at=self._dt_to_str(position.created_at),
                    closed_at=self._dt_to_str(position.closed_at) if position.closed_at else None,
                )
                session.add(model)
            session.commit()

    def get_position(self, position_id: str) -> PositionRecord | None:
        with Session(self.engine) as session:
            model = session.get(PositionModel, position_id)
            if model is None:
                return None
            return PositionRecord(
                id=model.id,
                symbol=model.symbol,
                direction=model.direction,
                entry_price=model.entry_price,
                total_size=model.total_size,
                status=model.status,
                exit_price=model.exit_price,
                tag=model.tag,
                tp_hit=model.tp_hit,
                created_at=self._str_to_dt(model.created_at),
                closed_at=self._str_to_dt(model.closed_at),
            )

    def list_positions(
        self,
        symbol: str | None = None,
        status: str | None = None,
        tag: str | None = None,
    ) -> list[PositionRecord]:
        with Session(self.engine) as session:
            query = select(PositionModel)
            if symbol:
                query = query.where(PositionModel.symbol == symbol)
            if status:
                query = query.where(PositionModel.status == status)
            if tag:
                query = query.where(PositionModel.tag == tag)
            query = query.order_by(PositionModel.created_at.desc())

            result = session.execute(query)
            models = result.scalars().all()

            return [
                PositionRecord(
                    id=m.id,
                    symbol=m.symbol,
                    direction=m.direction,
                    entry_price=m.entry_price,
                    total_size=m.total_size,
                    status=m.status,
                    exit_price=m.exit_price,
                    tag=m.tag,
                    tp_hit=m.tp_hit,
                    created_at=self._str_to_dt(m.created_at),
                    closed_at=self._str_to_dt(m.closed_at),
                )
                for m in models
            ]

    def save_order(self, order: OrderRecord) -> None:
        with Session(self.engine) as session:
            existing = session.get(OrderModel, order.id)
            if existing:
                existing.position_id = order.position_id
                existing.symbol = order.symbol
                existing.direction = order.direction
                existing.size = order.size
                existing.price = order.price
                existing.reason = order.reason
                existing.order_type = order.order_type
                existing.created_at = self._dt_to_str(order.created_at)
            else:
                model = OrderModel(
                    id=order.id,
                    position_id=order.position_id,
                    symbol=order.symbol,
                    direction=order.direction,
                    size=order.size,
                    price=order.price,
                    reason=order.reason,
                    order_type=order.order_type,
                    created_at=self._dt_to_str(order.created_at),
                )
                session.add(model)
            session.commit()

    def get_orders_by_position(self, position_id: str) -> list[OrderRecord]:
        with Session(self.engine) as session:
            query = select(OrderModel).where(OrderModel.position_id == position_id).order_by(OrderModel.created_at)
            result = session.execute(query)
            models = result.scalars().all()

            return [
                OrderRecord(
                    id=m.id,
                    position_id=m.position_id,
                    symbol=m.symbol,
                    direction=m.direction,
                    size=m.size,
                    price=m.price,
                    reason=m.reason,
                    order_type=m.order_type,
                    created_at=self._str_to_dt(m.created_at),
                )
                for m in models
            ]

    def list_orders(
        self,
        symbol: str | None = None,
        order_type: str | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> list[OrderRecord]:
        with Session(self.engine) as session:
            query = select(OrderModel)
            if symbol:
                query = query.where(OrderModel.symbol == symbol)
            if order_type:
                query = query.where(OrderModel.order_type == order_type)
            query = query.order_by(OrderModel.created_at.desc()).limit(limit).offset(offset)

            result = session.execute(query)
            models = result.scalars().all()

            return [
                OrderRecord(
                    id=m.id,
                    position_id=m.position_id,
                    symbol=m.symbol,
                    direction=m.direction,
                    size=m.size,
                    price=m.price,
                    reason=m.reason,
                    order_type=m.order_type,
                    created_at=self._str_to_dt(m.created_at),
                )
                for m in models
            ]

    def save_signal(self, signal: SignalRecord) -> None:
        with Session(self.engine) as session:
            existing = session.get(SignalModel, signal.id)
            if existing:
                existing.symbol = signal.symbol
                existing.signal_type = signal.signal_type
                existing.direction = signal.direction
                existing.severity = signal.severity
                existing.description = signal.description
                existing.metadata = json.dumps(signal.metadata)
                existing.created_at = self._dt_to_str(signal.created_at)
            else:
                model = SignalModel(
                    id=signal.id,
                    symbol=signal.symbol,
                    signal_type=signal.signal_type,
                    direction=signal.direction,
                    severity=signal.severity,
                    description=signal.description,
                    metadata_json=json.dumps(signal.metadata),
                    created_at=self._dt_to_str(signal.created_at),
                )
                session.add(model)
            session.commit()

    def list_signals(
        self,
        symbol: str | None = None,
        severity_min: int | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> list[SignalRecord]:
        with Session(self.engine) as session:
            query = select(SignalModel)
            if symbol:
                query = query.where(SignalModel.symbol == symbol)
            if severity_min is not None:
                query = query.where(SignalModel.severity >= severity_min)
            query = query.order_by(SignalModel.created_at.desc()).limit(limit).offset(offset)

            result = session.execute(query)
            models = result.scalars().all()

            return [
                SignalRecord(
                    id=m.id,
                    symbol=m.symbol,
                    signal_type=m.signal_type,
                    direction=m.direction,
                    severity=m.severity,
                    description=m.description,
                    metadata_json=json.loads(m.metadata_json),
                    created_at=self._str_to_dt(m.created_at),
                )
                for m in models
            ]
