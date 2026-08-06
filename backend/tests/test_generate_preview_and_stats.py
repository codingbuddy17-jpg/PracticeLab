"""
The Generate screen must not tell the trainer something the generator will not do.

Two ways it did. The pool preview parsed topic filters differently from the
generator, so it could report a pool as sufficient when generation would refuse
it. And standalone randomisation stats were computed from invented data rather
than the questions actually assigned, so they reported perfect uniqueness no
matter how much the papers really overlapped.
"""
import pytest

from conftest import make_question


def _q(text, correct="A"):
    return {
        "question_text": text,
        "option_a": "alpha", "option_b": "beta",
        "option_c": "gamma", "option_d": "delta",
        "correct_answer": correct, "difficulty": "Medium",
        "topic": "T", "shuffle_options": False,
    }


def _standalone_payload(n_questions, n_coders, per_paper):
    return {
        "assessment_name": "Standalone",
        "coders": [{"coder_name": f"C{i}", "employee_id": f"E{i}"} for i in range(n_coders)],
        "duration_minutes": 30,
        "total_questions": per_paper,
        "specialty_mix": [],
        "difficulty_mode": "auto",
        "generated_by": "trainer",
        "save_config": False,
        "randomise": True,
        "standalone_questions": [_q(f"Question {i}?") for i in range(n_questions)],
    }


# ── pool preview must agree with generation ───────────────────────────────────

def test_preview_matches_generation_for_multi_topic_rows(client, db):
    """
    A row's topic filter may itself list several topics, meaning "any of these".
    The preview used to split the WHOLE parameter on commas and hand the pieces
    out to specialties by position, so a row filtering "Sepsis, Pneumonia"
    donated "Pneumonia" to the NEXT specialty and counted only Sepsis for
    itself.
    """
    for _ in range(4):
        make_question(db, specialty="ICD10CM", topic="Sepsis")
    for _ in range(3):
        make_question(db, specialty="ICD10CM", topic="Pneumonia")
    for _ in range(5):
        make_question(db, specialty="Surgery", topic="Fractures")
    db.commit()

    r = client.get("/assessment/pool-preview", params=[
        ("specialty", "ICD10CM"), ("specialty", "Surgery"),
        ("topic_filter", "Sepsis,Pneumonia"), ("topic_filter", "Fractures"),
    ])
    assert r.status_code == 200, r.text
    rows = {row["specialty"]: row for row in r.json()}

    # Generation ORs the topics within a row: 4 Sepsis + 3 Pneumonia.
    assert rows["ICD10CM"]["active_count"] == 7
    assert rows["Surgery"]["active_count"] == 5


def test_preview_agrees_with_what_generation_actually_builds(client, db):
    """The preview count and the generated paper must come from the same pool."""
    for _ in range(4):
        make_question(db, specialty="ICD10CM", topic="Sepsis")
    for _ in range(3):
        make_question(db, specialty="ICD10CM", topic="Pneumonia")
    db.commit()

    preview = client.get("/assessment/pool-preview", params=[
        ("specialty", "ICD10CM"), ("topic_filter", "Sepsis,Pneumonia"),
    ]).json()[0]["active_count"]

    r = client.post("/assessment/generate", json={
        "assessment_name": "Matched", "coders": [{"coder_name": "A"}],
        "duration_minutes": 30, "total_questions": preview,
        "specialty_mix": [{"specialty": "ICD10CM", "pct": 1.0,
                           "topic_filter": "Sepsis,Pneumonia"}],
        "difficulty_mode": "auto", "generated_by": "t",
        "save_config": False, "randomise": True,
    })
    assert r.status_code == 200, (
        f"preview said {preview} questions were available, generation disagreed: {r.text}")
    assert r.json()["total_questions"] == preview


def test_a_row_with_no_topic_filter_still_counts_everything(client, db):
    for _ in range(6):
        make_question(db, specialty="ICD10CM", topic="Anything")
    db.commit()
    r = client.get("/assessment/pool-preview", params=[("specialty", "ICD10CM")])
    assert r.json()[0]["active_count"] == 6


# ── standalone randomisation stats must be measured, not invented ─────────────

def test_standalone_stats_reflect_the_questions_actually_assigned(client, db):
    """
    Every coder draws from the same small pool, so their papers must overlap
    heavily. The old code fabricated disjoint id ranges per coder, which are
    unique by construction — it reported flawless randomisation for papers that
    were nearly identical.
    """
    r = client.post("/assessment/generate",
                    json=_standalone_payload(n_questions=6, n_coders=5, per_paper=5))
    assert r.status_code == 200, r.text
    stats = r.json()["randomisation_stats"]

    assert stats, "standalone generation must report randomisation stats"
    assert stats["avg_uniqueness_pct"] < 100.0, (
        "5 coders drawing 5 of 6 questions cannot all hold unique sets — "
        f"got {stats['avg_uniqueness_pct']}%")
    assert stats["total_pool"] == 6


