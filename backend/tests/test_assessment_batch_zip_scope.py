"""
A batch's coder reports must describe that batch.

The ZIP called analytics_coder() with a name and nothing else, so each PDF
carried the coder's entire assessment history. A trainer reading "Wave 1
results" was actually reading every paper that coder had ever sat — evidence
for a cohort contaminated by everything outside it.
"""
import io
import zipfile

from conftest import seed_question_pool


def _payload(name, batch, coders):
    return {
        "assessment_name": name,
        "batch_name": batch,
        "coders": coders,
        "duration_minutes": 60,
        "total_questions": 3,
        "specialty_mix": [{"specialty": "IP-DRG", "pct": 1.0, "topic_filter": ""}],
        "difficulty_mode": "auto",
        "generated_by": "trainer",
        "save_config": False,
        "randomise": True,
    }


def _sit(client, db, token, answer="A"):
    started = client.post(f"/assessment/take/{token}/start").json()
    for i, q in enumerate(started["questions"]):
        client.post(f"/assessment/take/{token}/answer", json={
            "question_index": i, "question_id": q["question_id"], "selected_answer": answer,
        })
    client.post(f"/assessment/take/{token}/submit", json={"auto_submitted": False})


def _two_batches(client, db):
    """Alice sits one paper in Wave 1 and another in Wave 2."""
    seed_question_pool(db)
    alice = [{"coder_name": "Alice", "employee_id": "E001"}]
    for batch in ("Wave 1", "Wave 2"):
        gen = client.post("/assessment/generate",
                          json=_payload(f"{batch} paper", batch, alice)).json()
        _sit(client, db, gen["sessions"][0]["session_token"])


def test_coder_analytics_can_be_scoped_to_one_batch(client, db):
    _two_batches(client, db)

    everything = client.get("/assessment/analytics/coder",
                            params={"coder_name": "Alice"}).json()
    wave1 = client.get("/assessment/analytics/coder",
                       params={"coder_name": "Alice", "batch_name": "Wave 1"}).json()

    assert everything["total_assessments_taken"] == 2
    assert wave1["total_assessments_taken"] == 1


def test_batch_zip_contains_one_pdf_per_coder(client, db):
    seed_question_pool(db)
    gen = client.post("/assessment/generate", json=_payload(
        "Wave 1 paper", "Wave 1",
        [{"coder_name": "Alice", "employee_id": "E001"},
         {"coder_name": "Bob", "employee_id": "E002"}],
    )).json()
    for s in gen["sessions"]:
        _sit(client, db, s["session_token"])

    r = client.get("/assessment/analytics/batch-coder-reports.zip",
                   params={"batch_name": "Wave 1"})
    assert r.status_code == 200
    names = zipfile.ZipFile(io.BytesIO(r.content)).namelist()
    assert len(names) == 2
    assert any("Alice" in n and "E001" in n for n in names)
    assert any("Bob" in n and "E002" in n for n in names)


def test_same_named_coders_get_separate_reports(client, db):
    """Two people called Alice are two people, not one merged report."""
    seed_question_pool(db)
    gen = client.post("/assessment/generate", json=_payload(
        "Wave 1 paper", "Wave 1",
        [{"coder_name": "Alice", "employee_id": "E001"},
         {"coder_name": "Alice", "employee_id": "E002"}],
    )).json()
    for s in gen["sessions"]:
        _sit(client, db, s["session_token"])

    r = client.get("/assessment/analytics/batch-coder-reports.zip",
                   params={"batch_name": "Wave 1"})
    names = zipfile.ZipFile(io.BytesIO(r.content)).namelist()
    assert len(names) == 2, f"expected one report each, got {names}"
