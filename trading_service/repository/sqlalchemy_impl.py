"""SQLAlchemy Repository 实现"""

from __future__ import annotations

import json
from datetime import datetime, timezone

from sqlalchemy import create_engine, func, select
from sqlalchemy.orm import Session

from trading_service.repository.abc import (
    OrderRecord,
    PositionRecord,
    SignalRecord,
    StrategyExecutionRecord,
    StrategyScheduleRecord,
    TradingRepository,
)
from trading_service.repository.models import (
    OrderModel,
    PositionModel,
    SignalModel,
    StrategyExecutionModel,
    StrategyScheduleModel,
)


class SqlalchemyTradingStore(TradingRepository):
    """SQLAlchemy 实现的交易数据存储"""

    def __init__(self, db_path: str) -> None:
        self.db_url = f"sqlite:///{db_path}"
        self.engine = create_engine(self.db_url, echo=False)

    def _dt_to_str(self, dt: datetime) -> str:
        return dt.isoformat()

    def _str_to_dt(self, s: str | None) -> datetime:
        if s is None:
            return datetime.now(timezone.utc)
        return datetime.fromisoformat(s)

    def save_position(self, position: PositionRecord) -> None:
        with Session(self.engine) as session:
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
                closed_at=self._str_to_dt(model.closed_at) if model.closed_at else None,
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
                    closed_at=self._str_to_dt(m.closed_at) if m.closed_at else None,
                )
                for m in models
            ]

    def count_positions(
        self,
        status: str | None = None,
        tag: str | None = None,
    ) -> int:
        with Session(self.engine) as session:
            query = select(func.count()).select_from(PositionModel)
            if status:
                query = query.where(PositionModel.status == status)
            if tag:
                query = query.where(PositionModel.tag == tag)
            result = session.execute(query)
            return result.scalar_one()

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

    def count_orders(
        self,
        symbol: str | None = None,
        order_type: str | None = None,
    ) -> int:
        with Session(self.engine) as session:
            query = select(func.count()).select_from(OrderModel)
            if symbol:
                query = query.where(OrderModel.symbol == symbol)
            if order_type:
                query = query.where(OrderModel.order_type == order_type)
            result = session.execute(query)
            return result.scalar_one()

    def save_signal(self, signal: SignalRecord) -> None:
        with Session(self.engine) as session:
            existing = session.get(SignalModel, signal.id)
            if existing:
                existing.symbol = signal.symbol
                existing.signal_type = signal.signal_type
                existing.direction = signal.direction
                existing.severity = signal.severity
                existing.description = signal.description
                existing.metadata_json = json.dumps(signal.metadata_json)
                existing.created_at = self._dt_to_str(signal.created_at)
            else:
                model = SignalModel(
                    id=signal.id,
                    symbol=signal.symbol,
                    signal_type=signal.signal_type,
                    direction=signal.direction,
                    severity=signal.severity,
                    description=signal.description,
                    metadata_json=json.dumps(signal.metadata_json),
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
            return [self._signal_model_to_record(m) for m in models]

    def count_signals(
        self,
        symbol: str | None = None,
        severity_min: int | None = None,
    ) -> int:
        with Session(self.engine) as session:
            query = select(func.count()).select_from(SignalModel)
            if symbol:
                query = query.where(SignalModel.symbol == symbol)
            if severity_min is not None:
                query = query.where(SignalModel.severity >= severity_min)
            result = session.execute(query)
            return result.scalar_one()

    def _signal_model_to_record(self, model) -> SignalRecord:
        return SignalRecord(
            id=model.id,
            symbol=model.symbol,
            signal_type=model.signal_type,
            direction=model.direction,
            severity=model.severity,
            description=model.description,
            metadata_json=model.metadata_json or {},
            created_at=self._str_to_dt(model.created_at),
        )

    # ---- 策略调度 ----

    def save_schedule(self, schedule: StrategyScheduleRecord) -> None:
        with Session(self.engine) as session:
            existing = session.get(StrategyScheduleModel, schedule.strategy_name)
            now = self._dt_to_str(datetime.now(timezone.utc))
            if existing:
                existing.cron = schedule.cron
                existing.enabled = schedule.enabled
                existing.updated_at = now
            else:
                model = StrategyScheduleModel(
                    strategy_name=schedule.strategy_name,
                    cron=schedule.cron,
                    enabled=schedule.enabled,
                    created_at=self._dt_to_str(schedule.created_at),
                    updated_at=now,
                )
                session.add(model)
            session.commit()

    def get_schedule(self, strategy_name: str) -> StrategyScheduleRecord | None:
        with Session(self.engine) as session:
            model = session.get(StrategyScheduleModel, strategy_name)
            if model is None:
                return None
            return StrategyScheduleRecord(
                strategy_name=model.strategy_name,
                cron=model.cron,
                enabled=model.enabled,
                created_at=self._str_to_dt(model.created_at),
                updated_at=self._str_to_dt(model.updated_at),
            )

    def list_schedules(self) -> list[StrategyScheduleRecord]:
        with Session(self.engine) as session:
            result = session.execute(select(StrategyScheduleModel))
            models = result.scalars().all()
            return [
                StrategyScheduleRecord(
                    strategy_name=m.strategy_name,
                    cron=m.cron,
                    enabled=m.enabled,
                    created_at=self._str_to_dt(m.created_at),
                    updated_at=self._str_to_dt(m.updated_at),
                )
                for m in models
            ]

    def save_execution(self, execution: StrategyExecutionRecord) -> None:
        with Session(self.engine) as session:
            model = StrategyExecutionModel(
                id=execution.id,
                strategy_name=execution.strategy_name,
                started_at=self._dt_to_str(execution.started_at),
                finished_at=self._dt_to_str(execution.finished_at) if execution.finished_at else None,
                success=execution.success,
                action_count=execution.action_count,
                actions_json=json.dumps(execution.actions_json),
                error=execution.error,
            )
            session.add(model)
            session.commit()

    def list_executions(
        self,
        strategy_name: str,
        limit: int = 20,
        offset: int = 0,
    ) -> list[StrategyExecutionRecord]:
        with Session(self.engine) as session:
            query = (
                select(StrategyExecutionModel)
                .where(StrategyExecutionModel.strategy_name == strategy_name)
                .order_by(StrategyExecutionModel.started_at.desc())
                .limit(limit)
                .offset(offset)
            )
            result = session.execute(query)
            models = result.scalars().all()
            return [
                StrategyExecutionRecord(
                    id=m.id,
                    strategy_name=m.strategy_name,
                    started_at=self._str_to_dt(m.started_at),
                    finished_at=self._str_to_dt(m.finished_at) if m.finished_at else None,
                    success=m.success,
                    action_count=m.action_count,
                    actions_json=json.loads(m.actions_json) if m.actions_json else [],
                    error=m.error,
                )
                for m in models
            ]

    def begin(self) -> None:
        """开始事务（SQLAlchemy 是隐式的，这里占位）。"""
        pass

    def commit(self) -> None:
        """提交事务（SQLAlchemy 每次操作自动提交）。"""
        pass

    def rollback(self) -> None:
        """回滚事务 - 当前实现不支持真正的回滚。
        
        注意：当前的 SQLAlchemy 实现是每条语句自动 commit 的，
        如果需要真正的事务支持，需要重构为 session 模式。
        """
        pass
