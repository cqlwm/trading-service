from __future__ import annotations
from typing import Any

from fastapi import APIRouter

from trading_service.api.deps import ExchangeDep

router = APIRouter(tags=["signals"])


@router.get("")
async def list_signals(
    exchange: ExchangeDep,
    symbol: str | None = None,
    signal_type: str | None = None,
    severity_min: int | None = None,
    limit: int = 50,
    offset: int = 0,
) -> dict[str, Any]:
    """查询信号列表，支持按 symbol/signal_type/severity 过滤和分页。

    返回 {data: [...], total: N}，total 为符合筛选条件的总数。
    """
    signals = exchange.get_signals_filtered(
        symbol=symbol,
        signal_type=signal_type,
        severity_min=severity_min,
        limit=limit,
        offset=offset,
    )
    data = [
        {
            "id": s.id,
            "symbol": s.symbol,
            "signal_type": s.signal_type,
            "direction": s.direction,
            "severity": s.severity,
            "description": s.description,
            "metadata": s.metadata_json,
            "created_at": s.created_at.isoformat(),
        }
        for s in signals
    ]
    total = exchange.db.count_signals(symbol=symbol, signal_type=signal_type, severity_min=severity_min)
    return {"data": data, "total": total}
