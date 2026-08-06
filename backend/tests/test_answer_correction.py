"""
A trainer can correct one graded answer, and must say why.

Auto-grading compares letters. It cannot know that a key was wrong, or that a
coder explained a defensible reading offline. The correction is stored
alongside the grader's verdict rather than replacing it, so the record shows
that a score was changed, by whom, and on what grounds — a score that silently
moved is worth less than one that shows its working.
"""
import json

import pytest

from conftest import seed_question_pool

from models import (
    AssessmentAuditLog, AssessmentResponse, AssessmentResult,
    AssessmentSession, GeneratedAssessmentStudent,
)

PASS = {"passphrase": "test-passphrase"}


def _served_key(db, session_id):
    """question_index -> correct letter, as served to this coder."""
    sess = db.query(AssessmentSession).filter(AssessmentSession.id == session_id).first()
    slot = db.query(GeneratedAssessmentStudent).filter(
        GeneratedAssessmentStudent.id == sess.student_slot_id).first()
    qs = slot.questions_json
    qs = json.loads(qs) if isinstance(qs, str) else qs
    return {i: q["correct_answer"] for i, q in enumerate(qs)}


def _sat_assessment(client, db, n_questions=4):
    """
    One coder with a KNOWN mix of right and wrong: the first answer is correct,
    the rest deliberately are not.

    Answering "A" throughout is not deterministic — options are shuffled per
    coder, so a run could produce no correct answers at all and a test looking
    for one would fail at random.
    """
    seed_question_pool(db)
    gen = client.post("/assessment/generate", json={
        "assessment_name": "Correctable",
        "coders": [{"coder_name": "Alice", "employee_id": "E001"}],
        "duration_minutes": 30, "total_questions": n_questions,
        "specialty_mix": [{"specialty": "IP-DRG", "pct": 1.0, "topic_filter": ""}],
        "difficulty_mode": "auto", "generated_by": "t",
        "save_config": False, "randomise": True,
    }).json()
    token = gen["sessions"][0]["session_token"]
    started = client.post(f"/assessment/take/{token}/start").json()
    session = db.query(AssessmentSession).filter(
        AssessmentSession.session_token == token).first()
    key = _served_key(db, session.id)

    for i, q in enumerate(started["questions"]):
        right = key[i]
        answer = right if i == 0 else next(l for l in "ABCD" if l != right)
        client.post(f"/assessment/take/{token}/answer", json={
            "question_index": i, "question_id": q["question_id"], "selected_answer": answer,
        })
    client.post(f"/assessment/take/{token}/submit", json={"auto_submitted": False})
    db.expire_all()
    return gen["assessment_id"], session.id


def _override(client, aid, sid, index=0, is_correct=True,
              reason="Key was wrong — E11.22 is also defensible.", trainer="Trainer A"):
    return client.post(
        f"/assessment/{aid}/session/{sid}/response/{index}/override",
        params=PASS,
        json={"is_correct": is_correct, "reason": reason, "trainer_name": trainer},
    )


def _review(client, aid, sid):
    return client.get(f"/assessment/{aid}/session/{sid}/review", params=PASS).json()


# ── the justification is mandatory ────────────────────────────────────────────

def test_a_correction_without_a_reason_is_refused(client, db):
    aid, sid = _sat_assessment(client, db)
    r = _override(client, aid, sid, reason="")
    assert r.status_code == 400
    assert "justification" in r.json()["detail"].lower()


def test_a_token_reason_is_refused(client, db):
    """"ok" is not a justification."""
    aid, sid = _sat_assessment(client, db)
    assert _override(client, aid, sid, reason="ok").status_code == 400


def test_a_correction_without_a_trainer_name_is_refused(client, db):
    aid, sid = _sat_assessment(client, db)
    assert _override(client, aid, sid, trainer="").status_code == 400


# ── the score moves at once ───────────────────────────────────────────────────

def test_marking_a_wrong_answer_correct_raises_the_score(client, db):
    aid, sid = _sat_assessment(client, db, n_questions=4)
    before = db.query(AssessmentResult).filter(AssessmentResult.session_id == sid).first()
    start_correct = before.correct_count

    wrong = next(i for i, r in enumerate(
        db.query(AssessmentResponse).filter(AssessmentResponse.session_id == sid)
        .order_by(AssessmentResponse.question_index).all()) if not r.is_correct)

    r = _override(client, aid, sid, index=wrong, is_correct=True)
    assert r.status_code == 200, r.text
    assert r.json()["correct_count"] == start_correct + 1

    db.expire_all()
    after = db.query(AssessmentResult).filter(AssessmentResult.session_id == sid).first()
    assert after.correct_count == start_correct + 1
    assert after.score_pct == round((start_correct + 1) / after.total_questions * 100, 1)


def test_marking_a_right_answer_wrong_lowers_the_score(client, db):
    """Corrections run both ways — a key can be wrong in either direction."""
    aid, sid = _sat_assessment(client, db)
    right = next(i for i, r in enumerate(
        db.query(AssessmentResponse).filter(AssessmentResponse.session_id == sid)
        .order_by(AssessmentResponse.question_index).all()) if r.is_correct)

    before = db.query(AssessmentResult).filter(AssessmentResult.session_id == sid).first().correct_count
    r = _override(client, aid, sid, index=right, is_correct=False,
                  reason="Answer key updated; this option is no longer accepted.")
    assert r.status_code == 200
    assert r.json()["correct_count"] == before - 1


