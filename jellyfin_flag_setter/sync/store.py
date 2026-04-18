from datetime import UTC, datetime

from sqlalchemy import delete
from sqlmodel import Session, select

from jellyfin_flag_setter.jellyfin.models import MediaStream, MovieItem

from .models import DBLibrary, DBMediaItem, DBMediaStream, LibraryWithItems


def load_libraries(session: Session) -> list[LibraryWithItems] | None:
    db_libraries = session.exec(select(DBLibrary)).all()
    if not db_libraries:
        return None
    result = []
    for lib in db_libraries:
        db_items = session.exec(
            select(DBMediaItem).where(DBMediaItem.library_id == lib.id)
        ).all()
        items = []
        for db_item in db_items:
            db_streams = session.exec(
                select(DBMediaStream).where(DBMediaStream.item_id == db_item.id)
            ).all()
            streams = [
                MediaStream(
                    type=s.type,
                    language=s.language,
                    display_title=s.display_title,
                    codec=s.codec,
                )
                for s in db_streams
            ]
            items.append(
                MovieItem(
                    id=db_item.id,
                    name=db_item.name,
                    production_year=db_item.production_year,
                    media_streams=streams,
                )
            )
        edited_ids = {row.id for row in db_items if row.is_edited}
        result.append(
            LibraryWithItems(
                id=lib.id,
                name=lib.name,
                collection_type=lib.collection_type,
                items=items,
                edited_item_ids=edited_ids,
            )
        )
    return result


def save_libraries(session: Session, libraries: list[LibraryWithItems]) -> None:
    sync_time = datetime.now(UTC)

    session.exec(delete(DBMediaStream))
    session.exec(delete(DBMediaItem))
    session.exec(delete(DBLibrary))

    for lib in libraries:
        session.add(
            DBLibrary(
                id=lib.id,
                name=lib.name,
                collection_type=lib.collection_type,
                last_full_sync_at=sync_time,
            )
        )
        for item in lib.items:
            session.add(
                DBMediaItem(
                    id=item.id,
                    library_id=lib.id,
                    name=item.name,
                    production_year=item.production_year,
                    is_edited=item.id in lib.edited_item_ids,
                )
            )
            for stream in item.media_streams:
                session.add(
                    DBMediaStream(
                        item_id=item.id,
                        type=stream.type,
                        language=stream.language,
                        display_title=stream.display_title,
                        codec=stream.codec,
                    )
                )

    session.commit()


def mark_item_edited(session: Session, item_id: str) -> None:
    item = session.get(DBMediaItem, item_id)
    if item:
        item.is_edited = True
        session.add(item)
        session.commit()


def update_edited_flags(session: Session, edited_map: dict[str, bool]) -> None:
    """Bulk-update is_edited from a poster scan pass."""
    for item_id, is_edited in edited_map.items():
        item = session.get(DBMediaItem, item_id)
        if item:
            item.is_edited = is_edited
            session.add(item)
    session.commit()
