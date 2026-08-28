"""Admin-triggered CMS ingest job endpoints."""


PASS = {"X-Admin-Passphrase": "test-passphrase"}


def test_the_ingest_job_status_reports_the_current_job(client, monkeypatch):
    from services import code_ingest_job

    monkeypatch.setattr(code_ingest_job, "current_job", lambda: {
        "id": 123,
        "status": "running",
        "message": "working",
        "log_tail": ["ICD-10-CM"],
    })

    body = client.get("/codes/ingest-job").json()
    assert body["job"]["status"] == "running"
    assert body["job"]["log_tail"] == ["ICD-10-CM"]


def test_starting_the_ingest_requires_the_master_passphrase(client):
    r = client.post("/codes/ingest-job", json={"loaded_by": "trainer"})
    assert r.status_code == 403


def test_the_ingest_can_be_started_from_the_admin_header(client, monkeypatch):
    from services import code_ingest_job

    seen = {}

    def fake_start(loaded_by):
        seen["loaded_by"] = loaded_by
        return {"id": 456, "status": "running", "loaded_by": loaded_by}

    monkeypatch.setattr(code_ingest_job, "start_ingest_job", fake_start)

    r = client.post("/codes/ingest-job",
                    headers=PASS,
                    json={"loaded_by": "trainer workspace"})

    assert r.status_code == 200
    assert seen["loaded_by"] == "trainer workspace"
    assert r.json()["job"]["status"] == "running"
