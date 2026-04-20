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
    interval_minutes: int = Form(),
    _: User = Depends(get_current_user),
) -> JSONResponse:
    interval_minutes = max(1, interval_minutes)
    _manager(request).update_interval(job_id, interval_minutes * 60)
    return JSONResponse({"ok": True})
