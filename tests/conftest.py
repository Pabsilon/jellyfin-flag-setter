import os

os.environ.setdefault("SECRET_KEY", "test-secret-key-32chars-xxxxxxxxxxx")

import pytest
import respx
from starlette.testclient import TestClient

from jellyfin_flag_setter.main import app


def _make_tiny_jpeg() -> bytes:
    from wand.color import Color
    from wand.image import Image

    with Image(width=100, height=150, background=Color("white")) as img:
        img.format = "jpeg"
        return img.make_blob()


TINY_JPEG: bytes = _make_tiny_jpeg()

FAKE_MOVIE = {
    "Id": "movie1",
    "Name": "Test Movie",
    "ProductionYear": 2021,
    "MediaStreams": [
        {
            "Type": "Audio",
            "Language": "eng",
            "DisplayTitle": "English",
            "Codec": "aac",
        }
    ],
}

_SETUP_DATA = {
    "username": "testuser",
    "password": "testpass123",
    "password_confirm": "testpass123",
}


def setup_base_routes(router: respx.MockRouter) -> None:
    """Register all Jellyfin routes except the poster GET and movie details GET."""
    router.get("/Users").respond(json=[{"Id": "user1", "Name": "TestUser"}])
    router.get("/Users/user1/Views").respond(
        json={
            "Items": [{"Id": "lib1", "Name": "Movies", "CollectionType": "movies"}],
            "TotalRecordCount": 1,
        }
    )
    router.get("/Items").respond(json={"Items": [FAKE_MOVIE], "TotalRecordCount": 1})
    router.get("/Users/user1/Items/Latest").respond(json=[])
    router.post("/Items/movie1/Images/Primary").respond(status_code=204)


@pytest.fixture(autouse=True)
def _isolated_db(monkeypatch, tmp_path):
    import jellyfin_flag_setter.auth.db as db_module
    import jellyfin_flag_setter.config as config_module

    monkeypatch.setattr(config_module.settings, "db_path", str(tmp_path / "test.db"))
    monkeypatch.setattr(db_module, "_engine", None)
    yield
    monkeypatch.setattr(db_module, "_engine", None)


@pytest.fixture
def fake_jellyfin():
    with respx.mock(base_url="http://fake-jellyfin", assert_all_called=False) as router:
        setup_base_routes(router)
        router.get("/Items/movie1").respond(json=FAKE_MOVIE)
        router.get("/Items/movie1/Images/Primary").respond(
            content=TINY_JPEG, headers={"Content-Type": "image/jpeg"}
        )
        yield router


@pytest.fixture
def client(fake_jellyfin):
    with TestClient(app, raise_server_exceptions=False) as c:
        yield c


_JELLYFIN_DATA = {
    "jellyfin_url": "http://fake-jellyfin",
    "jellyfin_api_key": "test-api-key",
}


@pytest.fixture
def auth_client(fake_jellyfin):
    with TestClient(app, raise_server_exceptions=False) as c:
        c.post("/setup", data=_SETUP_DATA)
        c.post("/setup/jellyfin", data=_JELLYFIN_DATA)
        yield c
