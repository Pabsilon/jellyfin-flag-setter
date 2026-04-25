import asyncio
import logging
import secrets
import time
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager

from fastapi import Depends, FastAPI, Form, Query, Request
from fastapi.responses import JSONResponse, RedirectResponse, Response
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from sqlmodel import Session, select
from starlette.middleware.sessions import SessionMiddleware

from jellyfin_flag_setter.auth.db import create_tables, get_engine
from jellyfin_flag_setter.auth.dependencies import (
    RequiresJellyfinSetup,
    RequiresLogin,
    RequiresSetup,
    get_current_user,
)
from jellyfin_flag_setter.auth.models import ServerConfig, User
from jellyfin_flag_setter.auth.router import router as auth_router
from jellyfin_flag_setter.config import settings
from jellyfin_flag_setter.flags.composer import compose_flags, is_edited, mark_as_edited
from jellyfin_flag_setter.flags.mapping import (
    ALL_FLAGS,
    KNOWN_FLAGS,
    LANGUAGE_TO_FLAG,
    languages_to_flags,
)
from jellyfin_flag_setter.jellyfin.client import JellyfinClient
from jellyfin_flag_setter.jellyfin.models import MovieItem
from jellyfin_flag_setter.jobs.router import router as jobs_router
from jellyfin_flag_setter.jobs.runner import JobManager
from jellyfin_flag_setter.sync.models import LibraryWithItems
from jellyfin_flag_setter.sync.store import (
    load_libraries,
    mark_item_edited,
    mark_item_unedited,
    save_libraries,
    set_library_excluded,
    upsert_items,
)

logging.basicConfig(level=logging.INFO, format="%(levelname)s:%(name)s:%(message)s")

_LIBRARY_REFRESH_DEFAULT_INTERVAL = 86400  # seconds
_RECENT_SYNC_DEFAULT_INTERVAL = 900  # seconds
logger = logging.getLogger(__name__)


_COLLECTION_TYPE_MAP = {
    "movies": "Movie",
    "tvshows": "Series",
}


