from __future__ import annotations

from fastapi import APIRouter

from trading_service.api.deps import MartingaleDep, MicroCapDep

router = APIRouter(tags=["strategies"])


@router.post("/martingale/execute")
async def execute_martingale(
    strategy: MartingaleDep,
) -> dict:
    """执行马丁策略。"""
    await strategy.execute()
    return {"status": "ok", "message": "Martingale strategy executed"}


@router.get("/martingale/status")
async def get_martingale_status(
    strategy: MartingaleDep,
) -> dict:
    """查看马丁策略状态。"""
    return strategy.get_status()


@router.post("/micro-cap/execute")
async def execute_micro_cap(
    strategy: MicroCapDep,
) -> dict:
    """执行微市值策略。"""
    await strategy.execute()
    return {"status": "ok", "message": "MicroCap strategy executed"}


@router.get("/micro-cap/status")
async def get_micro_cap_status(
    strategy: MicroCapDep,
) -> dict:
    """查看微市值策略状态。"""
    return strategy.get_status()


@router.get("/micro-cap/history")
async def get_micro_cap_history(
    strategy: MicroCapDep,
    limit: int = 10,
) -> list[dict]:
    """查看微市值策略历史记录。"""
    return strategy.get_history(limit=limit)
