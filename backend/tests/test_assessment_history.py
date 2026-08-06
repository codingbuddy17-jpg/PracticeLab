"""
History lists assessments, and refuses to erase completed work by accident.

Delete cascaded through responses, results and sessions with nothing but a
passphrase. The passphrase proves who is asking; it never established that
destroying submitted work was intended — and none of it can be reconstructed.
"""
from sqlalchemy import event

from conftest import seed_question_pool

from models import AssessmentAuditLog, AssessmentResult, AssessmentSession, GeneratedAssessment

PASS = "test-passphrase"


def _generate(client, db, name="Paper", coders=None, batch=None, threshold=None, seed=True):
    # seed=False when generating repeatedly: the pool uses fixed question ids,
    # so re-seeding collides on the unique constraint.
    if seed:
        seed_question_pool(db)
    payload = {
        "assessment_name": name,
        "coders": coders or [{"coder_name": "Alice", "employee_id": "E001"}],
        "duration_minutes": 30, "total_questions": 2,
        "specialty_mix": [{"specialty": "IP-DRG", "pct": 1.0, "topic_filter": ""}],
        "difficulty_mode": "auto", "generated_by": "trainer",
        "save_config": False, "randomise": True,
    }
    if batch:
        payload["batch_name"] = batch
    if threshold:
        payload["pass_threshold"] = threshold
    return client.post("/assessment/generate", json=payload).json()


def _sit(client, token):
    started = client.post(f"/assessment/take/{token}/start").json()
    for i, q in enumerate(started["questions"]):
        client.post(f"/assessment/take/{token}/answer", json={
            "question_index": i, "question_id": q["question_id"], "selected_answer": "A",
        })
    client.post(f"/assessment/take/{token}/submit", json={"auto_submitted": False})


def _delete(client, aid, **params):
    return client.delete(f"/assessment/{aid}",
                         params={"passphrase": PASS, "trainer_name": "Trainer A", **params})


# ── deleting completed work ───────────────────────────────────────────────────

def test_an_unsat_assessment_deletes_freely(client, db):
    """Nothing has been done yet, so there is nothing to protect."""
    gen = _generate(client, db)
    r = _delete(client, gen["assessment_id"])
    assert r.status_code == 200, r.text
    assert db.query(GeneratedAssessment).count() == 0


def test_a_completed_assessment_is_not_deleted_by_default(client, db):
    gen = _generate(client, db)
    _sit(client, gen["sessions"][0]["session_token"])

    r = _delete(client, gen["assessment_id"])
    assert r.status_code == 409
    detail = r.json()["detail"]
    assert detail["submitted"] == 1
    assert detail["requires"] == "force"
    assert db.query(GeneratedAssessment).count() == 1, "nothing may be removed"
    assert db.query(AssessmentResult).count() == 1


def test_forcing_without_a_reason_is_refused(client, db):
    gen = _generate(client, db)
    _sit(client, gen["sessions"][0]["session_token"])
    r = _delete(client, gen["assessment_id"], force=True)
    assert r.status_code == 400
    assert "reason" in r.json()["detail"].lower()
    assert db.query(GeneratedAssessment).count() == 1


def test_forcing_with_a_reason_deletes_and_records_why(client, db):
    gen = _generate(client, db)
    _sit(client, gen["sessions"][0]["session_token"])

    r = _delete(client, gen["assessment_id"], force=True,
                reason="Duplicate paper issued in error; coders re-sat the correct one.")
    assert r.status_code == 200, r.text
    assert r.json()["completed_removed"] == 1
    assert db.query(GeneratedAssessment).count() == 0
    assert db.query(AssessmentSession).count() == 0

    entry = db.query(AssessmentAuditLog).filter(
        AssessmentAuditLog.action == "delete-assessment").first()
    assert entry is not None
    assert entry.trainer_name == "Trainer A"
    assert "re-sat" in entry.details, "the reason must survive into the log"


def test_every_delete_is_audited_even_when_nothing_was_lost(client, db):
    """A deletion nobody can trace is the gap an audit log exists to close."""
    gen = _generate(client, db)
    _delete(client, gen["assessment_id"])
    entry = db.query(AssessmentAuditLog).filter(
        AssessmentAuditLog.action == "delete-assessment").first()
    assert entry is not None
    assert "Paper" in entry.details


def test_delete_still_needs_the_passphrase(client, db):
    gen = _generate(client, db)
    r = client.delete(f"/assessment/{gen['assessment_id']}", params={"passphrase": "wrong"})
    assert r.status_code == 403
    assert db.query(GeneratedAssessment).count() == 1


# ── what the list carries ─────────────────────────────────────────────────────

def test_history_reports_batch_and_pass_mark(client, db):
    _generate(client, db, name="Wave 1 paper", batch="Wave 1", threshold=70)
    row = client.get("/assessment/history").json()[0]
    assert row["batch_name"] == "Wave 1"
    assert row["pass_threshold"] == 70.0


def test_history_reports_where_each_assessment_stands(client, db):
    """So the list answers "is this finished?" without opening Sessions."""
    gen = _generate(client, db, coders=[
        {"coder_name": "Alice", "employee_id": "E1"},
        {"coder_name": "Bob", "employee_id": "E2"},
    ])
    _sit(client, gen["sessions"][0]["session_token"])

    row = client.get("/assessment/history").json()[0]
    assert row["status_counts"]["submitted"] == 1
    assert row["status_counts"]["pending"] == 1


def test_history_does_not_query_per_assessment(client, db):
    """
    The per-row lookups used to run inside the loop — one for the first student
    and one lazy load for the config — which is hundreds of round trips on a
    year of assessments.
    """
    _generate(client, db, name="Paper 0")
    for i in range(1, 12):
        _generate(client, db, name=f"Paper {i}", seed=False)

    n = {"q": 0}
    bind = db.get_bind()

    def before(conn, cur, stmt, params, ctx, many):
        n["q"] += 1

    event.listen(bind, "before_cursor_execute", before)
    try:
        rows = client.get("/assessment/history").json()
    finally:
        event.remove(bind, "before_cursor_execute", before)

    assert len(rows) == 12
    assert n["q"] < 12, f"query count still scales with the number of assessments: {n['q']}"