async def _load_libraries(
    client: JellyfinClient, excluded_ids: set[str] | frozenset[str] = frozenset()
) -> list[LibraryWithItems]:
    libraries = await client.get_libraries()
    active = [lib for lib in libraries if lib.id not in excluded_ids]
    items_per_library = await asyncio.gather(
        *(
            client.get_library_items(
                lib.id, _COLLECTION_TYPE_MAP.get(lib.collection_type or "", "Movie")
            )
            for lib in active
        )
    )
    active_items = {lib.id: items for lib, items in zip(active, items_per_library)}
    return [
        LibraryWithItems(
            id=lib.id,
            name=lib.name,
            collection_type=lib.collection_type,
            items=active_items.get(lib.id, []),
            is_excluded=lib.id in excluded_ids,
        )
        for lib in libraries
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


async def _sync_recent(app: FastAPI) -> None:
    libraries = [lib for lib in app.state.libraries if not lib.is_excluded]
    new_per_lib = []
    for lib in libraries:
        try:
            t0 = time.monotonic()
            recent = await app.state.jellyfin.get_recently_added(
                lib.id,
                _COLLECTION_TYPE_MAP.get(lib.collection_type or "", "Movie"),
                limit=5,
            )
            logger.info(
                "Recent sync: get_recently_added [%s] took %.2fs",
                lib.name,
                time.monotonic() - t0,
            )
        except Exception as e:
            logger.warning("Recent sync: skipping library %s: %s", lib.name, e)
            continue
        new_items = [i for i in recent if i.id not in {x.id for x in lib.items}]
        if not new_items:
            continue
        if lib.collection_type == "movies":
            try:
                t0 = time.monotonic()
                new_items = await app.state.jellyfin.get_items_by_ids(
                    [i.id for i in new_items]
                )
                logger.info(
                    "Recent sync: get_items_by_ids [%s] (%d items) took %.2fs",
                    lib.name,
                    len(new_items),
                    time.monotonic() - t0,
                )
            except Exception as e:
                logger.warning(
                    "Recent sync: failed to fetch items for %s: %s", lib.name, e
                )
                continue
        new_per_lib.append((lib, new_items))
    all_new = [(lib, item) for lib, items in new_per_lib for item in items]
    if not all_new:
        logger.info("Recent sync: no new items")
        return

    temp_lib = LibraryWithItems(
        id="", name="", collection_type=None, items=[i for _, i in all_new]
    )
    t0 = time.monotonic()
    edited_map = await _check_all_posters(app.state.jellyfin, [temp_lib])
    logger.info(
        "Recent sync: _check_all_posters (%d items) took %.2fs",
        len(all_new),
        time.monotonic() - t0,
    )

    with Session(get_engine()) as session:
        for lib, items in new_per_lib:
            if items:
                upsert_items(session, lib.id, items, edited_map)

    for lib, item in all_new:
        lib.items.append(item)
        if edited_map.get(item.id):
            lib.edited_item_ids.add(item.id)

    logger.info("Recent sync: added %d new items", len(all_new))


async def _sync_libraries(app: FastAPI) -> None:
    excluded_ids = {lib.id for lib in app.state.libraries if lib.is_excluded}
    libraries = await _load_libraries(app.state.jellyfin, excluded_ids)
    active = [lib for lib in libraries if not lib.is_excluded]
    edited_map = await _check_all_posters(app.state.jellyfin, active)
    _apply_edited_map(active, edited_map)
    with Session(get_engine()) as session:
        save_libraries(session, libraries)
    app.state.libraries = libraries
    total = sum(len(lib.items) for lib in libraries)
    logger.info(
        "Refreshed libraries (%d items across %d libraries)",
        total,
        len(libraries),
    )


async def _init_jellyfin(app: FastAPI, config: ServerConfig) -> None:
    client = JellyfinClient(config.jellyfin_url, config.jellyfin_api_key)
    app.state.jellyfin = client

    with Session(get_engine()) as session:
        libraries = load_libraries(session)
    if libraries:
        total = sum(len(lib.items) for lib in libraries)
        logger.info(
            "Loaded %d items from DB across %d libraries", total, len(libraries)
        )
    else:
        libraries = await _load_libraries(client)
        edited_map = await _check_all_posters(client, libraries)
        _apply_edited_map(libraries, edited_map)
        with Session(get_engine()) as session:
            save_libraries(session, libraries)
        total = sum(len(lib.items) for lib in libraries)
        logger.info(
            "Synced %d items from Jellyfin across %d libraries", total, len(libraries)
        )
    app.state.libraries = libraries

    job_manager: JobManager = app.state.job_manager
    job_manager.register_and_start(
        "library_sync",
        "Library Sync",
        lambda: _sync_libraries(app),
        default_interval=_LIBRARY_REFRESH_DEFAULT_INTERVAL,
        time_unit="hours",
    )
    job_manager.register_and_start(
        "recent_sync",
        "Recent Sync",
        lambda: _sync_recent(app),
        default_interval=_RECENT_SYNC_DEFAULT_INTERVAL,
    )


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None]:
    create_tables()
    app.state.jellyfin = None
    app.state.libraries = []

    job_manager = JobManager()
    app.state.job_manager = job_manager
    job_manager.start(get_engine())

    with Session(get_engine()) as session:
        server_config = session.exec(select(ServerConfig)).first()

    if server_config:
        await _init_jellyfin(app, server_config)

    yield

    await job_manager.stop()
    if app.state.jellyfin:
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
app.include_router(jobs_router)
templates = Jinja2Templates(directory="templates")


@app.get("/setup/jellyfin")
async def setup_jellyfin_page(request: Request):
    if not request.session.get("user_id"):
        return RedirectResponse("/login", status_code=302)
    with Session(get_engine()) as session:
        if session.exec(select(ServerConfig)).first():
            return RedirectResponse("/", status_code=302)
    return templates.TemplateResponse(request, "setup_jellyfin.html", {"error": None})


