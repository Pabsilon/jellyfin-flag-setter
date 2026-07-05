import pytest
import respx
from conftest import TINY_JPEG
from starlette.testclient import TestClient

from jellyfin_flag_setter.main import app

_SETUP_DATA = {
    "username": "navuser",
    "password": "navpass123",
    "password_confirm": "navpass123",
}
_JELLYFIN_DATA = {
    "jellyfin_url": "http://fake-jellyfin",
    "jellyfin_api_key": "test-api-key",
}

_MEDIA_STREAM = [
    {"Type": "Audio", "Language": "eng", "DisplayTitle": "English", "Codec": "aac"}
]

MOVIES = [
    {
        "Id": "m1",
        "Name": "Alpha",
        "ProductionYear": 2021,
        "MediaStreams": _MEDIA_STREAM,
    },
    {"Id": "m2", "Name": "Beta", "ProductionYear": 2022, "MediaStreams": _MEDIA_STREAM},
    {
        "Id": "m3",
        "Name": "Gamma",
        "ProductionYear": 2023,
        "MediaStreams": _MEDIA_STREAM,
    },
]

SHOWS = [
    {
        "Id": "s1",
        "Name": "Show Alpha",
        "ProductionYear": 2021,
        "MediaStreams": _MEDIA_STREAM,
    },
    {
        "Id": "s2",
        "Name": "Show Beta",
        "ProductionYear": 2022,
        "MediaStreams": _MEDIA_STREAM,
    },
    {
        "Id": "s3",
        "Name": "Show Gamma",
        "ProductionYear": 2023,
        "MediaStreams": _MEDIA_STREAM,
    },
]


def _setup_jellyfin_routes(router, items, collection_type, library_id):
    router.get("/Users").respond(json=[{"Id": "user1", "Name": "TestUser"}])
    router.get("/Users/user1/Views").respond(
        json={
            "Items": [
                {"Id": library_id, "Name": "Lib", "CollectionType": collection_type}
            ],
            "TotalRecordCount": 1,
        }
    )
    router.get("/Items").respond(json={"Items": items, "TotalRecordCount": len(items)})
    router.get("/Users/user1/Items/Latest").respond(json=[])
    for item in items:
        iid = item["Id"]
        router.get(f"/Items/{iid}").respond(json=item)
        router.get(f"/Items/{iid}/Images/Primary").respond(
            content=TINY_JPEG, headers={"Content-Type": "image/jpeg"}
        )
        router.post(f"/Items/{iid}/Images/Primary").respond(status_code=204)


@pytest.fixture
def movie_client():
    """Auth client with 3 movies, all initially unedited."""
    with respx.mock(base_url="http://fake-jellyfin", assert_all_called=False) as router:
        _setup_jellyfin_routes(router, MOVIES, "movies", "lib_movies")
        with TestClient(app, raise_server_exceptions=False) as c:
            c.post("/setup", data=_SETUP_DATA)
            c.post("/setup/jellyfin", data=_JELLYFIN_DATA)
            yield c


@pytest.fixture
def show_client():
    """Auth client with 3 shows, all initially unedited."""
    with respx.mock(base_url="http://fake-jellyfin", assert_all_called=False) as router:
        _setup_jellyfin_routes(router, SHOWS, "tvshows", "lib_shows")
        with TestClient(app, raise_server_exceptions=False) as c:
            c.post("/setup", data=_SETUP_DATA)
            c.post("/setup/jellyfin", data=_JELLYFIN_DATA)
            yield c


def _lib(library_id: str):
    return next(lib for lib in app.state.libraries if lib.id == library_id)


# --- movie tests ---


def test_movie_next_id_skips_edited(movie_client):
    _lib("lib_movies").edited_item_ids.add("m2")

    resp = movie_client.get("/movie/m1")

    assert resp.status_code == 200
    assert b'value="m3"' in resp.content


def test_movie_next_id_is_none_when_all_remaining_edited(movie_client):
    _lib("lib_movies").edited_item_ids.update({"m2", "m3"})

    resp = movie_client.get("/movie/m1")

    assert resp.status_code == 200
    assert b'name="next_id"' not in resp.content


def test_movie_next_id_for_last_unedited_item(movie_client):
    _lib("lib_movies").edited_item_ids.update({"m1", "m2"})

    resp = movie_client.get("/movie/m3")

    assert resp.status_code == 200
    assert b'name="next_id"' not in resp.content


def test_movie_next_id_points_to_immediate_successor_when_unedited(movie_client):
    resp = movie_client.get("/movie/m1")

    assert resp.status_code == 200
    assert b'value="m2"' in resp.content


def test_movie_next_id_wraps_around_when_last_item_edited_first(movie_client):
    """Editing the last item first should surface earlier unedited items, not "done"."""
    resp = movie_client.get("/movie/m3")

    assert resp.status_code == 200
    assert b'value="m1"' in resp.content


# --- show tests ---


def test_show_next_id_skips_edited(show_client):
    _lib("lib_shows").edited_item_ids.add("s2")

    resp = show_client.get("/show/s1")

    assert resp.status_code == 200
    assert b'value="s3"' in resp.content


def test_show_next_id_is_none_when_all_remaining_edited(show_client):
    _lib("lib_shows").edited_item_ids.update({"s2", "s3"})

    resp = show_client.get("/show/s1")

    assert resp.status_code == 200
    assert b'name="next_id"' not in resp.content


def test_show_next_id_wraps_around_when_last_item_edited_first(show_client):
    resp = show_client.get("/show/s3")

    assert resp.status_code == 200
    assert b'value="s1"' in resp.content
