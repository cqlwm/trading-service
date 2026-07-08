"""Repository 抽象基类"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any


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
    metadata_json: dict[str, Any] = field(default_factory=dict)
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))


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
