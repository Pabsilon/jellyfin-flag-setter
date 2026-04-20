import pytest
from starlette.testclient import TestClient

PROTECTED_GET_ROUTES = [
    "/",
    "/movie/movie1",
    "/movie/movie1/poster/original",
    "/movie/movie1/poster/preview",
    "/settings",
    "/api/jobs",
    "/api/jobs/library_sync",
]

PROTECTED_POST_ROUTES = [
    ("/movie/movie1/apply", {}),
    ("/settings/password", {}),
    ("/api/jobs/library_sync/run", {}),
    ("/api/jobs/library_sync/interval", {"interval_minutes": "60"}),
]


@pytest.mark.parametrize("path", PROTECTED_GET_ROUTES)
def test_get_requires_auth(client: TestClient, path: str):
    response = client.get(path, follow_redirects=False)
    assert response.status_code == 302
    assert response.headers["location"] in ("/login", "/setup")


@pytest.mark.parametrize("path,data", PROTECTED_POST_ROUTES)
def test_post_requires_auth(client: TestClient, path: str, data: dict):
    response = client.post(path, data=data, follow_redirects=False)
    assert response.status_code == 302
    assert response.headers["location"] in ("/login", "/setup")
