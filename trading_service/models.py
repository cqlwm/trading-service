from __future__ import annotations

from typing import Optional

from sqlalchemy import Float, Integer, String, Text
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    """SQLAlchemy 基础模型类。"""

    pass


class PositionModel(Base):
    """持仓模型。"""

    __tablename__ = "trading_positions"

    id: Mapped[str] = mapped_column(String(32), primary_key=True)
    symbol: Mapped[str] = mapped_column(String(32), nullable=False)
    direction: Mapped[str] = mapped_column(String(16), nullable=False)
    entry_price: Mapped[float] = mapped_column(Float, nullable=False)
    total_size: Mapped[float] = mapped_column(Float, nullable=False)
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="open")
    exit_price: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    tag: Mapped[str] = mapped_column(String(64), nullable=False, default="")
    tp_hit: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    created_at: Mapped[str] = mapped_column(Text, nullable=False)
    closed_at: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    def __repr__(self) -> str:
        return f"<Position(id={self.id}, symbol={self.symbol}, status={self.status})>"


class OrderModel(Base):
    """订单模型。"""

    __tablename__ = "trading_orders"

    id: Mapped[str] = mapped_column(String(32), primary_key=True)
    position_id: Mapped[str] = mapped_column(String(32), nullable=False, default="")
    symbol: Mapped[str] = mapped_column(String(32), nullable=False)
    direction: Mapped[str] = mapped_column(String(16), nullable=False)
    size: Mapped[float] = mapped_column(Float, nullable=False)
    price: Mapped[float] = mapped_column(Float, nullable=False)
    reason: Mapped[str] = mapped_column(String(128), nullable=False, default="")
    order_type: Mapped[str] = mapped_column(String(32), nullable=False)
    created_at: Mapped[str] = mapped_column(Text, nullable=False)

    def __repr__(self) -> str:
        return f"<Order(id={self.id}, symbol={self.symbol}, type={self.order_type})>"


class SignalModel(Base):
    """信号模型。"""

    __tablename__ = "trading_signals"

    id: Mapped[str] = mapped_column(String(32), primary_key=True)
    symbol: Mapped[str] = mapped_column(String(32), nullable=False)
    signal_type: Mapped[str] = mapped_column(String(32), nullable=False)
    direction: Mapped[str] = mapped_column(String(16), nullable=False)
    severity: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    description: Mapped[str] = mapped_column(Text, nullable=False, default="")
    metadata_json: Mapped[str] = mapped_column(Text, nullable=False, default="{}")
    created_at: Mapped[str] = mapped_column(Text, nullable=False)

    def __repr__(self) -> str:
        return f"<Signal(id={self.id}, symbol={self.symbol}, severity={self.severity})>"
