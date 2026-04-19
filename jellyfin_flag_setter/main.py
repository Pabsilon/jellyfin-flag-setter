import asyncio
import logging
import secrets
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager

from fastapi import Depends, FastAPI, Form, Query, Request
from fastapi.responses import RedirectResponse, Response
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from sqlmodel import Session
from starlette.middleware.sessions import SessionMiddleware

from jellyfin_flag_setter.auth.db import create_tables, get_engine
from jellyfin_flag_setter.auth.dependencies import (
    RequiresLogin,
    RequiresSetup,
    get_current_user,
)
from jellyfin_flag_setter.auth.models import User
from jellyfin_flag_setter.auth.router import router as auth_router
from jellyfin_flag_setter.config import settings
from jellyfin_flag_setter.flags.composer import compose_flags, is_edited, mark_as_edited
from jellyfin_flag_setter.flags.mapping import (
    ALL_FLAGS,
    KNOWN_FLAGS,
    languages_to_flags,
)
from jellyfin_flag_setter.jellyfin.client import JellyfinClient
from jellyfin_flag_setter.jellyfin.models import MovieItem
from jellyfin_flag_setter.sync.models import LibraryWithItems
from jellyfin_flag_setter.sync.store import (
    load_libraries,
    mark_item_edited,
    save_libraries,
)

_LIBRARY_REFRESH_INTERVAL = 3600  # seconds
logger = logging.getLogger(__name__)


_COLLECTION_TYPE_MAP = {
    "movies": "Movie",
    "tvshows": "Series",
}


async def _load_libraries(client: JellyfinClient) -> list[LibraryWithItems]:
    libraries = await client.get_libraries()
    items_per_library = await asyncio.gather(
        *(
            client.get_library_items(
                lib.id, _COLLECTION_TYPE_MAP.get(lib.collection_type or "", "Movie")
            )
            for lib in libraries
        )
    )
    return [
        LibraryWithItems(
            id=lib.id, name=lib.name, collection_type=lib.collection_type, items=items
        )
        for lib, items in zip(libraries, items_per_library)
    ]


_POSTER_CHECK_CONCURRENCY = 10


def _apply_edited_map(
    libraries: list[LibraryWithItems], edited_map: dict[str, bool]
) -> None:
    for lib in libraries:
        lib_ids = {i.id for i in lib.items}
        lib.edited_item_ids = {k for k, v in edited_map.items() if v and k in lib_ids}


async def _check_all_posters(
    client: JellyfinClient, libraries: list[LibraryWithItems]
) -> dict[str, bool]:
    """Fetch all posters and return a map of item_id → is_edited."""
    all_items = [item for lib in libraries for item in lib.items]
    semaphore = asyncio.Semaphore(_POSTER_CHECK_CONCURRENCY)

    async def check(item) -> tuple[str, bool]:
        async with semaphore:
            poster = await client.get_poster(item.id)
            return item.id, is_edited(poster)

    results = await asyncio.gather(
        *[check(item) for item in all_items], return_exceptions=True
    )
    edited_map = {}
    for result in results:
        if isinstance(result, BaseException):
            logger.warning("Failed to check poster: %s", result)
        else:
            item_id, edited = result
            edited_map[item_id] = edited
    return edited_map


async def _refresh_loop(app: FastAPI) -> None:
    while True:
        await asyncio.sleep(_LIBRARY_REFRESH_INTERVAL)
        try:
            libraries = await _load_libraries(app.state.jellyfin)
            edited_map = await _check_all_posters(app.state.jellyfin, libraries)
            _apply_edited_map(libraries, edited_map)
            with Session(get_engine()) as session:
                save_libraries(session, libraries)
            app.state.libraries = libraries
            total = sum(len(lib.items) for lib in libraries)
            logger.info(
                "Refreshed libraries (%d items across %d libraries)",
                total,
                len(libraries),
            )
        except Exception:
            logger.exception("Failed to refresh libraries")


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None]:
    create_tables()
    app.state.jellyfin = JellyfinClient()
    with Session(get_engine()) as session:
        libraries = load_libraries(session)
    if libraries:
        total = sum(len(lib.items) for lib in libraries)
        logger.info(
            "Loaded %d items from DB across %d libraries", total, len(libraries)
        )
    else:
        libraries = await _load_libraries(app.state.jellyfin)
        edited_map = await _check_all_posters(app.state.jellyfin, libraries)
        _apply_edited_map(libraries, edited_map)
        with Session(get_engine()) as session:
            save_libraries(session, libraries)
        total = sum(len(lib.items) for lib in libraries)
        logger.info(
            "Synced %d items from Jellyfin across %d libraries", total, len(libraries)
        )
    app.state.libraries = libraries
    refresh_task = asyncio.create_task(_refresh_loop(app))
    yield
    refresh_task.cancel()
    await app.state.jellyfin.aclose()


