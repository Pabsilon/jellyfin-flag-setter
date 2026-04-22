from collections.abc import Generator
from pathlib import Path

from sqlmodel import Session, SQLModel, create_engine

import jellyfin_flag_setter.jobs.models  # noqa: F401 — registers job_config table
import jellyfin_flag_setter.sync.models  # noqa: F401 — registers sync tables with SQLModel metadata
from jellyfin_flag_setter.config import settings

_engine = None


def _get_engine():
    global _engine
    if _engine is None:
        db_path = Path(settings.db_path)
        db_path.parent.mkdir(parents=True, exist_ok=True)
        _engine = create_engine(
            f"sqlite:///{db_path}", connect_args={"check_same_thread": False}
        )
    return _engine


def get_engine():
    return _get_engine()


def create_tables() -> None:
    engine = _get_engine()
    SQLModel.metadata.create_all(engine)
    _migrate(engine)


def _migrate(engine) -> None:
    with engine.connect() as conn:
        existing = {
            row[1] for row in conn.exec_driver_sql("PRAGMA table_info(library)")
        }
        if "is_excluded" not in existing:
            conn.exec_driver_sql(
                "ALTER TABLE library ADD COLUMN is_excluded BOOLEAN NOT NULL DEFAULT 0"
            )
            conn.commit()


def get_session() -> Generator[Session]:
    with Session(_get_engine()) as session:
        yield session
