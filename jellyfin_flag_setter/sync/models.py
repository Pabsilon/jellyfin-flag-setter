from dataclasses import dataclass, field
from datetime import datetime

from sqlmodel import Field, SQLModel

from jellyfin_flag_setter.jellyfin.models import MovieItem


class DBLibrary(SQLModel, table=True):
    __tablename__ = "library"

    id: str = Field(primary_key=True)
    name: str
    collection_type: str | None = None
    last_full_sync_at: datetime | None = None
    last_recent_sync_at: datetime | None = None
    is_excluded: bool = False


class DBMediaItem(SQLModel, table=True):
    __tablename__ = "media_item"

    id: str = Field(primary_key=True)
    library_id: str = Field(foreign_key="library.id", index=True)
    name: str
    production_year: int | None = None
    is_edited: bool = False


class DBMediaStream(SQLModel, table=True):
    __tablename__ = "media_stream"

    id: int | None = Field(default=None, primary_key=True)
    item_id: str = Field(foreign_key="media_item.id", index=True)
    type: str
    language: str | None = None
    display_title: str | None = None
    codec: str | None = None


class DBLanguageMapping(SQLModel, table=True):
    __tablename__ = "language_mapping"

    position: int = Field(primary_key=True)
    language_code: str  # ISO 639-2, e.g. "eng"
    flag_code: str  # ISO 3166-1 alpha-2, e.g. "gb"


@dataclass
class LibraryWithItems:
    id: str
    name: str
    collection_type: str | None
    items: list[MovieItem] = field(default_factory=list)
    edited_item_ids: set[str] = field(default_factory=set)
    is_excluded: bool = False
