"""
A standalone question's id is only unique inside its own paper.

Standalone questions never enter the bank, so they have no bank id and are
given one at generation: SA-0001, SA-0002 — numbered by position WITHIN that
assessment. Two standalone papers therefore both contain an SA-0001, and the
analytics maps were keyed on the question id alone.

The two halves of the module then disagreed about which one won. batch-drill
kept the first it saw; _build_response_meta — which feeds By Specialty, By
Topic and the Coder Matrix — kept the last. So the same responses were
attributed to two different topics on two tabs sitting next to each other, and
neither was reliably right.

Keyed on (assessment_id, question_id) the ambiguity disappears, and it
disappears for papers already in the database — renumbering at generation would
only have fixed the ones not yet created.
"""
import json

import pytest

from models import AssessmentSession, GeneratedAssessmentStudent


def _standalone(client, db, name, topic, batch="Wave 1", answer="A"):
    """A one-question standalone assessment. Its question will be SA-0001."""
    gen = client.post("/assessment/generate", json={
        "assessment_name": name,
        "batch_name": batch,
        "coders": [{"coder_name": f"Coder {name}", "employee_id": f"E{name[-1]}"}],
        "duration_minutes": 30,
        "total_questions": 1,
        "specialty_mix": [],
        "difficulty_mode": "auto",
        "generated_by": "trainer",
        "save_config": False,
        "randomise": False,
        "standalone_questions": [{
            "question_text": f"Question for {topic}?",
            "option_a": "Right", "option_b": "Wrong", "option_c": "No", "option_d": "Nope",
            "correct_answer": "A",
            "specialty": "IP-DRG",
            "topic": topic,
            "difficulty": "Medium",
            "shuffle_options": False,
        }],
    })
    assert gen.status_code == 200, gen.text
    body = gen.json()

    token = body["sessions"][0]["session_token"]
    started = client.post(f"/assessment/take/{token}/start").json()
    q = started["questions"][0]
    client.post(f"/assessment/take/{token}/answer", json={
        "question_index": 0, "question_id": q["question_id"], "selected_answer": answer,
    })
    client.post(f"/assessment/take/{token}/submit", json={"auto_submitted": False})
    db.expire_all()
    return body


@pytest.fixture()
def two_standalone_papers(client, db):
    """
    Two standalone papers in one batch, on different topics. One coder answers
    correctly, the other does not, so a mis-attribution is visible as a score
    landing under the wrong topic.
    """
    a = _standalone(client, db, "Paper A", "Sepsis", answer="A")     # correct
    b = _standalone(client, db, "Paper B", "Fractures", answer="B")  # wrong
    return a, b


def test_the_two_papers_really_do_share_a_question_id(client, db, two_standalone_papers):
    """
    Fixture sanity — without this collision the rest of the file proves nothing.
    """
    ids = set()
    for slot in db.query(GeneratedAssessmentStudent).all():
        qs = slot.questions_json
        qs = json.loads(qs) if isinstance(qs, str) else qs
        for q in qs:
            ids.add(q["question_id"])
    assert ids == {"SA-0001"}, f"expected a shared id, got {ids}"


# ── the attribution ──────────────────────────────────────────────────────────

def test_each_topic_gets_its_own_result(client, db, two_standalone_papers):
    """
    One coder got their question right and the other got theirs wrong, on
    different topics. Collapsed onto a single id, both responses land under
    whichever topic won and the other topic vanishes entirely.
    """
    topics = client.get("/assessment/analytics/by-topic").json()["topics"]
    by_name = {t["topic"]: t for t in topics}

    assert "Sepsis" in by_name, "a whole topic disappeared into the other one"
    assert "Fractures" in by_name, "a whole topic disappeared into the other one"
    assert by_name["Sepsis"]["accuracy_pct"] == 100.0
    assert by_name["Fractures"]["accuracy_pct"] == 0.0


def test_the_batch_drill_agrees_with_the_topic_tab(client, db, two_standalone_papers):
    """
    The two halves used opposite tie-breaks — first-wins in the drill,
    last-wins in the shared meta — so the same data read differently on two
    tabs beside each other. Whatever they say, they must say it together.
    """
    topics = {t["topic"]: t["accuracy_pct"]
              for t in client.get("/assessment/analytics/by-topic").json()["topics"]}
    drill = client.get("/assessment/analytics/batch-drill/Wave 1").json()

    assert set(drill["all_topics"]) == set(topics), \
        "the drill and the topic tab do not even agree on which topics exist"


def test_specialty_totals_still_count_every_response(client, db, two_standalone_papers):
    """A collision must not lose responses, whichever way it resolves."""
    specialties = client.get("/assessment/analytics/by-specialty").json()["specialties"]
    assert sum(s["total_responses"] for s in specialties) == 2


# ── nothing moves for bank questions, which never collided ───────────────────

def test_bank_questions_are_unaffected(client, db):
    """
    Bank ids are globally unique, so composite keying must leave them reading
    exactly as before — this is the regression half of the change.
    """
    from conftest import seed_question_pool

    seed_question_pool(db)
    gen = client.post("/assessment/generate", json={
        "assessment_name": "Bank paper", "batch_name": "Wave 2",
        "coders": [{"coder_name": "Alice", "employee_id": "E9"}],
        "duration_minutes": 30, "total_questions": 2,
        "specialty_mix": [{"specialty": "IP-DRG", "pct": 1.0, "topic_filter": ""}],
        "difficulty_mode": "auto", "generated_by": "t",
        "save_config": False, "randomise": True,
    }).json()
    token = gen["sessions"][0]["session_token"]
    started = client.post(f"/assessment/take/{token}/start").json()
    for i, q in enumerate(started["questions"]):
        client.post(f"/assessment/take/{token}/answer", json={
            "question_index": i, "question_id": q["question_id"], "selected_answer": "A",
        })
    client.post(f"/assessment/take/{token}/submit", json={"auto_submitted": False})

    specialties = client.get("/assessment/analytics/by-specialty").json()["specialties"]
    assert [s["specialty"] for s in specialties] == ["IP-DRG"]
    assert specialties[0]["total_responses"] == 2

    topics = client.get("/assessment/analytics/by-topic").json()["topics"]
    assert sum(t["total_responses"] for t in topics) == 2

    matrix = client.get("/assessment/analytics/coder-matrix").json()
    assert matrix["coders"][0]["coder_name"] == "Alice"
    assert "IP-DRG" in matrix["coders"][0]["specialties"]
