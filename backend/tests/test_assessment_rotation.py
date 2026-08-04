"""
Question rotation (LRU) must age only the questions a coder actually received.

_per_coder_pool orders by last_used_at so unseen questions surface first. That
ordering only means something if last_used_at distinguishes questions. The
stamp used to be applied to the whole ELIGIBLE pool at generation time, so a
bank of 40 all aged identically after one 6-question assessment and rotation
degenerated into a plain shuffle — coders kept meeting the same questions.
"""
from conftest import seed_question_pool

from models import AssessmentQuestion

PAYLOAD = {
    "assessment_name": "Rotation Test",
    "coders": [{"coder_name": "Alice", "employee_id": "E001"}],
    "duration_minutes": 60,
    "total_questions": 3,
    "specialty_mix": [{"specialty": "IP-DRG", "pct": 1.0, "topic_filter": ""}],
    "difficulty_mode": "auto",
    "generated_by": "trainer",
    "save_config": False,
    "randomise": True,
}


def _used(db):
    return db.query(AssessmentQuestion).filter(
        AssessmentQuestion.last_used_at.isnot(None)
    ).count()


def test_only_served_questions_are_aged(client, db):
    seed_question_pool(db)
    total = db.query(AssessmentQuestion).count()
    assert total > 3, "seed pool must exceed the paper size for this test to mean anything"

    r = client.post("/assessment/generate", json=PAYLOAD)
    assert r.status_code == 200, r.text
    served = r.json()["total_questions"]

    assert _used(db) == served, (
        f"{_used(db)} of {total} questions were marked used, but only {served} were served"
    )


def test_unserved_questions_stay_unused(client, db):
    seed_question_pool(db)
    client.post("/assessment/generate", json=PAYLOAD)
    db.expire_all()
    untouched = db.query(AssessmentQuestion).filter(
        AssessmentQuestion.last_used_at.is_(None)
    ).count()
    assert untouched > 0, "the rest of the bank must remain first in line for the next paper"
