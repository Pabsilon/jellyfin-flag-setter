import httpx
import pytest
import respx
from starlette.testclient import TestClient

from jellyfin_flag_setter.main import app
from tests.conftest import _SETUP_DATA, FAKE_MOVIE, TINY_JPEG, setup_base_routes


@pytest.fixture
def auth_client_poster_404():
    calls = 0

    def poster_side_effect(request: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        if calls == 1:
            return httpx.Response(
                200, content=TINY_JPEG, headers={"Content-Type": "image/jpeg"}
            )
        return httpx.Response(404)

    with respx.mock(base_url="http://fake-jellyfin", assert_all_called=False) as router:
        setup_base_routes(router)
        router.get("/Items/movie1").respond(json=FAKE_MOVIE)
        router.get("/Items/movie1/Images/Primary").mock(side_effect=poster_side_effect)
        with TestClient(app, raise_server_exceptions=False) as c:
            c.post("/setup", data=_SETUP_DATA)
            yield c


@pytest.fixture
def auth_client_movie_404():
    with respx.mock(base_url="http://fake-jellyfin", assert_all_called=False) as router:
        setup_base_routes(router)
        router.get("/Items/movie1").respond(status_code=404)
        router.get("/Items/movie1/Images/Primary").respond(
            content=TINY_JPEG, headers={"Content-Type": "image/jpeg"}
        )
        with TestClient(app, raise_server_exceptions=False) as c:
            c.post("/setup", data=_SETUP_DATA)
            yield c


def test_poster_original_404(auth_client_poster_404: TestClient):
    response = auth_client_poster_404.get("/movie/movie1/poster/original")
    assert response.status_code == 500


def test_poster_preview_404(auth_client_poster_404: TestClient):
    response = auth_client_poster_404.get("/movie/movie1/poster/preview?flags=gb")
    assert response.status_code == 500


def test_poster_apply_404(auth_client_poster_404: TestClient):
    response = auth_client_poster_404.post(
        "/movie/movie1/apply", data={"flags": ["gb"]}
    )
    assert response.status_code == 500


def test_movie_details_404(auth_client_movie_404: TestClient):
    response = auth_client_movie_404.get("/movie/movie1")
    assert response.status_code == 500
