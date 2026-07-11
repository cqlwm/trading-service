from __future__ import annotations

from typing import Any

from fastapi import APIRouter

from trading_service.api.deps import ExchangeDep
from trading_service.exchange import CloseResult
from trading_service.repository import SignalRecord, OrderRecord

router = APIRouter(tags=["timeline"])


def _serialize_event_data(data: SignalRecord | OrderRecord | CloseResult) -> dict[str, Any]:
    """序列化事件数据。"""
    if isinstance(data, SignalRecord):
        return {
            "id": data.id,
            "symbol": data.symbol,
            "signal_type": data.signal_type,
            "direction": data.direction,
            "severity": data.severity,
            "description": data.description,
            "metadata": data.metadata_json,
        }
    elif isinstance(data, OrderRecord):
        return {
            "id": data.id,
            "order_type": data.order_type,
            "size": data.size,
            "price": data.price,
        }
    elif isinstance(data, CloseResult):
        return {
            "position_id": data.position_id,
            "close_price": data.close_price,
            "pnl_pct": round(data.pnl_pct, 2),
        }
    return {}


@router.get("/timeline")
async def get_timeline(
    exchange: ExchangeDep,
    limit: int = 50,
    offset: int = 0,
) -> dict[str, Any]:
    """获取全局交易活动时间线（信号+订单+平仓），按时间倒序。

    返回 {data: [...], total: N}。
    """
    events = exchange.get_timeline(limit=limit, offset=offset)
    data = [
        {
            "timestamp": e.timestamp.isoformat(),
            "event_type": e.event_type,
            "data": _serialize_event_data(e.data),
        }
        for e in events
    ]
    total = exchange.db.count_signals() + exchange.db.count_orders()
    return {"data": data, "total": total}


@router.get("/story/{symbol}")
async def get_trade_story(
    symbol: str,
    exchange: ExchangeDep,
) -> list[dict[str, Any]]:
    """获取某个 Symbol 的交易故事（信号+订单+平仓时间线）。"""
    story = exchange.get_trade_story(symbol)
    return [
        {
            "timestamp": e.timestamp.isoformat(),
            "event_type": e.event_type,
            "data": _serialize_event_data(e.data),
        }
        for e in story
    ]
