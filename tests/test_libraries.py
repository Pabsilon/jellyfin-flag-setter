from starlette.testclient import TestClient

from jellyfin_flag_setter.main import app


def test_exclude_library(auth_client: TestClient):
    resp = auth_client.post("/api/libraries/lib1/excluded", data={"excluded": "true"})
    assert resp.status_code == 200
    assert resp.json() == {"ok": True}
    lib = next(lib for lib in app.state.libraries if lib.id == "lib1")
    assert lib.is_excluded is True


def test_reinclude_library(auth_client: TestClient):
    auth_client.post("/api/libraries/lib1/excluded", data={"excluded": "true"})
    resp = auth_client.post("/api/libraries/lib1/excluded", data={"excluded": "false"})
    assert resp.status_code == 200
    lib = next(lib for lib in app.state.libraries if lib.id == "lib1")
    assert lib.is_excluded is False


def test_exclude_unknown_library_returns_404(auth_client: TestClient):
    resp = auth_client.post(
        "/api/libraries/doesnotexist/excluded", data={"excluded": "true"}
    )
    assert resp.status_code == 404
    assert resp.json() == {"error": "unknown library"}


def test_excluded_library_hidden_from_index(auth_client: TestClient):
    before = auth_client.get("/")
    assert b"Movies" in before.content

    auth_client.post("/api/libraries/lib1/excluded", data={"excluded": "true"})

    after = auth_client.get("/")
    assert b"Movies" not in after.content


def test_excluded_library_still_visible_in_settings(auth_client: TestClient):
    auth_client.post("/api/libraries/lib1/excluded", data={"excluded": "true"})
    resp = auth_client.get("/settings")
    assert resp.status_code == 200
    assert b"Movies" in resp.content
    assert b"Re-include" in resp.content


def test_settings_page_shows_all_libraries(auth_client: TestClient):
    resp = auth_client.get("/settings")
    assert resp.status_code == 200
    assert b"Movies" in resp.content
    assert b"Exclude" in resp.content


def test_exclusion_persists_in_db(auth_client: TestClient):
    auth_client.post("/api/libraries/lib1/excluded", data={"excluded": "true"})

    from sqlmodel import Session, select

    from jellyfin_flag_setter.auth.db import get_engine
    from jellyfin_flag_setter.sync.models import DBLibrary

    with Session(get_engine()) as session:
        db_lib = session.exec(select(DBLibrary).where(DBLibrary.id == "lib1")).first()
    assert db_lib is not None
    assert db_lib.is_excluded is True
