from __future__ import annotations
from typing import Any

from fastapi import APIRouter, HTTPException

from trading_service.api.deps import MartingaleDep, MicroCapDep, SchedulerDep

router = APIRouter(tags=["strategies"])


def _format_actions(actions: list) -> list[dict[str, str]]:
    """格式化策略动作为 API 响应。"""
    return [
        {"type": a.type, "symbol": a.symbol, "detail": a.detail}
        for a in actions
    ]


@router.post("/martingale/execute")
async def execute_martingale(
    strategy: MartingaleDep,
) -> dict[str, Any]:
    """执行马丁策略。"""
    actions = await strategy.execute()
    return {
        "status": "ok",
        "strategy": "martingale",
        "actions": _format_actions(actions),
        "action_count": len(actions),
    }


@router.get("/martingale/status")
async def get_martingale_status(
    strategy: MartingaleDep,
    scheduler: SchedulerDep,
) -> dict[str, Any]:
    """查看马丁策略状态（含调度信息）。"""
    status = strategy.get_status()
    status["schedule"] = scheduler.get_strategy_schedule("martingale")
    return status

@router.post("/micro-cap/execute")
async def execute_micro_cap(
    strategy: MicroCapDep,
) -> dict[str, Any]:
    """执行微市值策略。"""
    actions = await strategy.execute()
    return {
        "status": "ok",
        "strategy": "micro_cap",
        "actions": _format_actions(actions),
        "action_count": len(actions),
    }


@router.get("/micro-cap/status")
async def get_micro_cap_status(
    strategy: MicroCapDep,
    scheduler: SchedulerDep,
) -> dict[str, Any]:
    """查看微市值策略状态（含调度信息）。"""
    status = strategy.get_status()
    status["schedule"] = scheduler.get_strategy_schedule("micro_cap")
    return status


@router.get("/micro-cap/history")
async def get_micro_cap_history(
    strategy: MicroCapDep,
    limit: int = 10,
) -> list[dict[str, Any]]:
    """查看微市值策略历史记录。"""
    return strategy.get_history(limit=limit)


# ---- 调度控制 ----

@router.post("/{strategy_name}/start")
async def start_strategy_schedule(
    strategy_name: str,
    scheduler: SchedulerDep,
) -> dict[str, Any]:
    """启动策略的定时调度。"""
    success = scheduler.start_strategy(strategy_name)
    if not success:
        raise HTTPException(status_code=404, detail=f"策略不存在: {strategy_name}")
    schedule = scheduler.get_strategy_schedule(strategy_name)
    return {"status": "ok", "strategy": strategy_name, "schedule": schedule}


@router.post("/{strategy_name}/stop")
async def stop_strategy_schedule(
    strategy_name: str,
    scheduler: SchedulerDep,
) -> dict[str, Any]:
    """停止策略的定时调度。"""
    success = scheduler.stop_strategy(strategy_name)
    if not success:
        raise HTTPException(status_code=404, detail=f"策略不存在: {strategy_name}")
    schedule = scheduler.get_strategy_schedule(strategy_name)
    return {"status": "ok", "strategy": strategy_name, "schedule": schedule}


@router.get("/{strategy_name}/schedule")
async def get_strategy_schedule(
    strategy_name: str,
    scheduler: SchedulerDep,
) -> dict[str, Any]:
    """查看策略调度状态。"""
    schedule = scheduler.get_strategy_schedule(strategy_name)
    if schedule is None:
        raise HTTPException(status_code=404, detail=f"策略不存在: {strategy_name}")
    return schedule


@router.get("/{strategy_name}/executions")
async def get_strategy_executions(
    strategy_name: str,
    scheduler: SchedulerDep,
    limit: int = 20,
    offset: int = 0,
) -> dict[str, Any]:
    """查看策略执行历史。"""
    executions = scheduler.list_executions(strategy_name, limit=limit, offset=offset)
    return {
        "data": [
            {
                "id": e.id,
                "strategy_name": e.strategy_name,
                "started_at": e.started_at.isoformat(),
                "finished_at": e.finished_at.isoformat() if e.finished_at else None,
                "success": e.success,
                "action_count": e.action_count,
                "actions": e.actions_json,
                "error": e.error,
            }
            for e in executions
        ],
        "total": len(executions),
    }
