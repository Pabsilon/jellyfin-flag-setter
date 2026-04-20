import asyncio
import logging
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from datetime import UTC, datetime

from sqlalchemy import Engine
from sqlmodel import Session

from jellyfin_flag_setter.jobs.models import DBJobConfig

logger = logging.getLogger(__name__)


@dataclass
class _JobInfo:
    job_id: str
    label: str
    default_interval: int
    fn: Callable[[], Awaitable[None]]


class JobManager:
    def __init__(self) -> None:
        self._jobs: dict[str, _JobInfo] = {}
        self._locks: dict[str, asyncio.Lock] = {}
        self._running: dict[str, bool] = {}
        self._loop_tasks: dict[str, asyncio.Task] = {}
        self._engine: Engine | None = None

    def register(
        self,
        job_id: str,
        label: str,
        fn: Callable[[], Awaitable[None]],
        default_interval: int = 3600,
    ) -> None:
        self._jobs[job_id] = _JobInfo(job_id, label, default_interval, fn)
        self._locks[job_id] = asyncio.Lock()
        self._running[job_id] = False

    def start(self, engine: Engine) -> None:
        self._engine = engine
        for job_id in self._jobs:
            self._loop_tasks[job_id] = asyncio.create_task(self._run_loop(job_id))

    async def stop(self) -> None:
        for task in self._loop_tasks.values():
            task.cancel()
        if self._loop_tasks:
            await asyncio.gather(*self._loop_tasks.values(), return_exceptions=True)

    def _get_interval(self, job_id: str) -> int:
        with Session(self._engine) as session:
            config = session.get(DBJobConfig, job_id)
        return (
            config.interval_seconds if config else self._jobs[job_id].default_interval
        )

    async def _execute(self, job_id: str) -> None:
        lock = self._locks[job_id]
        if lock.locked():
            return
        async with lock:
            self._running[job_id] = True
            try:
                await self._jobs[job_id].fn()
                with Session(self._engine) as session:
                    config = session.get(DBJobConfig, job_id)
                    if config is None:
                        config = DBJobConfig(
                            job_id=job_id,
                            interval_seconds=self._jobs[job_id].default_interval,
                        )
                    config.last_run_at = datetime.now(UTC)
                    session.add(config)
                    session.commit()
            except Exception:
                logger.exception("Job %s failed", job_id)
            finally:
                self._running[job_id] = False

    async def _run_loop(self, job_id: str) -> None:
        while True:
            interval = self._get_interval(job_id)
            await asyncio.sleep(interval)
            await self._execute(job_id)

    async def trigger(self, job_id: str) -> bool:
        """Trigger a job immediately. Returns False if already running or unknown."""
        if job_id not in self._jobs:
            return False
        if self._running[job_id]:
            return False
        asyncio.create_task(self._execute(job_id))
        return True

    def update_interval(self, job_id: str, interval_seconds: int) -> None:
        with Session(self._engine) as session:
            config = session.get(DBJobConfig, job_id)
            if config is None:
                config = DBJobConfig(job_id=job_id)
            config.interval_seconds = interval_seconds
            session.add(config)
            session.commit()
        # Restart loop so new interval takes effect on next cycle
        if job_id in self._loop_tasks:
            self._loop_tasks[job_id].cancel()
        self._loop_tasks[job_id] = asyncio.create_task(self._run_loop(job_id))

    def get_status(self, job_id: str) -> dict:
        job = self._jobs[job_id]
        with Session(self._engine) as session:
            config = session.get(DBJobConfig, job_id)
        return {
            "job_id": job_id,
            "label": job.label,
            "interval_seconds": config.interval_seconds
            if config
            else job.default_interval,
            "is_running": self._running[job_id],
            "last_run_at": (
                config.last_run_at.isoformat()
                if config and config.last_run_at
                else None
            ),
        }

    def list_statuses(self) -> list[dict]:
        return [self.get_status(job_id) for job_id in self._jobs]
