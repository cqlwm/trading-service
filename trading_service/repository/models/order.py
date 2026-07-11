"""订单模型"""

from __future__ import annotations

from sqlalchemy import Float, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from trading_service.repository.models.base import Base


class OrderModel(Base):
    """订单模型。"""

    __tablename__ = "trading_orders"

    id: Mapped[str] = mapped_column(String(32), primary_key=True)
    position_id: Mapped[str] = mapped_column(String(32), nullable=False, default="")
    symbol: Mapped[str] = mapped_column(String(32), nullable=False)
    direction: Mapped[str] = mapped_column(String(16), nullable=False)
    size: Mapped[float] = mapped_column(Float, nullable=False)
    price: Mapped[float] = mapped_column(Float, nullable=False)
    order_type: Mapped[str] = mapped_column(String(32), nullable=False)
    created_at: Mapped[str] = mapped_column(Text, nullable=False)
