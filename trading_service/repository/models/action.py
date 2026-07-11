"""策略动作记录模型"""

from __future__ import annotations

from sqlalchemy import String, Text
from sqlalchemy.orm import Mapped, mapped_column

from trading_service.repository.models.base import Base


class StrategyActionModel(Base):
    """策略动作记录模型 -- 决策层，记录每个操作的决策上下文。

    通过 execution_id 关联轮次记录，通过 position_id / order_id 关联仓位和订单。
    reason_text 存自然语言决策描述，reason_data 存结构化 JSON 数据。
    """

    __tablename__ = "trading_strategy_actions"

    id: Mapped[str] = mapped_column(String(32), primary_key=True)
    execution_id: Mapped[str] = mapped_column(String(32), nullable=False, default="", index=True)
    strategy_name: Mapped[str] = mapped_column(String(64), nullable=False, default="", index=True)
    action_type: Mapped[str] = mapped_column(String(32), nullable=False)
    symbol: Mapped[str] = mapped_column(String(32), nullable=False, default="")
    position_id: Mapped[str] = mapped_column(String(32), nullable=False, default="")
    order_id: Mapped[str] = mapped_column(String(32), nullable=False, default="")
    reason_text: Mapped[str] = mapped_column(Text, nullable=False, default="")
    reason_data: Mapped[str] = mapped_column(Text, nullable=False, default="{}")
    created_at: Mapped[str] = mapped_column(Text, nullable=False)
