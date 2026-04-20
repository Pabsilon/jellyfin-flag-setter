from datetime import datetime

from sqlmodel import Field, SQLModel


class DBJobConfig(SQLModel, table=True):
    __tablename__ = "job_config"

    job_id: str = Field(primary_key=True)
    interval_seconds: int = Field(default=3600)
    last_run_at: datetime | None = None
