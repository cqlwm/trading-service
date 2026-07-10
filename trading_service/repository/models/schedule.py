"""策略调度模型"""

from __future__ import annotations

from sqlalchemy import Boolean, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from trading_service.repository.models.base import Base


class StrategyScheduleModel(Base):
    """策略调度配置模型。"""

    __tablename__ = "trading_strategy_schedules"

    strategy_name: Mapped[str] = mapped_column(String(64), primary_key=True)
    cron: Mapped[str] = mapped_column(String(128), nullable=False, default="")
    enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    created_at: Mapped[str] = mapped_column(Text, nullable=False)
    updated_at: Mapped[str] = mapped_column(Text, nullable=False)


class StrategyExecutionModel(Base):
    """策略执行历史模型。"""

    __tablename__ = "trading_strategy_executions"

    id: Mapped[str] = mapped_column(String(32), primary_key=True)
    strategy_name: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    started_at: Mapped[str] = mapped_column(Text, nullable=False)
    finished_at: Mapped[str | None] = mapped_column(Text, nullable=True)
    success: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    action_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    actions_json: Mapped[str] = mapped_column(Text, nullable=False, default="[]")
    error: Mapped[str | None] = mapped_column(Text, nullable=True)
