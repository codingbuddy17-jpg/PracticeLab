"""
Overview: one meaning per number, and a lapsed session that says so.

An assessment has two clocks. `expires_at` is the window to START — eight hours
from generation — and `time_limit_ends_at` is the duration clock once someone
has. The sweep handled the second and not the first, so a coder who never
turned up left a session sitting at "pending" indefinitely. Sessions computed
"expired" for its own display and stored nothing, which meant analytics read
the column, found "pending", and counted a session nobody would ever sit as
merely not done yet — for as long as the database lived.

The rest is numbers that changed meaning underneath the reader: a headline
count that meant one thing filtered and another unfiltered, and a caveat about
varying pass marks that fired on papers the screen was not showing.
"""
from datetime import datetime, timedelta, timezone

import pytest

from conftest import seed_question_pool

from models import AssessmentSession, GeneratedAssessment


def _generate(client, db, name="Paper", coders=None, threshold=None, seed=True,
              batch=None):
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
    if threshold:
        payload["pass_threshold"] = threshold
    if batch:
        payload["batch_name"] = batch
    return client.post("/assessment/generate", json=payload).json()


def _overview(client, **params):
    return client.get("/assessment/analytics/overview", params=params).json()


# ── a lapsed session becomes a fact, not a display trick ─────────────────────

def test_a_session_nobody_started_expires_once_its_window_closes(client, db):
    gen = _generate(client, db)
    sess = db.query(AssessmentSession).filter(
        AssessmentSession.session_token == gen["sessions"][0]["session_token"]).first()
    assert sess.status == "pending"

    sess.expires_at = datetime.now(timezone.utc) - timedelta(hours=1)
    db.commit()

    # Any analytics read runs the sweep first — that is the point of wiring it
    # at the router rather than per endpoint.
    _overview(client)
    db.expire_all()
    assert db.query(AssessmentSession).filter(
        AssessmentSession.id == sess.id).first().status == "expired"


def test_a_session_still_inside_its_window_is_left_alone(client, db):
    gen = _generate(client, db)
    sess = db.query(AssessmentSession).filter(
        AssessmentSession.session_token == gen["sessions"][0]["session_token"]).first()
    _overview(client)
    db.expire_all()
    assert db.query(AssessmentSession).filter(
        AssessmentSession.id == sess.id).first().status == "pending"


def test_expiring_writes_no_result(client, db):
    """They never answered anything. A score would be an invention."""
    from models import AssessmentResult

    gen = _generate(client, db)
    sess = db.query(AssessmentSession).filter(
        AssessmentSession.session_token == gen["sessions"][0]["session_token"]).first()
    sess.expires_at = datetime.now(timezone.utc) - timedelta(hours=1)
    db.commit()

    _overview(client)
    assert db.query(AssessmentResult).filter(
        AssessmentResult.session_id == sess.id).count() == 0


def test_overview_reports_the_lapsed_count(client, db):
    """
    It read s.status == "expired" and nothing ever wrote that, so the figure
    was structurally always zero — dead code that looked live.
    """
    gen = _generate(client, db, coders=[
        {"coder_name": "Alice"}, {"coder_name": "Bob"}])
    for s in db.query(AssessmentSession).all():
        s.expires_at = datetime.now(timezone.utc) - timedelta(hours=1)
    db.commit()

    assert _overview(client)["expired_sessions"] == 2


def test_expiry_is_idempotent(client, db):
    """It runs on every analytics request; the second must be a no-op."""
    gen = _generate(client, db)
    sess = db.query(AssessmentSession).filter(
        AssessmentSession.session_token == gen["sessions"][0]["session_token"]).first()
    sess.expires_at = datetime.now(timezone.utc) - timedelta(hours=1)
    db.commit()

    assert _overview(client)["expired_sessions"] == 1
    assert _overview(client)["expired_sessions"] == 1


# ── numbers that mean the same thing however you arrive at them ──────────────

def test_total_assessments_means_the_same_filtered_or_not(client, db):
    """
    It fell back to "every assessment ever generated" when unfiltered, so the
    headline changed definition the moment someone picked a date range — and
    counted papers no figure beside it described.
    """
    _generate(client, db, name="Sat paper")
    token = db.query(AssessmentSession).first().session_token
    client.post(f"/assessment/take/{token}/start")
    client.post(f"/assessment/take/{token}/submit", json={"auto_submitted": False})

    # A second paper with no sessions at all cannot be represented in any window.
    db.add(GeneratedAssessment(assessment_name="Never issued", generated_by="t",
                               student_count=0))
    db.commit()

    unfiltered = _overview(client)
    assert unfiltered["total_assessments"] == 1, \
        "an assessment with no sessions was counted in the headline"


def test_pass_thresholds_vary_only_looks_at_this_window(client, db):
    """
    Judged against every threshold in the database, a filtered view of one
    batch marked entirely at 90 still warned that pass marks varied — because
    an unrelated older paper used 80.
    """
    old = _generate(client, db, name="Old paper at 80", threshold=80, batch="Wave 1")
    new = _generate(client, db, name="This batch at 90", threshold=90, seed=False,
                    batch="Wave 2")
    for gen in (old, new):
        t = gen["sessions"][0]["session_token"]
        client.post(f"/assessment/take/{t}/start")
        client.post(f"/assessment/take/{t}/submit", json={"auto_submitted": False})

    # Unfiltered the marks genuinely differ; filtered to one batch they do not.
    assert _overview(client)["pass_thresholds_vary"] is True
    only_this = _overview(client, batch_name="Wave 2")
    assert only_this["pass_thresholds_vary"] is False, \
        "a caveat fired on a paper this view is not showing"
    assert only_this["total_assessments"] == 1


def test_pass_thresholds_vary_still_fires_when_they_really_do(client, db):
    """The caveat has to keep working; scoping it must not silence it."""
    a = _generate(client, db, name="At 80", threshold=80, batch="Wave 1")
    b = _generate(client, db, name="At 90", threshold=90, seed=False, batch="Wave 1")
    for gen in (a, b):
        t = gen["sessions"][0]["session_token"]
        client.post(f"/assessment/take/{t}/start")
        client.post(f"/assessment/take/{t}/submit", json={"auto_submitted": False})

    assert _overview(client)["pass_thresholds_vary"] is True


# ── denominators ─────────────────────────────────────────────────────────────

def test_the_rates_carry_the_counts_behind_them(client, db):
    gen = _generate(client, db, coders=[{"coder_name": "Alice"}, {"coder_name": "Bob"}])
    t = gen["sessions"][0]["session_token"]
    client.post(f"/assessment/take/{t}/start")
    client.post(f"/assessment/take/{t}/submit", json={"auto_submitted": False})

    d = _overview(client)
    assert d["total_sessions"] == 2
    assert d["total_submitted"] == 1
    assert d["completion_rate"] == 50.0
    assert d["auto_submitted_count"] == 0