def test_standalone_stats_can_still_report_high_uniqueness_when_earned(client, db):
    """A pool large enough for genuinely distinct papers should say so."""
    r = client.post("/assessment/generate",
                    json=_standalone_payload(n_questions=60, n_coders=3, per_paper=4))
    stats = r.json()["randomisation_stats"]
    assert stats["avg_uniqueness_pct"] > 50.0
    assert stats["total_pool"] == 60


def test_standalone_pool_utilisation_is_real(client, db):
    """3 coders x 4 questions cannot use more of the pool than they were served."""
    r = client.post("/assessment/generate",
                    json=_standalone_payload(n_questions=60, n_coders=3, per_paper=4))
    stats = r.json()["randomisation_stats"]
    assert 0 < stats["pool_utilisation_pct"] <= round(12 / 60 * 100, 1) + 0.1


def test_no_randomisation_still_says_so(client, db):
    payload = _standalone_payload(n_questions=10, n_coders=3, per_paper=4)
    payload["randomise"] = False
    stats = client.post("/assessment/generate", json=payload).json()["randomisation_stats"]
    assert stats["avg_uniqueness_pct"] == 0.0


# ── identities that cannot be told apart afterwards ───────────────────────────

def _standard(coders, mix=None):
    return {
        "assessment_name": "Standard", "coders": coders,
        "duration_minutes": 30, "total_questions": 2,
        "specialty_mix": mix or [{"specialty": "ICD10CM", "pct": 1.0, "topic_filter": ""}],
        "difficulty_mode": "auto", "generated_by": "t",
        "save_config": False, "randomise": True,
    }


def test_two_coders_with_the_same_identity_are_refused(client, db):
    """Analytics groups on employee id falling back to name, so these merge."""
    r = client.post("/assessment/generate", json=_standard(
        [{"coder_name": "Alice"}, {"coder_name": "alice"}]))
    assert r.status_code == 400
    assert "twice" in r.json()["detail"]


def test_the_same_name_with_different_ids_is_allowed(client, db):
    """Two real people can share a name; the id is what tells them apart."""
    for _ in range(4):
        make_question(db, specialty="ICD10CM")
    db.commit()
    r = client.post("/assessment/generate", json=_standard(
        [{"coder_name": "Alice", "employee_id": "E001"},
         {"coder_name": "Alice", "employee_id": "E002"}]))
    assert r.status_code == 200, r.text
    assert r.json()["coder_count"] == 2


def test_a_repeated_employee_id_is_refused(client, db):
    r = client.post("/assessment/generate", json=_standard(
        [{"coder_name": "Alice", "employee_id": "E001"},
         {"coder_name": "Bob", "employee_id": "E001"}]))
    assert r.status_code == 400


def test_a_repeated_specialty_row_is_refused(client, db):
    """One pool split across two rows passes each row's shortfall check twice."""
    r = client.post("/assessment/generate", json=_standard(
        [{"coder_name": "Alice"}],
        mix=[{"specialty": "ICD10CM", "pct": 0.5, "topic_filter": ""},
             {"specialty": "ICD10CM", "pct": 0.5, "topic_filter": "Sepsis"}]))
    assert r.status_code == 400
    assert "more than once" in r.json()["detail"]


# ── topic suggestions ─────────────────────────────────────────────────────────

def test_preview_lists_the_topics_the_specialty_actually_has(client, db):
    """
    A trainer typing a topic from memory cannot know what the bank calls it.
    "Sepsis" against a bank storing "Sepsis & Shock" returns nothing and looks
    like an empty pool rather than a spelling mismatch.
    """
    for _ in range(4):
        make_question(db, specialty="ICD10CM", topic="Sepsis & Shock")
    for _ in range(2):
        make_question(db, specialty="ICD10CM", topic="Diabetes")
    db.commit()

    row = client.get("/assessment/pool-preview", params=[("specialty", "ICD10CM")]).json()[0]
    assert row["topics"] == [
        {"topic": "Sepsis & Shock", "count": 4},
        {"topic": "Diabetes", "count": 2},
    ]


def test_topic_suggestions_ignore_the_current_filter(client, db):
    """
    The list is what you could pick, not what you have picked — filtering it by
    the current filter would leave a trainer unable to widen their choice.
    """
    for _ in range(3):
        make_question(db, specialty="ICD10CM", topic="Sepsis")
    for _ in range(3):
        make_question(db, specialty="ICD10CM", topic="Diabetes")
    db.commit()

    row = client.get("/assessment/pool-preview", params=[
        ("specialty", "ICD10CM"), ("topic_filter", "Sepsis"),
    ]).json()[0]
    assert row["active_count"] == 3          # the filter still narrows the count
    assert len(row["topics"]) == 2           # but not the suggestions
