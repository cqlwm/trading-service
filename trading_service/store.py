from __future__ import annotations

import json
import sqlite3
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
    position_id: str
    symbol: str
    direction: str
    size: float
    price: float
    reason: str
    order_type: str
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
    """交易数据存储抽象接口。"""

    @abstractmethod
    def save_position(self, position: PositionRecord) -> None:
        """保存持仓。"""

    @abstractmethod
    def get_position(self, position_id: str) -> PositionRecord | None:
        """获取单个持仓。"""

    @abstractmethod
    def get_positions(
        self, status: str | None = None, tag: str | None = None
    ) -> list[PositionRecord]:
        """获取持仓列表。"""

    @abstractmethod
    def save_order(self, order: OrderRecord) -> None:
        """保存订单。"""

    @abstractmethod
    def get_orders_by_position(self, position_id: str) -> list[OrderRecord]:
        """获取持仓的所有订单。"""

    @abstractmethod
    def get_orders_filtered(
        self,
        symbol: str | None = None,
        order_type: str | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> list[OrderRecord]:
        """过滤查询订单。"""

    @abstractmethod
    def save_signal(self, signal: SignalRecord) -> None:
        """保存信号。"""

    @abstractmethod
    def get_signals_filtered(
        self,
        symbol: str | None = None,
        severity_min: int | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> list[SignalRecord]:
        """过滤查询信号。"""


class SqliteTradingStore(TradingStore):
    """SQLite 实现的交易数据存储。"""

    def __init__(self, db_path: str) -> None:
        self.db_path = db_path
        self._init_tables()

    def _get_conn(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        return conn

    def _init_tables(self) -> None:
        with self._get_conn() as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS trading_positions (
                    id TEXT PRIMARY KEY,
                    symbol TEXT NOT NULL,
                    direction TEXT NOT NULL,
                    entry_price REAL NOT NULL,
                    total_size REAL NOT NULL,
                    status TEXT NOT NULL DEFAULT 'open',
                    exit_price REAL,
                    tag TEXT NOT NULL DEFAULT '',
                    tp_hit INTEGER NOT NULL DEFAULT 0,
                    created_at TEXT NOT NULL,
                    closed_at TEXT
                )
            """)
            conn.execute("""
                CREATE TABLE IF NOT EXISTS trading_orders (
                    id TEXT PRIMARY KEY,
                    position_id TEXT NOT NULL DEFAULT '',
                    symbol TEXT NOT NULL,
                    direction TEXT NOT NULL,
                    size REAL NOT NULL,
                    price REAL NOT NULL,
                    reason TEXT NOT NULL DEFAULT '',
                    order_type TEXT NOT NULL,
                    created_at TEXT NOT NULL
                )
            """)
            conn.execute("""
                CREATE TABLE IF NOT EXISTS trading_signals (
                    id TEXT PRIMARY KEY,
                    symbol TEXT NOT NULL,
                    signal_type TEXT NOT NULL,
                    direction TEXT NOT NULL,
                    severity INTEGER NOT NULL DEFAULT 0,
                    description TEXT NOT NULL DEFAULT '',
                    metadata TEXT NOT NULL DEFAULT '{}',
                    created_at TEXT NOT NULL
                )
            """)
            conn.commit()

    def _dt_to_str(self, dt: datetime) -> str:
        return dt.isoformat()

    def _str_to_dt(self, s: str | None) -> datetime | None:
        if s is None:
            return None
        return datetime.fromisoformat(s)

    def save_position(self, position: PositionRecord) -> None:
        with self._get_conn() as conn:
            conn.execute(
                """
                INSERT OR REPLACE INTO trading_positions
                (id, symbol, direction, entry_price, total_size, status,
                 exit_price, tag, tp_hit, created_at, closed_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    position.id,
                    position.symbol,
                    position.direction,
                    position.entry_price,
                    position.total_size,
                    position.status,
                    position.exit_price,
                    position.tag,
                    position.tp_hit,
                    self._dt_to_str(position.created_at),
                    self._dt_to_str(position.closed_at) if position.closed_at else None,
                ),
            )
            conn.commit()

    def get_position(self, position_id: str) -> PositionRecord | None:
        with self._get_conn() as conn:
            row = conn.execute(
                "SELECT * FROM trading_positions WHERE id = ?", (position_id,)
            ).fetchone()
            if row is None:
                return None
            return PositionRecord(
                id=row["id"],
                symbol=row["symbol"],
                direction=row["direction"],
                entry_price=row["entry_price"],
                total_size=row["total_size"],
                status=row["status"],
                exit_price=row["exit_price"],
                tag=row["tag"],
                tp_hit=row["tp_hit"],
                created_at=self._str_to_dt(row["created_at"]),
                closed_at=self._str_to_dt(row["closed_at"]),
            )

    def get_positions(
        self, status: str | None = None, tag: str | None = None
    ) -> list[PositionRecord]:
        query = "SELECT * FROM trading_positions WHERE 1=1"
        params: list[Any] = []
        if status is not None:
            query += " AND status = ?"
            params.append(status)
        if tag is not None:
            query += " AND tag LIKE ?"
            params.append(f"%{tag}%")
        query += " ORDER BY created_at DESC"

        with self._get_conn() as conn:
            rows = conn.execute(query, params).fetchall()
            return [
                PositionRecord(
                    id=r["id"],
                    symbol=r["symbol"],
                    direction=r["direction"],
                    entry_price=r["entry_price"],
                    total_size=r["total_size"],
                    status=r["status"],
                    exit_price=r["exit_price"],
                    tag=r["tag"],
                    tp_hit=r["tp_hit"],
                    created_at=self._str_to_dt(r["created_at"]),
                    closed_at=self._str_to_dt(r["closed_at"]),
                )
                for r in rows
            ]

    def save_order(self, order: OrderRecord) -> None:
        with self._get_conn() as conn:
            conn.execute(
                """
                INSERT OR REPLACE INTO trading_orders
                (id, position_id, symbol, direction, size, price, reason, order_type, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    order.id,
                    order.position_id,
                    order.symbol,
                    order.direction,
                    order.size,
                    order.price,
                    order.reason,
                    order.order_type,
                    self._dt_to_str(order.created_at),
                ),
            )
            conn.commit()

    def get_orders_by_position(self, position_id: str) -> list[OrderRecord]:
        with self._get_conn() as conn:
            rows = conn.execute(
                "SELECT * FROM trading_orders WHERE position_id = ? ORDER BY created_at ASC",
                (position_id,),
            ).fetchall()
            return [
                OrderRecord(
                    id=r["id"],
                    position_id=r["position_id"],
                    symbol=r["symbol"],
                    direction=r["direction"],
                    size=r["size"],
                    price=r["price"],
                    reason=r["reason"],
                    order_type=r["order_type"],
                    created_at=self._str_to_dt(r["created_at"]),
                )
                for r in rows
            ]

    def get_orders_filtered(
        self,
        symbol: str | None = None,
        order_type: str | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> list[OrderRecord]:
        query = "SELECT * FROM trading_orders WHERE 1=1"
        params: list[Any] = []
        if symbol is not None:
            query += " AND symbol = ?"
            params.append(symbol)
        if order_type is not None:
            query += " AND order_type = ?"
            params.append(order_type)
        query += " ORDER BY created_at DESC LIMIT ? OFFSET ?"
        params.extend([limit, offset])

        with self._get_conn() as conn:
            rows = conn.execute(query, params).fetchall()
            return [
                OrderRecord(
                    id=r["id"],
                    position_id=r["position_id"],
                    symbol=r["symbol"],
                    direction=r["direction"],
                    size=r["size"],
                    price=r["price"],
                    reason=r["reason"],
                    order_type=r["order_type"],
                    created_at=self._str_to_dt(r["created_at"]),
                )
                for r in rows
            ]

    def save_signal(self, signal: SignalRecord) -> None:
        with self._get_conn() as conn:
            conn.execute(
                """
                INSERT OR REPLACE INTO trading_signals
                (id, symbol, signal_type, direction, severity, description, metadata, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    signal.id,
                    signal.symbol,
                    signal.signal_type,
                    signal.direction,
                    signal.severity,
                    signal.description,
                    json.dumps(signal.metadata),
                    self._dt_to_str(signal.created_at),
                ),
            )
            conn.commit()

    def get_signals_filtered(
        self,
        symbol: str | None = None,
        severity_min: int | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> list[SignalRecord]:
        query = "SELECT * FROM trading_signals WHERE 1=1"
        params: list[Any] = []
        if symbol is not None:
            query += " AND symbol = ?"
            params.append(symbol)
        if severity_min is not None:
            query += " AND severity >= ?"
            params.append(severity_min)
        query += " ORDER BY created_at DESC LIMIT ? OFFSET ?"
        params.extend([limit, offset])

        with self._get_conn() as conn:
            rows = conn.execute(query, params).fetchall()
            return [
                SignalRecord(
                    id=r["id"],
                    symbol=r["symbol"],
                    signal_type=r["signal_type"],
                    direction=r["direction"],
                    severity=r["severity"],
                    description=r["description"],
                    metadata=json.loads(r["metadata"]),
                    created_at=self._str_to_dt(r["created_at"]),
                )
                for r in rows
            ]
