from pydantic import BaseModel, ConfigDict
from pydantic.alias_generators import to_pascal


class MediaStream(BaseModel):
    model_config = ConfigDict(alias_generator=to_pascal, populate_by_name=True)

    type: str  # "Audio", "Subtitle", "Video"
    language: str | None = None
    display_title: str | None = None
    codec: str | None = None


class MovieItem(BaseModel):
    model_config = ConfigDict(alias_generator=to_pascal, populate_by_name=True)

    id: str
    name: str
    production_year: int | None = None
    media_streams: list[MediaStream] = []


class ItemsResponse(BaseModel):
    model_config = ConfigDict(alias_generator=to_pascal, populate_by_name=True)

    items: list[MovieItem]
    total_record_count: int


class LibraryItem(BaseModel):
    model_config = ConfigDict(alias_generator=to_pascal, populate_by_name=True)

    id: str
    name: str
    collection_type: str | None = None


class LibrariesResponse(BaseModel):
    model_config = ConfigDict(alias_generator=to_pascal, populate_by_name=True)

    items: list[LibraryItem]
