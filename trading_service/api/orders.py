from __future__ import annotations
from typing import Any

from fastapi import APIRouter, Depends

from trading_service.api.deps import ExchangeDep
from trading_service.exchange import MockExchange

router = APIRouter(tags=["orders"])


@router.get("")
async def list_orders(
    symbol: str | None = None,
    order_type: str | None = None,
    limit: int = 50,
    offset: int = 0,
    exchange: MockExchange = Depends(ExchangeDep),
) -> list[dict[str, Any]]:
    """查询订单列表，支持按 symbol/order_type 过滤和分页。"""
    orders = exchange.get_orders_filtered(
        symbol=symbol,
        order_type=order_type,
        limit=limit,
        offset=offset,
    )
    return [
        {
            "id": o.id,
            "position_id": o.position_id,
            "symbol": o.symbol,
            "direction": o.direction.value,
            "size": o.size,
            "price": o.price,
            "reason": o.reason,
            "order_type": o.order_type.value,
            "created_at": o.created_at.isoformat(),
        }
        for o in orders
    ]
