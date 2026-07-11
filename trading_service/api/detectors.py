"""信号检测器 API 端点。"""

from __future__ import annotations
from typing import Any

from fastapi import APIRouter, HTTPException

from trading_service.api.deps import SchedulerDep

router = APIRouter(prefix="/detectors", tags=["detectors"])


@router.get("")
async def list_detectors(
    scheduler: SchedulerDep,
) -> list[dict[str, Any]]:
    """列出所有信号检测器的调度状态。"""
    return scheduler.list_all_detectors()


@router.get("/{detector_name}")
async def get_detector_schedule(
    detector_name: str,
    scheduler: SchedulerDep,
) -> dict[str, Any]:
    """查看信号检测器调度状态。"""
    schedule = scheduler.get_detector_schedule(detector_name)
    if schedule is None:
        raise HTTPException(status_code=404, detail=f"检测器不存在: {detector_name}")
    return schedule


@router.post("/{detector_name}/start")
async def start_detector(
    detector_name: str,
    scheduler: SchedulerDep,
) -> dict[str, Any]:
    """启动信号检测器的定时调度。"""
    success = scheduler.start_detector(detector_name)
    if not success:
        raise HTTPException(status_code=404, detail=f"检测器不存在: {detector_name}")
    schedule = scheduler.get_detector_schedule(detector_name)
    return {"status": "ok", "detector": detector_name, "schedule": schedule}


@router.post("/{detector_name}/stop")
async def stop_detector(
    detector_name: str,
    scheduler: SchedulerDep,
) -> dict[str, Any]:
    """停止信号检测器的定时调度。"""
    success = scheduler.stop_detector(detector_name)
    if not success:
        raise HTTPException(status_code=404, detail=f"检测器不存在: {detector_name}")
    schedule = scheduler.get_detector_schedule(detector_name)
    return {"status": "ok", "detector": detector_name, "schedule": schedule}


@router.post("/{detector_name}/execute")
async def execute_detector(
    detector_name: str,
    scheduler: SchedulerDep,
) -> dict[str, Any]:
    """手动执行信号检测器。"""
    try:
        count = await scheduler.execute_detector_manually(detector_name)
        return {
            "status": "ok",
            "detector": detector_name,
            "signal_count": count,
        }
    except ValueError:
        raise HTTPException(status_code=404, detail=f"检测器不存在: {detector_name}")
