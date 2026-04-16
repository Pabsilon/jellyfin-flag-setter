from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from jellyfin_flag_setter.jellyfin.client import JellyfinClient


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None]:
    app.state.jellyfin = JellyfinClient()
    yield
    await app.state.jellyfin.aclose()


app = FastAPI(title="Jellyfin Flag Setter", lifespan=lifespan)
app.mount("/static", StaticFiles(directory="static"), name="static")
templates = Jinja2Templates(directory="templates")


@app.get("/")
async def index(request: Request):
    client: JellyfinClient = request.app.state.jellyfin
    movies = await client.get_recent_movies()
    return templates.TemplateResponse(request, "index.html", {"movies": movies})
