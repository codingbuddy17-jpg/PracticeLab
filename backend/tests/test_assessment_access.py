"""
What the assessment module protects, and what it deliberately does not.

Passphrase gates were added after finding the question bank, the answer-key PDF
and the session tokens served unauthenticated. They were then removed at the
product owner's direction: the platform has no accounts, the trainer screens are
reached by URL knowledge alone, and a shared secret in a query string was buying
friction rather than protection — it walled off screens trainers use hourly
while anyone holding the secret still had everything.

What stays guarded is DESTRUCTION, not reading. Deleting an assessment or a
question cannot be undone, so those keep the passphrase; every other endpoint in
the module is open to anyone who can reach the API.

These tests exist so that position is explicit and deliberate rather than
something that drifted. If gating returns it should return as real per-user
auth, not a shared secret.
"""
import pytest

from conftest import make_question, seed_question_pool

from models import AssessmentQuestion, AssessmentSession, GeneratedAssessment

PASS = {"passphrase": "test-passphrase"}
WRONG = {"passphrase": "not-the-passphrase"}


@pytest.fixture()
def a_question(db):
    q = make_question(db, specialty="ICD10CM")
    db.commit()
    return q


def _sat(client, db):
    """One generated, submitted assessment. Returns (assessment_id, session_id)."""
    seed_question_pool(db)
    gen = client.post("/assessment/generate", json={
        "assessment_name": "P", "coders": [{"coder_name": "Alice"}],
        "duration_minutes": 30, "total_questions": 2,
        "specialty_mix": [{"specialty": "IP-DRG", "pct": 1.0, "topic_filter": ""}],
        "difficulty_mode": "auto", "generated_by": "t",
        "save_config": False, "randomise": True,
    }).json()
    token = gen["sessions"][0]["session_token"]
    started = client.post(f"/assessment/take/{token}/start").json()
    for i, q in enumerate(started["questions"]):
        client.post(f"/assessment/take/{token}/answer", json={
            "question_index": i, "question_id": q["question_id"], "selected_answer": "A"})
    client.post(f"/assessment/take/{token}/submit", json={"auto_submitted": False})
    sid = db.query(AssessmentSession).filter(
        AssessmentSession.session_token == token).first().id
    return gen["assessment_id"], sid


# ── open by design ────────────────────────────────────────────────────────────

def test_the_question_bank_reads_without_a_passphrase(client, a_question):
    r = client.get("/assessment/questions", params={"specialty": "ICD10CM"})
    assert r.status_code == 200
    assert r.json()["total"] == 1


def test_every_trainer_read_is_reachable(client, a_question, db):
    """
    The reads a trainer performs in the ordinary course of the job. Gating these
    put a wall in front of work that happens hourly, for a secret most screens
    had no way to collect.
    """
    for path, params in (
        ("/assessment/questions", {"specialty": "ICD10CM"}),
        ("/assessment/questions/stats", {}),
        ("/assessment/questions/pool-summary", {"specialty": "ICD10CM"}),
        ("/assessment/history", {}),
        ("/assessment/1/sessions", {}),
        ("/assessment/1/export-answer-key", {}),
        ("/assessment/1/export-pdf", {}),
        ("/assessment/analytics/overview", {}),
    ):
        assert client.get(path, params=params).status_code != 403, f"{path} must not be gated"


def test_editing_a_question_needs_no_passphrase(client, a_question, db):
    r = client.put(f"/assessment/questions/{a_question.question_id}",
                   json={"question_text": "Edited without a passphrase?"})
    assert r.status_code == 200, r.text
    db.expire_all()
    assert a_question.question_text == "Edited without a passphrase?"


def test_retiring_a_question_needs_no_passphrase(client, a_question, db):
    r = client.put(f"/assessment/questions/{a_question.question_id}/status",
                   params={"status": "Inactive", "updated_by": "someone"})
    assert r.status_code == 200
    db.expire_all()
    assert a_question.status == "Inactive"


def test_the_review_and_responses_export_are_open(client, db):
    aid, sid = _sat(client, db)
    assert client.get(f"/assessment/{aid}/session/{sid}/review").status_code == 200
    assert client.get(f"/assessment/{aid}/export-responses.xlsx").status_code == 200


def test_correcting_an_answer_needs_no_passphrase(client, db):
    """
    Still requires a written justification and still writes an audit entry —
    neither of those was ever about the passphrase.
    """
    aid, sid = _sat(client, db)
    r = client.post(f"/assessment/{aid}/session/{sid}/response/0/override",
                    json={"is_correct": True, "reason": "Key was wrong on this one.",
                          "trainer_name": "Trainer A"})
    assert r.status_code == 200, r.text

    bad = client.post(f"/assessment/{aid}/session/{sid}/response/0/override",
                      json={"is_correct": True, "reason": "", "trainer_name": "Trainer A"})
    assert bad.status_code == 400, "the justification is still required"


# ── still guarded: destruction ────────────────────────────────────────────────

def test_deleting_a_question_still_needs_the_passphrase(client, a_question, db):
    """Reading can be redone. Deleting cannot."""
    r = client.delete(f"/assessment/questions/{a_question.question_id}",
                      params={**WRONG, "deleted_by": "someone"})
    assert r.status_code == 403
    assert db.query(AssessmentQuestion).count() == 1


def test_deleting_an_assessment_still_needs_the_passphrase(client, db):
    aid, _ = _sat(client, db)
    r = client.delete(f"/assessment/{aid}", params=WRONG)
    assert r.status_code == 403
    assert db.query(GeneratedAssessment).count() == 1


# ── the verifier still verifies ───────────────────────────────────────────────

def test_verify_passphrase_still_checks(client, db):
    """
    Not a gate on data — the predicate the Question Bank asks before showing its
    screen. One that returns ok for anything is a trap for whoever reads it next.
    """
    assert client.post("/assessment/audit/verify-passphrase",
                       params={"trainer_name": "T", **PASS}).status_code == 200
    assert client.post("/assessment/audit/verify-passphrase",
                       params={"trainer_name": "T", **WRONG}).status_code == 403


# ── the coder path is unchanged ───────────────────────────────────────────────

def test_a_coder_still_reaches_only_their_own_session(client, db):
    """The take flow is gated by the session token, and always was."""
    assert client.get("/assessment/take/ASM-NOTREAL").status_code == 404
