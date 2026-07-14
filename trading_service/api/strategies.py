from __future__ import annotations
from typing import Any

from fastapi import APIRouter, HTTPException

from trading_service.api.deps import (
    ContentScanDep,
    MartingaleDep,
    MartingaleShortDep,
    MicroCapDep,
    SchedulerDep,
)

router = APIRouter(tags=["strategies"])


def _format_actions(actions: list) -> list[dict[str, str]]:
    """格式化策略动作为 API 响应。"""
    return [
        {"type": a.type, "symbol": a.symbol, "reason": a.reason}
        for a in actions
    ]


@router.post("/martingale/execute")
async def execute_martingale(
    scheduler: SchedulerDep,
) -> dict[str, Any]:
    """执行马丁策略。"""
    execution_id, actions = await scheduler.execute_strategy_manually("martingale")
    return {
        "status": "ok",
        "strategy": "martingale",
        "execution_id": execution_id,
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
    scheduler: SchedulerDep,
) -> dict[str, Any]:
    """执行微市值策略。"""
    execution_id, actions = await scheduler.execute_strategy_manually("micro_cap")
    return {
        "status": "ok",
        "strategy": "micro_cap",
        "execution_id": execution_id,
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


@router.post("/martingale-short/execute")
async def execute_martingale_short(
    scheduler: SchedulerDep,
) -> dict[str, Any]:
    """执行马丁做空策略。"""
    execution_id, actions = await scheduler.execute_strategy_manually("martingale_short")
    return {
        "status": "ok",
        "strategy": "martingale_short",
        "execution_id": execution_id,
        "actions": _format_actions(actions),
        "action_count": len(actions),
    }


@router.get("/martingale-short/status")
async def get_martingale_short_status(
    strategy: MartingaleShortDep,
    scheduler: SchedulerDep,
) -> dict[str, Any]:
    """查看马丁做空策略状态（含调度信息）。"""
    status = strategy.get_status()
    status["schedule"] = scheduler.get_strategy_schedule("martingale_short")
    return status


@router.post("/content-scan/execute")
async def execute_content_scan(
    scheduler: SchedulerDep,
) -> dict[str, Any]:
    """执行内容扫描策略（选币 -> 信号检测 -> 写 content 动作 -> 触发贴文生成）。"""
    execution_id, actions = await scheduler.execute_strategy_manually("content_scan")
    return {
        "status": "ok",
        "strategy": "content_scan",
        "execution_id": execution_id,
        "actions": _format_actions(actions),
        "action_count": len(actions),
    }


@router.get("/content-scan/status")
async def get_content_scan_status(
    strategy: ContentScanDep,
    scheduler: SchedulerDep,
) -> dict[str, Any]:
    """查看内容扫描策略状态（含调度信息）。"""
    status = strategy.get_status()
    status["schedule"] = scheduler.get_strategy_schedule("content_scan")
    return status


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


@router.get("/{strategy_name}/executions/{execution_id}")
async def get_execution_detail(
    strategy_name: str,
    execution_id: str,
    scheduler: SchedulerDep,
) -> dict[str, Any]:
    """查看单次策略执行详情（含动作记录和生成的贴文）。"""
    executions = scheduler.list_executions(strategy_name, limit=1000)
    execution = next((e for e in executions if e.id == execution_id), None)
    if execution is None:
        raise HTTPException(
            status_code=404,
            detail=f"执行记录不存在: {execution_id}",
        )

    actions = scheduler.list_actions_by_execution(execution_id)
    posts = scheduler.list_posts_by_execution(execution_id)

    return {
        "id": execution.id,
        "strategy_name": execution.strategy_name,
        "started_at": execution.started_at.isoformat(),
        "finished_at": execution.finished_at.isoformat() if execution.finished_at else None,
        "success": execution.success,
        "action_count": execution.action_count,
        "error": execution.error,
        "actions": [
            {
                "id": a.id,
                "action_type": a.action_type,
                "symbol": a.symbol,
                "position_id": a.position_id,
                "order_id": a.order_id,
                "reason": a.reason_text,
                "reason_data": a.reason_data,
                "signal_ids": a.signal_ids,
                "created_at": a.created_at.isoformat(),
            }
            for a in actions
        ],
        "posts": [
            {
                "id": p.id,
                "execution_id": p.execution_id,
                "action_type": p.action_type,
                "symbol": p.symbol,
                "strategy_name": p.strategy_name,
                "style": p.style,
                "prompt": p.prompt,
                "post_text": p.post_text,
                "created_at": p.created_at.isoformat(),
                "published_at": p.published_at.isoformat() if p.published_at else None,
                "share_link": p.share_link,
                "publish_error": p.publish_error,
            }
            for p in posts
        ],
    }


@router.get("/{strategy_name}/executions")
async def get_strategy_executions(
    strategy_name: str,
    scheduler: SchedulerDep,
    limit: int = 20,
    offset: int = 0,
) -> dict[str, Any]:
    """查看策略执行历史。"""
    executions = scheduler.list_executions(strategy_name, limit=limit, offset=offset)
    result = []
    for e in executions:
        actions = scheduler.list_actions_by_execution(e.id)
        result.append({
            "id": e.id,
            "strategy_name": e.strategy_name,
            "started_at": e.started_at.isoformat(),
            "finished_at": e.finished_at.isoformat() if e.finished_at else None,
            "success": e.success,
            "action_count": e.action_count,
            "error": e.error,
            "actions": [
                {
                    "id": a.id,
                    "action_type": a.action_type,
                    "symbol": a.symbol,
                    "position_id": a.position_id,
                    "order_id": a.order_id,
                    "reason": a.reason_text,
                    "reason_data": a.reason_data,
                    "signal_ids": a.signal_ids,
                    "created_at": a.created_at.isoformat(),
                }
                for a in actions
            ],
        })
    return {
        "data": result,
        "total": len(result),
    }
