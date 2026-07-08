from __future__ import annotations

from fastapi import APIRouter

from trading_service.api.deps import ExchangeDep

router = APIRouter(tags=["signals"])


@router.get("")
async def list_signals(
    exchange: ExchangeDep,
    symbol: str | None = None,
    severity_min: int | None = None,
    limit: int = 50,
    offset: int = 0,
) -> list[dict]:
    """查询信号列表，支持按 symbol/severity 过滤和分页。"""
    signals = exchange.get_signals_filtered(
        symbol=symbol,
        severity_min=severity_min,
        limit=limit,
        offset=offset,
    )
    return [
        {
            "id": s.id,
            "symbol": s.symbol,
            "signal_type": s.signal_type,
            "direction": s.direction,
            "severity": s.severity,
            "description": s.description,
            "metadata": s.metadata,
            "created_at": s.created_at.isoformat(),
        }
        for s in signals
    ]
