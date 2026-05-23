from starlette.testclient import TestClient

from jellyfin_flag_setter.flags.mapping import languages_to_flags
from jellyfin_flag_setter.main import app
from jellyfin_flag_setter.sync.store import DEFAULT_LANGUAGE_MAPPINGS

# --- unit tests for languages_to_flags ---


def test_languages_to_flags_follows_mapping_order():
    mappings = [("eng", "gb"), ("spa", "es")]
    assert languages_to_flags(["spa", "eng"], mappings) == ["gb", "es"]


def test_languages_to_flags_first_entry_has_priority():
    mappings = [("spa", "es"), ("eng", "gb")]
    assert languages_to_flags(["spa", "eng"], mappings) == ["es", "gb"]


def test_languages_to_flags_skips_unmapped():
    mappings = [("eng", "gb")]
    assert languages_to_flags(["eng", "jpn"], mappings) == ["gb"]


def test_languages_to_flags_deduplicates_same_flag():
    mappings = [("eng", "gb"), ("epo", "gb")]
    assert languages_to_flags(["eng", "epo"], mappings) == ["gb"]


def test_languages_to_flags_empty_input():
    assert languages_to_flags([], [("eng", "gb")]) == []


def test_languages_to_flags_defaults_when_none():
    result = languages_to_flags(["eng", "spa"])
    assert "gb" in result
    assert "es" in result


# --- API tests ---


def test_get_languages_returns_defaults(auth_client: TestClient):
    resp = auth_client.get("/api/languages")
    assert resp.status_code == 200
    data = resp.json()
    codes = [entry["language_code"] for entry in data]
    flags = [entry["flag_code"] for entry in data]
    assert codes == [lc for lc, _ in DEFAULT_LANGUAGE_MAPPINGS]
    assert flags == [fc for _, fc in DEFAULT_LANGUAGE_MAPPINGS]


def test_add_language(auth_client: TestClient):
    resp = auth_client.post(
        "/api/languages", data={"language_code": "por", "flag_code": "pt"}
    )
    assert resp.status_code == 200
    assert resp.json() == {"ok": True, "language_code": "por", "flag_code": "pt"}

    mappings = app.state.language_mappings
    assert ("por", "pt") in mappings


def test_add_language_normalises_to_lowercase(auth_client: TestClient):
    resp = auth_client.post(
        "/api/languages", data={"language_code": "ITA", "flag_code": "IT"}
    )
    assert resp.status_code == 200
    assert ("ita", "it") in app.state.language_mappings


def test_add_duplicate_language_returns_400(auth_client: TestClient):
    auth_client.post("/api/languages", data={"language_code": "por", "flag_code": "pt"})
    resp = auth_client.post(
        "/api/languages", data={"language_code": "por", "flag_code": "pt"}
    )
    assert resp.status_code == 400
    assert "already mapped" in resp.json()["error"]


def test_add_unknown_flag_returns_400(auth_client: TestClient):
    resp = auth_client.post(
        "/api/languages", data={"language_code": "xyz", "flag_code": "zzz"}
    )
    assert resp.status_code == 400
    assert "unknown flag" in resp.json()["error"]


def test_delete_language(auth_client: TestClient):
    resp = auth_client.delete("/api/languages/eng")
    assert resp.status_code == 200
    assert resp.json() == {"ok": True}
    assert all(lc != "eng" for lc, _ in app.state.language_mappings)


def test_delete_nonexistent_language_still_returns_ok(auth_client: TestClient):
    resp = auth_client.delete("/api/languages/xyz")
    assert resp.status_code == 200


def test_reorder_languages(auth_client: TestClient):
    original = [lc for lc, _ in app.state.language_mappings]
    reversed_codes = list(reversed(original))

    resp = auth_client.post(
        "/api/languages/reorder",
        content=__import__("json").dumps(reversed_codes),
        headers={"Content-Type": "application/json"},
    )
    assert resp.status_code == 200
    assert [lc for lc, _ in app.state.language_mappings] == reversed_codes


def test_reorder_persists_to_db(auth_client: TestClient):
    from sqlmodel import Session, col, select

    from jellyfin_flag_setter.auth.db import get_engine
    from jellyfin_flag_setter.sync.models import DBLanguageMapping

    original = [lc for lc, _ in app.state.language_mappings]
    reversed_codes = list(reversed(original))
    auth_client.post(
        "/api/languages/reorder",
        content=__import__("json").dumps(reversed_codes),
        headers={"Content-Type": "application/json"},
    )

    with Session(get_engine()) as session:
        rows = session.exec(
            select(DBLanguageMapping).order_by(col(DBLanguageMapping.position))
        ).all()
    assert [r.language_code for r in rows] == reversed_codes


def test_settings_page_includes_language_mappings(auth_client: TestClient):
    resp = auth_client.get("/settings")
    assert resp.status_code == 200
    for lang_code, _ in DEFAULT_LANGUAGE_MAPPINGS:
        assert lang_code.encode() in resp.content


def test_movie_preview_known_flags_reflect_mappings(auth_client: TestClient):
    auth_client.delete("/api/languages/eng")
    resp = auth_client.get("/movie/movie1")
    assert resp.status_code == 200
    assert b'"gb"' not in resp.content or b'value="gb"' not in resp.content
