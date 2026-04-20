from starlette.testclient import TestClient

from jellyfin_flag_setter.main import app


def test_list_jobs_returns_library_sync(auth_client: TestClient):
    resp = auth_client.get("/api/jobs")
    assert resp.status_code == 200
    jobs = resp.json()
    assert isinstance(jobs, list)
    assert len(jobs) == 1
    job = jobs[0]
    assert job["job_id"] == "library_sync"
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
    resp = auth_client.post(
        "/api/jobs/library_sync/interval", data={"interval_minutes": "30"}
    )
    assert resp.status_code == 200
    assert resp.json() == {"ok": True}

    status = auth_client.get("/api/jobs/library_sync").json()
    assert status["interval_seconds"] == 1800


def test_update_interval_clamps_to_minimum(auth_client: TestClient):
    resp = auth_client.post(
        "/api/jobs/library_sync/interval", data={"interval_minutes": "0"}
    )
    assert resp.status_code == 200

    status = auth_client.get("/api/jobs/library_sync").json()
    assert status["interval_seconds"] == 60


def test_list_jobs_reflects_updated_interval(auth_client: TestClient):
    auth_client.post("/api/jobs/library_sync/interval", data={"interval_minutes": "45"})
    jobs = auth_client.get("/api/jobs").json()
    assert jobs[0]["interval_seconds"] == 2700


def test_settings_page_includes_jobs(auth_client: TestClient):
    resp = auth_client.get("/settings")
    assert resp.status_code == 200
    assert b"Library Sync" in resp.content
    assert b"Run now" in resp.content