app = FastAPI(title="Jellyfin Flag Setter", lifespan=lifespan)


def serve() -> None:
    import uvicorn

    uvicorn.run("jellyfin_flag_setter.main:app", reload=True)


_secret_key = settings.secret_key or secrets.token_hex(32)
if not settings.secret_key:
    logger.warning("SECRET_KEY not set — sessions will not persist across restarts")
app.add_middleware(SessionMiddleware, secret_key=_secret_key)

app.mount("/static", StaticFiles(directory="static"), name="static")
app.include_router(auth_router)
templates = Jinja2Templates(directory="templates")


@app.exception_handler(RequiresLogin)
async def _requires_login(request: Request, exc: RequiresLogin):
    return RedirectResponse("/login", status_code=302)


@app.exception_handler(RequiresSetup)
async def _requires_setup(request: Request, exc: RequiresSetup):
    return RedirectResponse("/setup", status_code=302)


def _get_client(request: Request) -> JellyfinClient:
    return request.app.state.jellyfin


def _get_libraries(request: Request) -> list[LibraryWithItems]:
    return request.app.state.libraries


def _get_movies(request: Request) -> list[MovieItem]:
    return [item for lib in _get_libraries(request) for item in lib.items]


def _audio_languages(movie) -> list[str]:
    return [s.language for s in movie.media_streams if s.type == "Audio" and s.language]


@app.get("/")
async def index(request: Request, current_user: User = Depends(get_current_user)):
    return templates.TemplateResponse(
        request,
        "index.html",
        {"libraries": _get_libraries(request), "user": current_user},
    )


@app.get("/library/{library_id}")
async def library_view(
    request: Request, library_id: str, current_user: User = Depends(get_current_user)
):
    library = next(
        (lib for lib in _get_libraries(request) if lib.id == library_id), None
    )
    if library is None:
        return RedirectResponse("/", status_code=302)
    unedited = [i for i in library.items if i.id not in library.edited_item_ids]
    edited = [i for i in library.items if i.id in library.edited_item_ids]
    return templates.TemplateResponse(
        request,
        "library.html",
        {
            "library": library,
            "unedited": unedited,
            "edited": edited,
            "user": current_user,
        },
    )


@app.get("/movie/{item_id}")
async def movie_preview(
    request: Request, item_id: str, current_user: User = Depends(get_current_user)
):
    client = _get_client(request)
    movie, poster = await asyncio.gather(
        client.get_movie(item_id),
        client.get_poster(item_id),
    )
    ids = [m.id for m in _get_movies(request)]
    try:
        idx = ids.index(item_id)
        next_id = ids[idx + 1] if idx + 1 < len(ids) else None
    except ValueError:
        next_id = None

    audio_streams = [s for s in movie.media_streams if s.type == "Audio"]
    proposed_flags = languages_to_flags(_audio_languages(movie))
    preview_qs = "&".join(f"flags={f}" for f in proposed_flags)
    return templates.TemplateResponse(
        request,
        "preview.html",
        {
            "movie": movie,
            "audio_streams": audio_streams,
            "proposed_flags": proposed_flags,
            "known_flags": KNOWN_FLAGS,
            "all_flags": ALL_FLAGS,
            "preview_qs": preview_qs,
            "next_id": next_id,
            "already_edited": is_edited(poster),
            "user": current_user,
        },
    )


@app.get("/movie/{item_id}/poster/original")
async def poster_original(
    item_id: str, request: Request, _: User = Depends(get_current_user)
):
    data = await _get_client(request).get_poster(item_id)
    return Response(content=data, media_type="image/jpeg")


@app.get("/movie/{item_id}/poster/preview")
async def poster_preview(
    item_id: str,
    request: Request,
    flags: list[str] = Query(default=[]),
    _: User = Depends(get_current_user),
):
    poster = await _get_client(request).get_poster(item_id)
    composed = compose_flags(poster, flags)
    return Response(content=composed, media_type="image/jpeg")


@app.post("/movie/{item_id}/apply")
async def apply_flags(
    item_id: str,
    request: Request,
    flags: list[str] = Form(default=[]),
    next_id: str | None = Form(default=None),
    _: User = Depends(get_current_user),
):
    client = _get_client(request)
    poster = await client.get_poster(item_id)
    composed = mark_as_edited(compose_flags(poster, flags))
    await client.upload_poster(item_id, composed)
    with Session(get_engine()) as session:
        mark_item_edited(session, item_id)
    for lib in _get_libraries(request):
        if any(item.id == item_id for item in lib.items):
            lib.edited_item_ids.add(item_id)
            break
    redirect_url = f"/movie/{next_id}" if next_id else "/"
    return RedirectResponse(url=redirect_url, status_code=303)
