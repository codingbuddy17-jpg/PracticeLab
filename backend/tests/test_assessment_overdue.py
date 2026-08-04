"""
A session whose time ran out must be scored, not merely labelled.

Auto-submit was driven entirely by the coder's browser timer. If the coder shut
the laptop, lost the network, or walked away, the session stayed in_progress
forever. The trainer's list cosmetically relabelled it "auto_submitted" while
no AssessmentResult existed — so the attempt showed a blank score and was
absent from every analytic, export and PDF.
"""
from datetime import timedelta

from conftest import seed_question_pool

from models import AssessmentSession, AssessmentResult
from services.timeutil import utc_now

PAYLOAD = {
    "assessment_name": "Overdue Test",
    "coders": [{"coder_name": "Alice", "employee_id": "E001"}],
    "duration_minutes": 60,
    "total_questions": 3,
    "specialty_mix": [{"specialty": "IP-DRG", "pct": 1.0, "topic_filter": ""}],
    "difficulty_mode": "auto",
    "generated_by": "trainer",
    "save_config": False,
    "randomise": True,
}


def _abandoned(client, db, answer_one=True):
    """A started session, one answer saved, then the clock wound past its end."""
    seed_question_pool(db)
    gen = client.post("/assessment/generate", json=PAYLOAD).json()
    token = gen["sessions"][0]["session_token"]
    started = client.post(f"/assessment/take/{token}/start").json()
    if answer_one:
        q = started["questions"][0]
        client.post(f"/assessment/take/{token}/answer", json={
            "question_index": 0,
            "question_id": q["question_id"],
            "selected_answer": "A",
        })
    session = db.query(AssessmentSession).filter(
        AssessmentSession.session_token == token
    ).first()
    session.time_limit_ends_at = utc_now() - timedelta(minutes=5)
    db.commit()
    return gen["assessment_id"], token, session.id


def _result(db, session_id):
    return db.query(AssessmentResult).filter(
        AssessmentResult.session_id == session_id
    ).first()


def test_overdue_session_is_scored_when_trainer_lists_sessions(client, db):
    assessment_id, _, session_id = _abandoned(client, db)
    assert _result(db, session_id) is None, "precondition: not yet scored"

    r = client.get(f"/assessment/{assessment_id}/sessions")
    assert r.status_code == 200

    db.expire_all()
    result = _result(db, session_id)
    assert result is not None, "an overdue session must be scored, not just relabelled"
    assert result.total_questions == 3
    row = r.json()["sessions"][0]
    assert row["status"] == "submitted"
    assert row["auto_submitted"] is True
    assert row["score_pct"] is not None


def test_overdue_session_reaches_analytics(client, db):
    _abandoned(client, db)
    r = client.get("/assessment/analytics/overview")
    assert r.status_code == 200
    # The sweep runs before the analytic reads, so the attempt is counted.
    assert _result(db, db.query(AssessmentSession).first().id) is not None


def test_unanswered_overdue_session_scores_zero_not_null(client, db):
    """Walking away without answering is a zero, which is a fact worth having."""
    _, _, session_id = _abandoned(client, db, answer_one=False)
    client.get("/assessment/analytics/overview")
    db.expire_all()
    result = _result(db, session_id)
    assert result is not None
    assert result.correct_count == 0
    assert result.score_pct == 0.0


def test_sweep_is_idempotent(client, db):
    assessment_id, _, session_id = _abandoned(client, db)
    for _ in range(3):
        client.get(f"/assessment/{assessment_id}/sessions")
    db.expire_all()
    n = db.query(AssessmentResult).filter(
        AssessmentResult.session_id == session_id
    ).count()
    assert n == 1, "repeated reads must not stack duplicate results"


def test_a_running_session_is_left_alone(client, db):
    """The sweep must not close a session whose clock is still running."""
    seed_question_pool(db)
    gen = client.post("/assessment/generate", json=PAYLOAD).json()
    token = gen["sessions"][0]["session_token"]
    client.post(f"/assessment/take/{token}/start")

    client.get(f"/assessment/{gen['assessment_id']}/sessions")

    db.expire_all()
    session = db.query(AssessmentSession).filter(
        AssessmentSession.session_token == token
    ).first()
    assert session.status == "in_progress"
    assert _result(db, session.id) is None
