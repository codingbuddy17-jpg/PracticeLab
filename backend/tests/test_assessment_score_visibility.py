"""
A coder sees their assessment mark only when the trainer turned it on.

Before this the submit endpoint returned a fixed sentence and nothing else, so
"your trainer will share your results" was the whole design rather than one of
two options. PracticeLab (show_results_to_coder) and the auditor module
(show_results_to_auditor) had both had the switch for a long time; the MCQ
paper was the odd one out.

Off is the default, and these tests assert that from the payload rather than
from the column, because a default that is only correct in the model is one
`req.show_results_to_coder or True` away from being wrong on the wire.
"""
import json

import pytest

from conftest import seed_question_pool

from models import AssessmentSession, GeneratedAssessment, GeneratedAssessmentStudent


def _sit(client, db, *, show, threshold=90, answer_correctly=True):
    """Generate a one-coder paper, sit it, and return the submit payload."""
    seed_question_pool(db)
    body = {
        "assessment_name": "Visibility", "batch_name": "W1",
        "coders": [{"coder_name": "Alice", "employee_id": "E001"}],
        "duration_minutes": 30, "total_questions": 4,
        "specialty_mix": [{"specialty": "IP-DRG", "pct": 1.0, "topic_filter": ""}],
        "difficulty_mode": "auto", "generated_by": "t",
        "save_config": False, "randomise": True,
        "pass_threshold": threshold,
    }
    if show is not None:
        body["show_results_to_coder"] = show
    gen = client.post("/assessment/generate", json=body).json()
    token = gen["sessions"][0]["session_token"]
    started = client.post(f"/assessment/take/{token}/start").json()

    sess = db.query(AssessmentSession).filter(
        AssessmentSession.session_token == token).first()
    slot = db.query(GeneratedAssessmentStudent).filter(
        GeneratedAssessmentStudent.id == sess.student_slot_id).first()
    qs = slot.questions_json
    qs = json.loads(qs) if isinstance(qs, str) else qs
    key = {i: q["correct_answer"] for i, q in enumerate(qs)}

    for i, q in enumerate(started["questions"]):
        pick = key[i] if answer_correctly else next(l for l in "ABCD" if l != key[i])
        client.post(f"/assessment/take/{token}/answer", json={
            "question_index": i, "question_id": q["question_id"], "selected_answer": pick,
        })
    out = client.post(f"/assessment/take/{token}/submit",
                      json={"auto_submitted": False}).json()
    return token, out, gen["assessment_id"]


def test_off_by_default_when_the_trainer_says_nothing(client, db):
    """The generate payload omits the field entirely — the old caller."""
    _, out, aid = _sit(client, db, show=None)
    assert out["result"] is None
    assert "trainer will share" in out["message"]
    paper = db.query(GeneratedAssessment).filter(GeneratedAssessment.id == aid).first()
    assert paper.show_results_to_coder is False


def test_off_explicitly_still_shows_nothing(client, db):
    _, out, _ = _sit(client, db, show=False)
    assert out["result"] is None


def test_on_returns_the_mark_and_the_papers_own_bar(client, db):
    _, out, _ = _sit(client, db, show=True, threshold=75, answer_correctly=True)
    r = out["result"]
    assert r is not None
    assert r["score_pct"] == 100.0
    assert r["correct_count"] == r["total_questions"] == 4
    # The paper's bar, not a module constant of 90.
    assert r["pass_threshold"] == 75
    assert r["passed"] is True
    # The sentence loses its promise when the mark is right there.
    assert "trainer will share" not in out["message"]


def test_a_failing_mark_is_reported_as_such(client, db):
    _, out, _ = _sit(client, db, show=True, threshold=75, answer_correctly=False)
    assert out["result"]["score_pct"] == 0.0
    assert out["result"]["passed"] is False


def test_no_pass_mark_is_NA_and_never_a_fail(client, db):
    """`NA` is a real value and is not a failure — see CLAUDE.md."""
    _, out, _ = _sit(client, db, show=True, threshold=None, answer_correctly=True)
    assert out["result"]["pass_threshold"] is None
    assert out["result"]["passed"] is None


def test_reopening_the_link_shows_the_same_thing(client, db):
    """A coder who closed the tab gets their mark back, not less."""
    token, out, _ = _sit(client, db, show=True, threshold=75)
    info = client.get(f"/assessment/take/{token}").json()
    assert info["status"] == "submitted"
    assert info["result"] == out["result"]


def test_reopening_shows_nothing_when_the_switch_is_off(client, db):
    token, _, _ = _sit(client, db, show=False)
    info = client.get(f"/assessment/take/{token}").json()
    assert info.get("result") is None


def test_the_answers_never_travel_with_the_score(client, db):
    """
    The mark, not the paper. Questions are reused across cohorts, so a coder
    who can read the key from their own result screen breaks every later sitting.
    """
    _, out, _ = _sit(client, db, show=True)
    blob = json.dumps(out)
    assert "correct_answer" not in blob
    assert "option_a" not in blob
    assert set(out["result"].keys()) == {
        "score_pct", "correct_count", "total_questions", "pass_threshold", "passed"}