def test_correcting_twice_does_not_double_count(client, db):
    """The override replaces the previous verdict rather than stacking on it."""
    aid, sid = _sat_assessment(client, db)
    wrong = next(i for i, r in enumerate(
        db.query(AssessmentResponse).filter(AssessmentResponse.session_id == sid)
        .order_by(AssessmentResponse.question_index).all()) if not r.is_correct)

    first = _override(client, aid, sid, index=wrong, is_correct=True).json()["correct_count"]
    second = _override(client, aid, sid, index=wrong, is_correct=True,
                       reason="Confirming the earlier correction.").json()["correct_count"]
    assert first == second


def test_a_correction_can_be_reversed(client, db):
    aid, sid = _sat_assessment(client, db)
    wrong = next(i for i, r in enumerate(
        db.query(AssessmentResponse).filter(AssessmentResponse.session_id == sid)
        .order_by(AssessmentResponse.question_index).all()) if not r.is_correct)

    raised = _override(client, aid, sid, index=wrong, is_correct=True).json()["correct_count"]
    lowered = _override(client, aid, sid, index=wrong, is_correct=False,
                        reason="Reverting — the original key was right after all.").json()["correct_count"]
    assert lowered == raised - 1


# ── the record shows its working ──────────────────────────────────────────────

def test_the_original_verdict_is_kept_alongside(client, db):
    """A correction must read as a correction, not as the original truth."""
    aid, sid = _sat_assessment(client, db)
    wrong = next(i for i, r in enumerate(
        db.query(AssessmentResponse).filter(AssessmentResponse.session_id == sid)
        .order_by(AssessmentResponse.question_index).all()) if not r.is_correct)
    _override(client, aid, sid, index=wrong, is_correct=True)

    q = _review(client, aid, sid)["questions"][wrong]
    assert q["is_correct"] is True          # what it counts as now
    assert q["auto_is_correct"] is False    # what the grader said
    assert q["overridden"] is True
    assert "defensible" in q["override_reason"]
    assert q["override_by"] == "Trainer A"
    assert q["override_at"]


def test_the_review_counts_corrections_for_the_sessions_badge(client, db):
    aid, sid = _sat_assessment(client, db)
    assert _review(client, aid, sid)["corrections"] == 0
    _override(client, aid, sid, index=0, is_correct=True)
    assert _review(client, aid, sid)["corrections"] == 1


def test_a_correction_is_written_to_the_audit_log(client, db):
    aid, sid = _sat_assessment(client, db)
    _override(client, aid, sid, index=0, is_correct=True)

    entry = db.query(AssessmentAuditLog).filter(
        AssessmentAuditLog.action == "correct-answer").first()
    assert entry is not None
    assert entry.trainer_name == "Trainer A"
    assert "Alice" in entry.details and "E001" in entry.details
    assert "defensible" in entry.details, "the reason must survive into the log"


# ── guards ────────────────────────────────────────────────────────────────────

def test_a_correction_needs_the_passphrase(client, db):
    aid, sid = _sat_assessment(client, db)
    r = client.post(f"/assessment/{aid}/session/{sid}/response/0/override",
                    json={"is_correct": True, "reason": "Trying it on", "trainer_name": "X"})
    assert r.status_code == 403


def test_an_unsubmitted_session_cannot_be_corrected(client, db):
    """Nothing to correct until it is graded, and the coder may still be sitting it."""
    seed_question_pool(db)
    gen = client.post("/assessment/generate", json={
        "assessment_name": "Open", "coders": [{"coder_name": "Bob"}],
        "duration_minutes": 30, "total_questions": 2,
        "specialty_mix": [{"specialty": "IP-DRG", "pct": 1.0, "topic_filter": ""}],
        "difficulty_mode": "auto", "generated_by": "t",
        "save_config": False, "randomise": True,
    }).json()
    sid = db.query(AssessmentSession).filter(
        AssessmentSession.session_token == gen["sessions"][0]["session_token"]).first().id
    r = _override(client, gen["assessment_id"], sid)
    assert r.status_code == 400
    assert "submitted" in r.json()["detail"].lower()


def test_an_unanswered_question_index_404s(client, db):
    aid, sid = _sat_assessment(client, db, n_questions=2)
    assert _override(client, aid, sid, index=99).status_code == 404


def test_the_sessions_list_flags_a_corrected_session(client, db):
    """The badge belongs on the row too, not only inside the review."""
    aid, sid = _sat_assessment(client, db)
    rows = client.get(f"/assessment/{aid}/sessions", params=PASS).json()["sessions"]
    assert rows[0]["corrected"] is False

    _override(client, aid, sid, index=0, is_correct=True)
    rows = client.get(f"/assessment/{aid}/sessions", params=PASS).json()["sessions"]
    assert rows[0]["corrected"] is True


def test_the_sessions_list_publishes_the_papers_pass_mark(client, db):
    """
    The screen coloured scores against a hardcoded 80/90, which may belong to a
    different assessment entirely.
    """
    seed_question_pool(db)
    gen = client.post("/assessment/generate", json={
        "assessment_name": "Refresher", "coders": [{"coder_name": "Alice"}],
        "duration_minutes": 30, "total_questions": 2, "pass_threshold": 70,
        "specialty_mix": [{"specialty": "IP-DRG", "pct": 1.0, "topic_filter": ""}],
        "difficulty_mode": "auto", "generated_by": "t",
        "save_config": False, "randomise": True,
    }).json()
    d = client.get(f"/assessment/{gen['assessment_id']}/sessions", params=PASS).json()
    assert d["pass_threshold"] == 70.0


def test_a_paper_without_its_own_mark_falls_back_to_the_default(client, db):
    aid, _ = _sat_assessment(client, db)
    d = client.get(f"/assessment/{aid}/sessions", params=PASS).json()
    assert d["pass_threshold"] == 90.0
