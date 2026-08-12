"""
Analytics reads the trainer's verdict, and judges each figure against its own bar.

Two defects, both silent, both of the kind that make a screen untrustworthy
rather than obviously broken.

A trainer correction called rescore_session, which rewrites AssessmentResult —
so anything analytics computed from RESULTS already moved, while everything it
recomputed from RESPONSES did not. The tab did not lag corrections uniformly;
its headline disagreed with its own breakdown.

And the report PDFs carried their own hardcoded bars: 90 for a coder's average
regardless of what their papers were actually marked at, and 90 again for a
batch PASS RATE — which is a share of a cohort, not a score, so a batch where
78% of coders passed was reported BELOW TARGET.
"""
import json

import pytest

from conftest import seed_question_pool

from models import AssessmentResponse, AssessmentResult, AssessmentSession, GeneratedAssessmentStudent

PASS = {"passphrase": "test-passphrase"}


def _served_key(db, session_id):
    sess = db.query(AssessmentSession).filter(AssessmentSession.id == session_id).first()
    slot = db.query(GeneratedAssessmentStudent).filter(
        GeneratedAssessmentStudent.id == sess.student_slot_id).first()
    qs = slot.questions_json
    qs = json.loads(qs) if isinstance(qs, str) else qs
    return {i: q["correct_answer"] for i, q in enumerate(qs)}


@pytest.fixture()
def sat(client, db):
    """One coder who answered everything wrong, so any correction is visible."""
    seed_question_pool(db)
    gen = client.post("/assessment/generate", json={
        "assessment_name": "Correctable", "batch_name": "Wave 1",
        "coders": [{"coder_name": "Alice", "employee_id": "E001"}],
        "duration_minutes": 30, "total_questions": 4,
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
        wrong = next(l for l in "ABCD" if l != key[i])
        client.post(f"/assessment/take/{token}/answer", json={
            "question_index": i, "question_id": q["question_id"], "selected_answer": wrong,
        })
    client.post(f"/assessment/take/{token}/submit", json={"auto_submitted": False})
    db.expire_all()
    return gen["assessment_id"], session.id


def _correct_one(client, aid, sid, index=0):
    return client.post(
        f"/assessment/{aid}/session/{sid}/response/{index}/override",
        params=PASS,
        json={"is_correct": True, "reason": "Key was wrong — the distractor is defensible.",
              "trainer_name": "Trainer A"})


# ── the breakdowns move with the correction ──────────────────────────────────

def test_specialty_accuracy_reflects_a_correction(client, db, sat):
    aid, sid = sat
    before = client.get("/assessment/analytics/by-specialty").json()["specialties"]
    assert before[0]["accuracy_pct"] == 0.0, "fixture sanity: everything was wrong"

    _correct_one(client, aid, sid)
    after = client.get("/assessment/analytics/by-specialty").json()["specialties"]
    assert after[0]["accuracy_pct"] > 0.0, "a corrected answer never reached specialty accuracy"


def test_topic_accuracy_reflects_a_correction(client, db, sat):
    aid, sid = sat
    _correct_one(client, aid, sid)
    rows = client.get("/assessment/analytics/by-topic").json()["topics"]
    assert any((r["accuracy_pct"] or 0) > 0 for r in rows), \
        "corrections never reached topic accuracy"


def test_question_accuracy_reflects_a_correction(client, db, sat):
    aid, sid = sat
    _correct_one(client, aid, sid)
    drill = client.get(f"/assessment/analytics/assessment/{aid}").json()
    assert any((q.get("accuracy_pct") or 0) > 0 for q in drill["question_accuracy"]), \
        "corrections never reached the per-question accuracy table"


def test_the_coder_matrix_reflects_a_correction(client, db, sat):
    aid, sid = sat
    _correct_one(client, aid, sid)
    matrix = client.get("/assessment/analytics/coder-matrix").json()
    cells = [v for row in matrix["coders"] for v in (row.get("specialties") or {}).values()]
    assert any((v or 0) > 0 for v in cells), \
        "corrections never reached the coder x specialty matrix"


def test_the_headline_and_the_breakdown_agree(client, db, sat):
    """
    The version of this bug that matters. The result row was rescored and the
    breakdowns were not, so one screen reported two different truths about the
    same coder.
    """
    aid, sid = sat
    _correct_one(client, aid, sid)
    db.expire_all()

    result = db.query(AssessmentResult).filter(AssessmentResult.session_id == sid).first()
    coder = client.get("/assessment/analytics/coder", params={"coder_name": "Alice"}).json()
    assert coder["avg_score"] == result.score_pct


def test_an_unanswered_question_still_does_not_count(client, db, sat):
    """
    Analytics must keep skipping questions that were never answered. Reading
    the override alone would have counted them as wrong and quietly deflated
    every accuracy figure.
    """
    aid, sid = sat
    resp = (db.query(AssessmentResponse)
            .filter(AssessmentResponse.session_id == sid)
            .order_by(AssessmentResponse.question_index).first())
    resp.is_correct = None
    resp.selected_answer = None
    db.commit()

    rows = client.get("/assessment/analytics/by-specialty").json()["specialties"]
    assert sum(r["total_responses"] for r in rows) == 3, \
        "an unanswered question was counted in the denominator"


# ── the PDFs use the right bar, of the right kind ────────────────────────────

def test_the_coder_report_uses_the_papers_own_pass_mark(client, db):
    """
    It hardcoded 90, so a coder sitting an 80% paper was reported against a
    standard they were never marked on — and the PDF disagreed with the screen.
    """
    seed_question_pool(db)
    gen = client.post("/assessment/generate", json={
        "assessment_name": "Refresher", "pass_threshold": 80,
        "coders": [{"coder_name": "Bob", "employee_id": "E9"}],
        "duration_minutes": 30, "total_questions": 2,
        "specialty_mix": [{"specialty": "IP-DRG", "pct": 1.0, "topic_filter": ""}],
        "difficulty_mode": "auto", "generated_by": "t",
        "save_config": False, "randomise": True,
    }).json()
    token = gen["sessions"][0]["session_token"]
    client.post(f"/assessment/take/{token}/start")
    client.post(f"/assessment/take/{token}/submit", json={"auto_submitted": False})

    data = client.get("/assessment/analytics/coder", params={"coder_name": "Bob"}).json()
    assert data["pass_threshold"] == 80.0
    assert data["pass_rate_target"] == 70.0

    r = client.get("/assessment/analytics/coder-report.pdf", params={"coder_name": "Bob"})
    assert r.status_code == 200
    assert r.content[:4] == b"%PDF"


def test_a_batch_pass_rate_is_judged_against_a_rate_target(client, db):
    """
    The units bug, in the batch PDF. A pass RATE is the share of a cohort who
    passed; comparing it to the 90 score bar reported a healthy cohort as
    failing.
    """
    seed_question_pool(db)
    client.post("/assessment/generate", json={
        "assessment_name": "Wave paper", "batch_name": "Wave 1",
        "coders": [{"coder_name": "Alice"}],
        "duration_minutes": 30, "total_questions": 2,
        "specialty_mix": [{"specialty": "IP-DRG", "pct": 1.0, "topic_filter": ""}],
        "difficulty_mode": "auto", "generated_by": "t",
        "save_config": False, "randomise": True,
    })
    data = client.get("/assessment/analytics/batch-drill/Wave 1").json()
    assert data["pass_rate_target"] == 70.0, "the PDF has no rate target to use"
    assert data["default_pass_threshold"] == 90.0
    assert data["pass_rate_target"] < data["default_pass_threshold"], (
        "the two bars must stay distinct — collapsing them is the bug")
