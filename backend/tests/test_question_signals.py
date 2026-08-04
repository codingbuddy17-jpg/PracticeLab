"""
Question Signals measures the paper rather than the coders.

The load-bearing detail is that options are shuffled per coder, so the stored
selected_answer letter means something different for each of them. Aggregating
letters would spread four coders who all picked the SAME wrong text across four
different letters — an even 25% split on every question, which reads as "no
pattern here" no matter how misleading the question actually is.
"""
import json

from sqlalchemy import text as sql_text

from conftest import make_question, seed_question_pool

from models import AssessmentSession, GeneratedAssessmentStudent


def _payload(name, coders, n=1):
    return {
        "assessment_name": name,
        "coders": coders,
        "duration_minutes": 60,
        "total_questions": n,
        "specialty_mix": [{"specialty": "IP-DRG", "pct": 1.0, "topic_filter": ""}],
        "difficulty_mode": "auto",
        "generated_by": "trainer",
        "save_config": False,
        "randomise": True,
    }


def _slot_q(db, token):
    s = db.query(AssessmentSession).filter(
        AssessmentSession.session_token == token).first()
    slot = db.query(GeneratedAssessmentStudent).filter(
        GeneratedAssessmentStudent.id == s.student_slot_id).first()
    qs = slot.questions_json
    return json.loads(qs) if isinstance(qs, str) else qs


def _answer_text(client, db, token, wanted_text):
    """
    Answer with whichever letter maps to `wanted_text` FOR THIS CODER.
    Returns the letters used, so a test can prove the shuffle really varied
    them rather than assuming it did.
    """
    started = client.post(f"/assessment/take/{token}/start").json()
    letters = []
    for i, q in enumerate(started["questions"]):
        letter = next(l for l in "ABCD" if q[f"option_{l.lower()}"] == wanted_text)
        letters.append(letter)
        client.post(f"/assessment/take/{token}/answer", json={
            "question_index": i, "question_id": q["question_id"], "selected_answer": letter,
        })
    client.post(f"/assessment/take/{token}/submit", json={"auto_submitted": False})
    return letters


def _signals(client, **params):
    r = client.get("/assessment/analytics/question-signals", params=params)
    assert r.status_code == 200, r.text
    return r.json()


def test_everyone_choosing_the_same_wrong_text_shows_as_one_distractor(client, db):
    """
    Six coders all pick "Option C". Under a per-coder shuffle their stored
    letters differ, so counting letters would scatter them. Counting text must
    show one distractor at 100%.
    """
    make_question(db, specialty="IP-DRG")
    db.commit()
    # Twelve rather than six: with four options the chance that every coder
    # happens to receive the same arrangement is then negligible, so a
    # letter-counting regression cannot slip past on a lucky shuffle.
    coders = [{"coder_name": f"C{i}", "employee_id": f"E{i}"} for i in range(12)]
    gen = client.post("/assessment/generate", json=_payload("Trap", coders)).json()
    used = []
    for s in gen["sessions"]:
        used += _answer_text(client, db, s["session_token"], "Option C")

    assert len(set(used)) > 1, (
        "the shuffle gave every coder the same letter, so this run proves nothing"
    )

    q = _signals(client)["questions"][0]
    assert q["attempts"] == 12
    assert q["accuracy_pct"] == 0.0
    assert len(q["options"]) == 1, f"letters were counted, not text: {q['options']}"
    assert q["top_distractor"]["text"] == "Option C"
    assert q["top_distractor"]["pct"] == 100.0


def test_a_wrong_option_beating_the_answer_is_flagged_misleading(client, db):
    make_question(db, specialty="IP-DRG")
    db.commit()
    coders = [{"coder_name": f"C{i}", "employee_id": f"E{i}"} for i in range(6)]
    gen = client.post("/assessment/generate", json=_payload("Trap", coders)).json()
    for i, s in enumerate(gen["sessions"]):
        # Two get it right, four take the same bait.
        _answer_text(client, db, s["session_token"],
                     "Option A" if i < 2 else "Option C")

    q = _signals(client)["questions"][0]
    assert q["misleading"] is True
    assert q["signal"] == "misleading"


def test_an_easy_question_is_flagged_as_no_longer_measuring(client, db):
    make_question(db, specialty="IP-DRG")
    db.commit()
    coders = [{"coder_name": f"C{i}", "employee_id": f"E{i}"} for i in range(6)]
    gen = client.post("/assessment/generate", json=_payload("Easy", coders)).json()
    for s in gen["sessions"]:
        _answer_text(client, db, s["session_token"], "Option A")   # the correct text

    q = _signals(client)["questions"][0]
    assert q["accuracy_pct"] == 100.0
    assert q["signal"] == "too_easy"


def test_thin_questions_are_withheld_not_ranked(client, db):
    """
    One coder getting a question wrong is not a signal. Those questions are
    counted so the trainer knows they exist, but never ranked as if 0% on a
    single attempt meant the same as 0% on fifty.
    """
    make_question(db, specialty="IP-DRG")
    db.commit()
    gen = client.post("/assessment/generate", json=_payload(
        "Thin", [{"coder_name": "Solo", "employee_id": "E1"}])).json()
    _answer_text(client, db, gen["sessions"][0]["session_token"], "Option C")

    d = _signals(client)
    assert d["questions"] == []
    assert d["summary"]["too_few_attempts"] == 1

    # ...and it appears once the bar is lowered to meet it.
    d2 = _signals(client, min_attempts=1)
    assert len(d2["questions"]) == 1


def test_signals_honour_the_window(client, db):
    seed_question_pool(db)
    for batch in ("Wave 1", "Wave 2"):
        p = _payload(f"{batch} paper",
                     [{"coder_name": f"C-{batch}", "employee_id": batch}], n=3)
        p["batch_name"] = batch
        gen = client.post("/assessment/generate", json=p).json()
        token = gen["sessions"][0]["session_token"]
        started = client.post(f"/assessment/take/{token}/start").json()
        for i, q in enumerate(started["questions"]):
            client.post(f"/assessment/take/{token}/answer", json={
                "question_index": i, "question_id": q["question_id"], "selected_answer": "A",
            })
        client.post(f"/assessment/take/{token}/submit", json={"auto_submitted": False})

    wide = _signals(client, min_attempts=1)["summary"]["scored"]
    narrow = _signals(client, min_attempts=1, batch_name="Wave 1")["summary"]["scored"]
    assert narrow <= wide
    assert narrow > 0
