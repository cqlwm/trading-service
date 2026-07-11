from __future__ import annotations
from typing import Any

from fastapi import APIRouter, Depends, HTTPException

from trading_service.api.deps import get_exchange
from trading_service.exchange import MockExchange

router = APIRouter(tags=["positions"])


async def _fetch_open_prices(
    symbols: list[str],
    exchange: MockExchange,
) -> dict[str, float]:
    """批量获取持仓中的交易对最新价格。

    返回的 dict key 与持仓 symbol 一致（binance 原生格式）。
    """
    if not symbols:
        return {}

    return await exchange.fetch_prices(symbols)


@router.get("")
async def list_positions(
    status: str | None = None,
    exchange: MockExchange = Depends(get_exchange),
) -> dict[str, Any]:
    """查看所有持仓（含历史），可按状态过滤。

    返回 {data: [...], total: N}，total 为符合筛选条件的总数。
    """
    resolved_status = status if status in ("open", "closed") else None
    positions = exchange.get_positions(status=resolved_status)

    open_positions = [p for p in positions if p.status == "open"]
    prices: dict[str, float] = {}
    if open_positions:
        symbols = list({p.symbol for p in open_positions})
        prices = await _fetch_open_prices(symbols, exchange)

    data = [
        {
            "id": p.id,
            "symbol": p.symbol,
            "direction": p.direction.value,
            "entry_price": p.entry_price,
            "avg_price": p.entry_price,
            "current_price": prices.get(
                p.symbol, p.exit_price or p.entry_price
            ),
            "total_size": p.total_size,
            "status": p.status,
            "exit_price": p.exit_price,
            "tag": p.tag,
            "source": "short_sell"
            if "short_sell" in p.tag
            else "micro_cap"
            if "micro_cap" in p.tag
            else "martingale"
            if "martingale" in p.tag
            else "technical",
            "layers": len([o for o in p.orders if o.order_type == "ADD"]) + 1,
            "tp_hit": p.tp_hit,
            "pnl_pct": round(
                p.pnl_pct(prices.get(p.symbol, 0.0)), 2
            )
            if p.status == "open"
            else round(p.final_pnl_pct, 2)
            if p.final_pnl_pct is not None
            else 0.0,
            "created_at": p.created_at.isoformat(),
            "closed_at": p.closed_at.isoformat() if p.closed_at else None,
        }
        for p in positions
    ]

    return {"data": data, "total": len(positions)}


@router.get("/{position_id}")
async def get_position(
    position_id: str,
    exchange: MockExchange = Depends(get_exchange),
) -> dict[str, Any]:
    """查看单个持仓详情。"""
    context = exchange.get_position_context(position_id)
    if context is None:
        raise HTTPException(status_code=404, detail="持仓不存在")
    return context


@router.get("/{position_id}/actions")
async def get_position_actions(
    position_id: str,
    exchange: MockExchange = Depends(get_exchange),
) -> list[dict[str, Any]]:
    """获取持仓的所有订单记录。"""
    pos = exchange.get_position(position_id)
    if pos is None:
        return []
    return [
        {
            "id": o.id,
            "order_type": o.order_type.value,
            "size": o.size,
            "price": o.price,
            "direction": o.direction.value,
            "created_at": o.created_at.isoformat(),
        }
        for o in pos.orders
    ]


@router.post("/{position_id}/close")
async def close_position(
    position_id: str,
    exchange: MockExchange = Depends(get_exchange),
) -> dict[str, Any]:
    """手动平仓指定持仓。"""
    result = exchange.close_position(position_id)
    if result is None:
        raise HTTPException(status_code=404, detail="持仓不存在")

    return {
        "message": f"已平仓 {position_id}",
        "position_id": result.position_id,
        "close_price": result.close_price,
        "pnl_pct": round(result.pnl_pct, 2),
    }
