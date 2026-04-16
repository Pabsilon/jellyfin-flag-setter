import asyncio
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager

from fastapi import FastAPI, Form, Query, Request
from fastapi.responses import RedirectResponse, Response
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from jellyfin_flag_setter.flags.composer import compose_flags
from jellyfin_flag_setter.flags.mapping import (
    ALL_FLAGS,
    KNOWN_FLAGS,
    languages_to_flags,
)
from jellyfin_flag_setter.jellyfin.client import JellyfinClient


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None]:
    app.state.jellyfin = JellyfinClient()
    yield
    await app.state.jellyfin.aclose()


app = FastAPI(title="Jellyfin Flag Setter", lifespan=lifespan)
app.mount("/static", StaticFiles(directory="static"), name="static")
templates = Jinja2Templates(directory="templates")


def _get_client(request: Request) -> JellyfinClient:
    return request.app.state.jellyfin


def _audio_languages(movie) -> list[str]:
    return [s.language for s in movie.media_streams if s.type == "Audio" and s.language]


@app.get("/")
async def index(request: Request):
    movies = await _get_client(request).get_recent_movies()
    return templates.TemplateResponse(request, "index.html", {"movies": movies})


@app.get("/movie/{item_id}")
async def movie_preview(request: Request, item_id: str):
    client = _get_client(request)
    movie, all_movies = await asyncio.gather(
        client.get_movie(item_id),
        client.get_recent_movies(),
    )
    ids = [m.id for m in all_movies]
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
        },
    )


@app.get("/movie/{item_id}/poster/original")
async def poster_original(item_id: str, request: Request):
    data = await _get_client(request).get_poster(item_id)
    return Response(content=data, media_type="image/jpeg")


@app.get("/movie/{item_id}/poster/preview")
async def poster_preview(
    item_id: str, request: Request, flags: list[str] = Query(default=[])
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
):
    client = _get_client(request)
    poster = await client.get_poster(item_id)
    composed = compose_flags(poster, flags)
    await client.upload_poster(item_id, composed)
    redirect_url = f"/movie/{next_id}" if next_id else "/"
    return RedirectResponse(url=redirect_url, status_code=303)
