from starlette.testclient import TestClient

from jellyfin_flag_setter.main import app


def test_list_jobs_returns_library_sync(auth_client: TestClient):
    resp = auth_client.get("/api/jobs")
    assert resp.status_code == 200
    jobs = resp.json()
    assert isinstance(jobs, list)
    assert len(jobs) >= 1
    job = next(j for j in jobs if j["job_id"] == "library_sync")
    assert job["label"] == "Library Sync"
    assert isinstance(job["interval_seconds"], int)
    assert isinstance(job["is_running"], bool)
    assert "last_run_at" in job


def test_job_status_fields(auth_client: TestClient):
    resp = auth_client.get("/api/jobs/library_sync")
    assert resp.status_code == 200
    job = resp.json()
    assert job["job_id"] == "library_sync"
    assert job["interval_seconds"] == 86400
    assert job["time_unit"] == "hours"
    assert job["interval_display"] == 24
    assert job["is_running"] is False
    assert job["last_run_at"] is None


def test_unknown_job_returns_404(auth_client: TestClient):
    resp = auth_client.get("/api/jobs/does_not_exist")
    assert resp.status_code == 404


def test_trigger_job(auth_client: TestClient):
    resp = auth_client.post("/api/jobs/library_sync/run")
    assert resp.status_code == 200
    assert resp.json() == {"triggered": True}


def test_trigger_job_already_running(auth_client: TestClient):
    app.state.job_manager._running["library_sync"] = True
    try:
        resp = auth_client.post("/api/jobs/library_sync/run")
        assert resp.status_code == 200
        assert resp.json() == {"triggered": False}
    finally:
        app.state.job_manager._running["library_sync"] = False


def test_update_interval_persists(auth_client: TestClient):
    # library_sync uses hours — 2h = 7200s
    resp = auth_client.post(
        "/api/jobs/library_sync/interval", data={"interval_value": "2"}
    )
    assert resp.status_code == 200
    assert resp.json() == {"ok": True}

    status = auth_client.get("/api/jobs/library_sync").json()
    assert status["interval_seconds"] == 7200
    assert status["interval_display"] == 2


def test_update_interval_clamps_to_minimum(auth_client: TestClient):
    resp = auth_client.post(
        "/api/jobs/library_sync/interval", data={"interval_value": "0"}
    )
    assert resp.status_code == 200

    status = auth_client.get("/api/jobs/library_sync").json()
    assert status["interval_seconds"] == 3600  # 1 hour minimum
    assert status["interval_display"] == 1


def test_list_jobs_reflects_updated_interval(auth_client: TestClient):
    # library_sync uses hours — 3h = 10800s
    auth_client.post("/api/jobs/library_sync/interval", data={"interval_value": "3"})
    job = next(
        j for j in auth_client.get("/api/jobs").json() if j["job_id"] == "library_sync"
    )
    assert job["interval_seconds"] == 10800
    assert job["interval_display"] == 3


def test_recent_sync_uses_minutes(auth_client: TestClient):
    status = auth_client.get("/api/jobs/recent_sync").json()
    assert status["time_unit"] == "minutes"
    assert status["interval_seconds"] == 900
    assert status["interval_display"] == 15


def test_update_recent_sync_interval(auth_client: TestClient):
    resp = auth_client.post(
        "/api/jobs/recent_sync/interval", data={"interval_value": "30"}
    )
    assert resp.status_code == 200
    status = auth_client.get("/api/jobs/recent_sync").json()
    assert status["interval_seconds"] == 1800


def test_settings_page_includes_jobs(auth_client: TestClient):
    resp = auth_client.get("/settings")
    assert resp.status_code == 200
    assert b"Library Sync" in resp.content
    assert b"Recent Sync" in resp.content
    assert b"Run now" in resp.content
    assert b"hours" in resp.content
    assert b"minutes" in resp.content


def test_list_jobs_includes_recent_sync(auth_client: TestClient):
    jobs = auth_client.get("/api/jobs").json()
    ids = [j["job_id"] for j in jobs]
    assert "recent_sync" in ids


def test_recent_sync_default_interval(auth_client: TestClient):
    status = auth_client.get("/api/jobs/recent_sync").json()
    assert status["interval_seconds"] == 900


def test_trigger_recent_sync(auth_client: TestClient):
    resp = auth_client.post("/api/jobs/recent_sync/run")
    assert resp.status_code == 200
    assert resp.json() == {"triggered": True}
