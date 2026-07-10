from __future__ import annotations
from typing import Any

from fastapi import APIRouter, Depends

from trading_service.api.deps import get_exchange
from trading_service.exchange import MockExchange

router = APIRouter(tags=["orders"])


@router.get("")
async def list_orders(
    symbol: str | None = None,
    order_type: str | None = None,
    limit: int = 50,
    offset: int = 0,
    exchange: MockExchange = Depends(get_exchange),
) -> dict[str, Any]:
    """查询订单列表，支持按 symbol/order_type 过滤和分页。

    返回 {data: [...], total: N}，total 为符合筛选条件的总数。
    """
    orders = exchange.get_orders_filtered(
        symbol=symbol,
        order_type=order_type,
        limit=limit,
        offset=offset,
    )
    data = [
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
    total = exchange.db.count_orders(symbol=symbol, order_type=order_type)
    return {"data": data, "total": total}
