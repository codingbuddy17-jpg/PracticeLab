"""
Standalone assessments must score per question, not per question_id collision.

Standalone questions are supplied inline by the trainer and never enter the
question bank, so they carry no bank ID. They were all written with
question_id=None, which meant the submit path's {question_id: correct_answer}
map held exactly one entry no matter how many questions were served — every
response was graded against whichever question happened to be last.
"""
import json

import pytest

from models import (
    AssessmentSession, AssessmentResult, GeneratedAssessmentStudent,
)

# Four questions whose correct answers differ, so a collapsed map cannot
# accidentally produce the right score.
def _q(text, correct):
    return {
        "question_text": text,
        "option_a": "alpha", "option_b": "beta",
        "option_c": "gamma", "option_d": "delta",
        "correct_answer": correct,
        "difficulty": "Medium",
        "topic": "Mixed",
        "shuffle_options": False,   # keep the served letters predictable
    }


PAYLOAD = {
    "assessment_name": "Standalone Scoring",
    "coders": [{"coder_name": "Alice", "employee_id": "E001"}],
    "duration_minutes": 30,
    "total_questions": 4,
    "specialty_mix": [],
    "difficulty_mode": "auto",
    "generated_by": "trainer",
    "save_config": False,
    "randomise": False,
    "standalone_questions": [
        _q("Q1", "A"), _q("Q2", "B"), _q("Q3", "C"), _q("Q4", "D"),
    ],
}


def _generate(client):
    r = client.post("/assessment/generate", json=PAYLOAD)
    assert r.status_code == 200, r.text
    return r.json()["sessions"][0]["session_token"]


def _served(db, token):
    session = db.query(AssessmentSession).filter(
        AssessmentSession.session_token == token
    ).first()
    slot = db.query(GeneratedAssessmentStudent).filter(
        GeneratedAssessmentStudent.id == session.student_slot_id
    ).first()
    qs = slot.questions_json
    return session, (json.loads(qs) if isinstance(qs, str) else qs)


def _result(db, session):
    return db.query(AssessmentResult).filter(
        AssessmentResult.session_id == session.id
    ).first()


def test_standalone_questions_get_distinct_ids(client, db):
    token = _generate(client)
    _, questions = _served(db, token)
    ids = [q["question_id"] for q in questions]
    assert len(set(ids)) == len(ids) == 4
    assert all(i for i in ids), "no standalone question may carry a null id"


def test_all_correct_scores_100(client, db):
    token = _generate(client)
    session, questions = _served(db, token)
    client.post(f"/assessment/take/{token}/start")
    for i, q in enumerate(questions):
        client.post(f"/assessment/take/{token}/answer", json={
            "question_index": i,
            "question_id": q["question_id"],
            "selected_answer": q["correct_answer"],
        })
    client.post(f"/assessment/take/{token}/submit", json={"auto_submitted": False})
    assert _result(db, session).score_pct == pytest.approx(100.0, abs=0.1)


def test_partial_answers_score_partially(client, db):
    """
    Answer every question 'A'. Only Q1 is correct, so 25%. Under the collapsed
    map this returned 0% or 100% depending on which question won the key.
    """
    token = _generate(client)
    session, questions = _served(db, token)
    client.post(f"/assessment/take/{token}/start")
    for i, q in enumerate(questions):
        client.post(f"/assessment/take/{token}/answer", json={
            "question_index": i,
            "question_id": q["question_id"],
            "selected_answer": "A",
        })
    client.post(f"/assessment/take/{token}/submit", json={"auto_submitted": False})
    result = _result(db, session)
    assert result.correct_count == 1
    assert result.score_pct == pytest.approx(25.0, abs=0.1)