@app.post("/setup/jellyfin")
async def setup_jellyfin(
    request: Request,
    jellyfin_url: str = Form(),
    jellyfin_api_key: str = Form(),
):
    if not request.session.get("user_id"):
        return RedirectResponse("/login", status_code=302)
    with Session(get_engine()) as session:
        if session.exec(select(ServerConfig)).first():
            return RedirectResponse("/", status_code=302)

    url = jellyfin_url.rstrip("/")
    test_client = JellyfinClient(url, jellyfin_api_key)
    try:
        await test_client.get_libraries()
    except Exception as e:
        await test_client.aclose()
        return templates.TemplateResponse(
            request,
            "setup_jellyfin.html",
            {"error": f"Could not connect to Jellyfin: {e}"},
            status_code=400,
        )
    await test_client.aclose()

    with Session(get_engine()) as session:
        config = ServerConfig(jellyfin_url=url, jellyfin_api_key=jellyfin_api_key)
        session.add(config)
        session.commit()
        session.refresh(config)

    await _init_jellyfin(request.app, config)
    return RedirectResponse("/", status_code=303)


@app.post("/api/libraries/{library_id}/excluded")
async def set_excluded(
    library_id: str,
    request: Request,
    excluded: bool = Form(),
    _: User = Depends(get_current_user),
):
    with Session(get_engine()) as session:
        found = set_library_excluded(session, library_id, excluded)
    if not found:
        return JSONResponse({"error": "unknown library"}, status_code=404)
    for lib in request.app.state.libraries:
        if lib.id == library_id:
            lib.is_excluded = excluded
            break
    return JSONResponse({"ok": True})


@app.exception_handler(RequiresLogin)
async def _requires_login(request: Request, exc: RequiresLogin):
    return RedirectResponse("/login", status_code=302)


@app.exception_handler(RequiresSetup)
async def _requires_setup(request: Request, exc: RequiresSetup):
    return RedirectResponse("/setup", status_code=302)


@app.exception_handler(RequiresJellyfinSetup)
async def _requires_jellyfin_setup(request: Request, exc: RequiresJellyfinSetup):
    return RedirectResponse("/setup/jellyfin", status_code=302)


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
        {
            "libraries": [
                lib for lib in _get_libraries(request) if not lib.is_excluded
            ],
            "user": current_user,
        },
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


@app.get("/library/{library_id}/done")
async def library_done(
    request: Request,
    library_id: str,
    current_user: User = Depends(get_current_user),
):
    library = next(
        (lib for lib in _get_libraries(request) if lib.id == library_id), None
    )
    if library is None:
        return RedirectResponse("/", status_code=302)
    return templates.TemplateResponse(
        request,
        "library_done.html",
        {"library": library, "user": current_user},
    )


@app.get("/movie/{item_id}")
async def movie_preview(
    request: Request,
    item_id: str,
    back: str = "/",
    current_user: User = Depends(get_current_user),
):
    client = _get_client(request)
    movie, poster = await asyncio.gather(
        client.get_movie(item_id),
        client.get_poster(item_id),
    )
    library = next(
        (
            lib
            for lib in _get_libraries(request)
            if any(item.id == item_id for item in lib.items)
        ),
        None,
    )
    if library:
        lib_ids = [m.id for m in library.items]
        try:
            idx = lib_ids.index(item_id)
            next_id = lib_ids[idx + 1] if idx + 1 < len(lib_ids) else None
        except ValueError:
            next_id = None
    else:
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
            "library": library,
            "already_edited": is_edited(poster),
            "back": back,
            "user": current_user,
        },
    )


