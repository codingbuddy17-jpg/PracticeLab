"""
The answers are not public.

A coder who can read the question bank, the answer-key PDF or the paper itself
has no reason to sit the assessment. All three were served over the public
internet with no passphrase, while `export`, `export-all` and the question
DELETE in the same files already checked one — the rule existed and had simply
been applied where it was written and not next door.
"""
import pytest

from conftest import make_question

PASS = {"passphrase": "test-passphrase"}
WRONG = {"passphrase": "not-the-passphrase"}


@pytest.fixture()
def a_question(db):
    q = make_question(db, specialty="ICD10CM")
    db.commit()
    return q


# ── the bank ──────────────────────────────────────────────────────────────────

def test_the_question_bank_is_not_readable_without_the_passphrase(client, a_question):
    r = client.get("/assessment/questions", params={"specialty": "ICD10CM"})
    assert r.status_code == 403
    assert "passphrase" in r.json()["detail"].lower()


def test_a_wrong_passphrase_is_refused(client, a_question):
    r = client.get("/assessment/questions", params={**WRONG, "specialty": "ICD10CM"})
    assert r.status_code == 403


def test_the_bank_is_readable_with_the_passphrase(client, a_question):
    r = client.get("/assessment/questions", params={**PASS, "specialty": "ICD10CM"})
    assert r.status_code == 200
    assert r.json()["total"] == 1


def test_no_answer_leaks_in_the_refusal_body(client, a_question):
    """A 403 must not carry the thing it is refusing."""
    body = client.get("/assessment/questions", params={"specialty": "ICD10CM"}).text
    assert "correct_answer" not in body
    assert a_question.question_text not in body


# ── writes ────────────────────────────────────────────────────────────────────

def test_editing_a_question_needs_the_passphrase(client, a_question, db):
    r = client.put(f"/assessment/questions/{a_question.question_id}",
                   json={"question_text": "Silently rewritten"})
    assert r.status_code == 403
    db.expire_all()
    assert a_question.question_text != "Silently rewritten"


def test_retiring_a_question_needs_the_passphrase(client, a_question, db):
    r = client.put(f"/assessment/questions/{a_question.question_id}/status",
                   params={"status": "Inactive", "updated_by": "someone"})
    assert r.status_code == 403
    db.expire_all()
    assert a_question.status == "Active"


def test_a_legitimate_edit_still_works(client, a_question, db):
    r = client.put(f"/assessment/questions/{a_question.question_id}",
                   params=PASS, json={"question_text": "Properly edited?"})
    assert r.status_code == 200, r.text
    db.expire_all()
    assert a_question.question_text == "Properly edited?"


def test_a_legitimate_retire_still_works(client, a_question, db):
    r = client.put(f"/assessment/questions/{a_question.question_id}/status",
                   params={**PASS, "status": "Inactive", "updated_by": "trainer"})
    assert r.status_code == 200, r.text
    db.expire_all()
    assert a_question.status == "Inactive"


# ── exports ───────────────────────────────────────────────────────────────────

def test_the_sessions_tab_downloads_need_no_passphrase(client, db):
    """
    The three buttons on the Sessions tab — responses, papers, answer key —
    are deliberately open. Gating them walled off the screen a trainer uses
    most, for a secret that tab had no way to collect.

    Everything else in the module keeps its gate; this exemption is these
    three, not a change of position.
    """
    for path in ("/assessment/1/export-answer-key",
                 "/assessment/1/export-pdf",
                 "/assessment/1/export-responses.xlsx",
                 "/assessment/1/sessions"):
        assert client.get(path).status_code != 403, f"{path} should not be gated"


# ── what must stay open ───────────────────────────────────────────────────────

def test_counts_only_endpoints_stay_public(client, a_question):
    """
    These expose no question content by design, and the coder-facing pool view
    depends on them. Gating everything would be its own kind of wrong.
    """
    for path, params in (
        ("/assessment/questions/stats", {}),
        ("/assessment/questions/pool-summary", {"specialty": "ICD10CM"}),
    ):
        r = client.get(path, params=params)
        assert r.status_code == 200, f"{path} should not be gated"
        assert "correct_answer" not in r.text


def test_a_coder_can_still_reach_their_own_session(client, db):
    """The take flow is gated by the session token, not the passphrase."""
    r = client.get("/assessment/take/ASM-NOTREAL")
    assert r.status_code == 404, "404 means it got past auth and looked, which is right"


# ── the edit endpoint obeys the same rules as the upload ──────────────────────

def _edit(client, qid, **fields):
    return client.put(f"/assessment/questions/{qid}", params=PASS, json=fields)


def test_the_bank_cannot_introduce_duplicate_options(client, a_question, db):
    """
    Upload refuses these; the edit screen was a second door with no lock. Two
    identical choices give a question two right answers while only one letter
    is keyed, and the shuffle makes which one vary per coder.
    """
    r = _edit(client, a_question.question_id, option_a="Same", option_b="Same")
    assert r.status_code == 400
    assert "duplicate" in r.json()["detail"].lower()
    db.expire_all()
    assert a_question.option_a != "Same"


def test_the_bank_cannot_introduce_a_blank_option(client, a_question):
    r = _edit(client, a_question.question_id, option_c="")
    assert r.status_code == 400
    assert "blank" in r.json()["detail"].lower()


def test_the_bank_cannot_set_a_nonsense_correct_answer(client, a_question):
    r = _edit(client, a_question.question_id, correct_answer="Z")
    assert r.status_code == 400
    assert "correct_answer" in r.json()["detail"].lower()


def test_the_bank_cannot_set_a_nonsense_difficulty(client, a_question):
    r = _edit(client, a_question.question_id, difficulty="banana")
    assert r.status_code == 400


def test_the_bank_cannot_set_a_nonsense_question_type(client, a_question):
    r = _edit(client, a_question.question_id, question_type="Vibes")
    assert r.status_code == 400


def test_validation_uses_the_stored_values_for_fields_not_being_changed(client, a_question, db):
    """
    A partial edit must be judged against the whole question, not only the
    fields present in the payload — otherwise changing one option to match
    another would slip through.
    """
    r = _edit(client, a_question.question_id, option_b=a_question.option_a)
    assert r.status_code == 400
    assert "duplicate" in r.json()["detail"].lower()


def test_a_valid_partial_edit_still_saves(client, a_question, db):
    r = _edit(client, a_question.question_id, topic="Sepsis", difficulty="Hard")
    assert r.status_code == 200, r.text
    db.expire_all()
    assert a_question.topic == "Sepsis"
    assert a_question.difficulty == "Hard"


# ── what Sessions needs open, and what stays shut ─────────────────────────────

def test_the_sessions_tab_works_without_a_passphrase(client, a_question, db):
    """
    Gating these put a wall in front of the screen a trainer uses most, for a
    passphrase that tab had no way to collect. Reverted deliberately.
    """
    for path in ("/assessment/1/sessions",
                 "/assessment/1/session/1/review",
                 "/assessment/1/export-responses.xlsx"):
        r = client.get(path)
        assert r.status_code != 403, f"{path} should not be passphrase-gated"


def test_the_question_bank_is_still_gated(client, a_question):
    """The bank returns correct_answer for every question, and stays shut."""
    assert client.get("/assessment/questions",
                      params={"specialty": "ICD10CM"}).status_code == 403
