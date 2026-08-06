"""
The response export must describe the same result as the screen.

Two ways it did not. It looked each coder's paper up by NAME, so two coders
sharing one had their answers graded against a paper they never sat. And it
re-compared the letters itself instead of reading the recorded verdict, so a
trainer's correction never reached the spreadsheet — the export contradicted
the score printed in its own row.
"""
import io
import json

import openpyxl

from conftest import seed_question_pool

from models import AssessmentSession, GeneratedAssessmentStudent

PASS = {"passphrase": "test-passphrase"}


def _generate(client, db, coders, n=3):
    seed_question_pool(db)
    return client.post("/assessment/generate", json={
        "assessment_name": "Export", "coders": coders,
        "duration_minutes": 30, "total_questions": n,
        "specialty_mix": [{"specialty": "IP-DRG", "pct": 1.0, "topic_filter": ""}],
        "difficulty_mode": "auto", "generated_by": "t",
        "save_config": False, "randomise": True,
    }).json()


def _key(db, session_id):
    sess = db.query(AssessmentSession).filter(AssessmentSession.id == session_id).first()
    slot = db.query(GeneratedAssessmentStudent).filter(
        GeneratedAssessmentStudent.id == sess.student_slot_id).first()
    qs = slot.questions_json
    return [q for q in (json.loads(qs) if isinstance(qs, str) else qs)]


def _sit(client, db, token, all_correct=True):
    started = client.post(f"/assessment/take/{token}/start").json()
    sess = db.query(AssessmentSession).filter(
        AssessmentSession.session_token == token).first()
    key = _key(db, sess.id)
    for i, q in enumerate(started["questions"]):
        right = key[i]["correct_answer"]
        ans = right if all_correct else next(l for l in "ABCD" if l != right)
        client.post(f"/assessment/take/{token}/answer", json={
            "question_index": i, "question_id": q["question_id"], "selected_answer": ans,
        })
    client.post(f"/assessment/take/{token}/submit", json={"auto_submitted": False})
    return sess.id


def _sheet_text(client, aid):
    r = client.get(f"/assessment/{aid}/export-responses.xlsx", params=PASS)
    assert r.status_code == 200, r.text
    ws = openpyxl.load_workbook(io.BytesIO(r.content)).active
    return ["\t".join(str(c) for c in row if c is not None)
            for row in ws.iter_rows(values_only=True)]


def test_same_named_coders_get_their_own_papers(client, db):
    """
    The lookup was by name, so one of two Alices was graded against the other's
    paper. Their question sets differ under per-coder randomisation.
    """
    gen = _generate(client, db, [
        {"coder_name": "Alice", "employee_id": "E001"},
        {"coder_name": "Alice", "employee_id": "E002"},
    ])
    for s in gen["sessions"]:
        _sit(client, db, s["session_token"], all_correct=True)

    rows = _sheet_text(client, gen["assessment_id"])
    body = [r for r in rows if "Alice" in r]
    assert len(body) == 2
    # Both answered every question correctly against their OWN paper.
    for r in body:
        assert "✗ Wrong" not in r, f"a coder was graded against someone else's paper: {r}"


def test_a_trainer_correction_reaches_the_export(client, db):
    """The spreadsheet must not contradict the score in its own row."""
    gen = _generate(client, db, [{"coder_name": "Bob", "employee_id": "E9"}])
    sid = _sit(client, db, gen["sessions"][0]["session_token"], all_correct=False)
    aid = gen["assessment_id"]

    before = _sheet_text(client, aid)
    assert any("✗ Wrong" in r for r in before)

    client.post(f"/assessment/{aid}/session/{sid}/response/0/override", params=PASS,
                json={"is_correct": True, "reason": "Key was wrong on this one.",
                      "trainer_name": "Trainer A"})

    after = _sheet_text(client, aid)
    joined = "\n".join(after)
    assert "corrected" in joined, "the export must show the answer was corrected"
    assert joined.count("✗ Wrong") == "\n".join(before).count("✗ Wrong") - 1


def test_the_export_does_not_require_a_passphrase(client, db):
    """
    Deliberately open, unlike the answer-key export.

    Gating the whole Sessions tab put a wall in front of the screen a trainer
    uses most, for a passphrase the tab had no way to collect. The answer key
    and the papers stay gated because they hand over the exam itself; this is a
    record of what coders already answered.
    """
    gen = _generate(client, db, [{"coder_name": "Bob"}])
    _sit(client, db, gen["sessions"][0]["session_token"])
    r = client.get(f"/assessment/{gen['assessment_id']}/export-responses.xlsx")
    assert r.status_code == 200