@app.get("/movie/{item_id}/poster/original")
async def poster_original(
    item_id: str, request: Request, _: User = Depends(get_current_user)
):
    data = await _get_client(request).get_poster(item_id)
    edited = is_edited(data)
    for lib in _get_libraries(request):
        if any(item.id == item_id for item in lib.items):
            was_edited = item_id in lib.edited_item_ids
            if edited != was_edited:
                lib.edited_item_ids.add(
                    item_id
                ) if edited else lib.edited_item_ids.discard(item_id)
                with Session(get_engine()) as session:
                    mark_item_edited(
                        session, item_id
                    ) if edited else mark_item_unedited(session, item_id)
            break
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
    library_id: str | None = Form(default=None),
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
    if next_id:
        redirect_url = f"/movie/{next_id}"
    elif library_id:
        redirect_url = f"/library/{library_id}/done"
    else:
        redirect_url = "/"
    return RedirectResponse(url=redirect_url, status_code=303)


@app.get("/api/show/{item_id}/language-analysis")
async def show_language_analysis(
    item_id: str,
    request: Request,
    _: User = Depends(get_current_user),
) -> JSONResponse:
    from collections import Counter

    episodes = await _get_client(request).get_series_episodes(item_id)
    if not episodes:
        return JSONResponse([])

    lang_counts: Counter[str] = Counter()
    for ep in episodes:
        ep_langs = {
            s.language for s in ep.media_streams if s.type == "Audio" and s.language
        }
        lang_counts.update(ep_langs)

    total = len(episodes)
    results = [
        {
            "language": lang,
            "flag": LANGUAGE_TO_FLAG.get(lang),
            "count": count,
            "pct": round(count / total * 100),
        }
        for lang, count in lang_counts.most_common(3)
    ]
    return JSONResponse(results)


@app.get("/show/{item_id}")
async def show_preview(
    request: Request,
    item_id: str,
    back: str = "/",
    current_user: User = Depends(get_current_user),
):
    client = _get_client(request)
    show, poster = await asyncio.gather(
        client.get_movie(item_id),
        client.get_poster(item_id),
    )
    library = next(
        (
            lib
            for lib in _get_libraries(request)
            if any(item.id == item_id for item in lib.items)
        ),
        None,
    )
    if library:
        lib_ids = [m.id for m in library.items]
        try:
            idx = lib_ids.index(item_id)
            next_id = lib_ids[idx + 1] if idx + 1 < len(lib_ids) else None
        except ValueError:
            next_id = None
    else:
        next_id = None

    return templates.TemplateResponse(
        request,
        "show_preview.html",
        {
            "show": show,
            "known_flags": KNOWN_FLAGS,
            "all_flags": ALL_FLAGS,
            "next_id": next_id,
            "library": library,
            "already_edited": is_edited(poster),
            "back": back,
            "user": current_user,
        },
    )


@app.get("/show/{item_id}/poster/original")
async def show_poster_original(
    item_id: str, request: Request, _: User = Depends(get_current_user)
):
    data = await _get_client(request).get_poster(item_id)
    edited = is_edited(data)
    for lib in _get_libraries(request):
        if any(item.id == item_id for item in lib.items):
            was_edited = item_id in lib.edited_item_ids
            if edited != was_edited:
                lib.edited_item_ids.add(
                    item_id
                ) if edited else lib.edited_item_ids.discard(item_id)
                with Session(get_engine()) as session:
                    mark_item_edited(
                        session, item_id
                    ) if edited else mark_item_unedited(session, item_id)
            break
    return Response(content=data, media_type="image/jpeg")


@app.get("/show/{item_id}/poster/preview")
async def show_poster_preview(
    item_id: str,
    request: Request,
    flags: list[str] = Query(default=[]),
    _: User = Depends(get_current_user),
):
    poster = await _get_client(request).get_poster(item_id)
    composed = compose_flags(poster, flags)
    return Response(content=composed, media_type="image/jpeg")


@app.post("/show/{item_id}/apply")
async def show_apply_flags(
    item_id: str,
    request: Request,
    flags: list[str] = Form(default=[]),
    next_id: str | None = Form(default=None),
    library_id: str | None = Form(default=None),
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
    if next_id:
        redirect_url = f"/show/{next_id}"
    elif library_id:
        redirect_url = f"/library/{library_id}/done"
    else:
        redirect_url = "/"
    return RedirectResponse(url=redirect_url, status_code=303)
