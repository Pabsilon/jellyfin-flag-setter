from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import JSONResponse

from jellyfin_flag_setter.auth.dependencies import get_current_user
from jellyfin_flag_setter.auth.models import User
from jellyfin_flag_setter.jobs.runner import JobManager

router = APIRouter(prefix="/api/jobs")


def _manager(request: Request) -> JobManager:
    return request.app.state.job_manager


@router.get("")
async def list_jobs(
    request: Request,
    _: User = Depends(get_current_user),
) -> JSONResponse:
    return JSONResponse(_manager(request).list_statuses())


@router.get("/{job_id}")
async def job_status(
    job_id: str,
    request: Request,
    _: User = Depends(get_current_user),
) -> JSONResponse:
    manager = _manager(request)
    if job_id not in manager._jobs:
        return JSONResponse({"error": "unknown job"}, status_code=404)
    return JSONResponse(manager.get_status(job_id))


@router.post("/{job_id}/run")
async def run_job(
    job_id: str,
    request: Request,
    _: User = Depends(get_current_user),
) -> JSONResponse:
    triggered = await _manager(request).trigger(job_id)
    return JSONResponse({"triggered": triggered})


@router.post("/{job_id}/interval")
async def update_interval(
    job_id: str,
    request: Request,
    interval_value: int = Form(),
    _: User = Depends(get_current_user),
) -> JSONResponse:
    manager = _manager(request)
    if job_id not in manager._jobs:
        return JSONResponse({"error": "unknown job"}, status_code=404)
    interval_value = max(1, interval_value)
    status = manager.get_status(job_id)
    multiplier = 3600 if status["time_unit"] == "hours" else 60
    manager.update_interval(job_id, interval_value * multiplier)
    return JSONResponse({"ok": True})
