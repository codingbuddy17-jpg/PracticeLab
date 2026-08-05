"""
Pool Summary answers "can I generate a fair paper from this?", not just
"how many questions exist?".

Readiness is not an absolute count. A 30-question pool is thin for a
25-question paper and generous for a 5-question one, so a fixed "50+ is
healthy" rule answers the wrong question. What decides whether an assessment
survives coders comparing notes is pairwise overlap — how much of their paper
any two of them hold in common.
"""
import pytest

from conftest import make_question


def _pool(client, db, n, specialty="ICD10CM", difficulty="Medium", status="Active"):
    for _ in range(n):
        q = make_question(db, specialty=specialty, difficulty=difficulty)
        q.status = status
    db.commit()


def _summary(client, specialty="ICD10CM", **params):
    r = client.get("/assessment/questions/pool-summary",
                   params={"specialty": specialty, **params})
    assert r.status_code == 200, r.text
    return r.json()


# ── specialty validation ──────────────────────────────────────────────────────

def test_an_unknown_specialty_is_refused_not_reported_as_empty(client, db):
    """Zeroes for a typo read exactly like a real but empty pool."""
    r = client.get("/assessment/questions/pool-summary",
                   params={"specialty": "ICD-10-CM"})   # plausible typo
    assert r.status_code == 400
    assert "Unknown specialty" in r.json()["detail"]


def test_a_known_specialty_with_no_questions_is_a_valid_empty_pool(client, db):
    d = _summary(client)
    assert d["total_active"] == 0
    assert d["total_inactive"] == 0


# ── inactive count ────────────────────────────────────────────────────────────

def test_inactive_questions_are_counted_separately(client, db):
    """Reactivating retired questions is far cheaper than authoring new ones."""
    _pool(client, db, 3)
    _pool(client, db, 7, status="Retired")
    d = _summary(client)
    assert d["total_active"] == 3
    assert d["total_inactive"] == 7


# ── readiness ─────────────────────────────────────────────────────────────────

def test_no_readiness_without_an_intended_paper(client, db):
    """Readiness is meaningless until you say what you are generating."""
    _pool(client, db, 50)
    assert _summary(client)["readiness"] == {}


def test_a_pool_smaller_than_the_paper_is_insufficient(client, db):
    _pool(client, db, 10)
    r = _summary(client, questions_per_paper=25, coders=40)["readiness"]
    assert r["verdict"] == "insufficient"
    assert r["overlap_pct"] is None
    assert "cannot be built" in r["headline"]


def test_a_barely_sufficient_pool_is_flagged_near_identical(client, db):
    """
    30 questions for a 25-question paper passes a naive "25+ is usable" rule,
    but every coder receives nearly the same paper.
    """
    _pool(client, db, 30)
    r = _summary(client, questions_per_paper=25, coders=40)["readiness"]
    assert r["verdict"] == "near_identical"
    assert r["overlap_pct"] == pytest.approx(83.3, abs=0.2)
    assert r["shared_questions"] == pytest.approx(20.8, abs=0.2)


def test_the_same_pool_is_strong_for_a_smaller_paper(client, db):
    """Readiness is relative to the paper, which is the whole point."""
    _pool(client, db, 30)
    r = _summary(client, questions_per_paper=2, coders=40)["readiness"]
    assert r["verdict"] == "strong"


def test_a_generous_pool_reads_as_workable_or_better(client, db):
    _pool(client, db, 250)
    r = _summary(client, questions_per_paper=25, coders=40)["readiness"]
    assert r["verdict"] in ("workable", "strong")
    assert r["overlap_pct"] == pytest.approx(10.0, abs=0.2)


def test_advice_names_a_concrete_target(client, db):
    _pool(client, db, 30)
    r = _summary(client, questions_per_paper=25, coders=40)["readiness"]
    assert str(25 * 4) in r["advice"]
    assert r["pool_for_light_overlap"] == 100
    assert r["pool_for_strong"] == 250


def test_a_single_coder_cannot_overlap_with_anyone(client, db):
    _pool(client, db, 30)
    r = _summary(client, questions_per_paper=25, coders=1)["readiness"]
    assert r["uniqueness_pct"] == 100.0


# ── difficulty outlook ────────────────────────────────────────────────────────

def test_a_lopsided_pool_says_what_an_auto_paper_will_look_like(client, db):
    """Auto mode derives its ratios FROM the pool — it does not refuse."""
    _pool(client, db, 95, difficulty="Easy")
    _pool(client, db, 5, difficulty="Hard")
    d = _summary(client, questions_per_paper=25, coders=10)["difficulty_outlook"]
    assert d["auto_mix_pct"]["Easy"] == 95
    assert any("95% Easy" in n for n in d["notes"])


def test_a_thin_bucket_warns_that_manual_mix_will_cascade(client, db):
    _pool(client, db, 95, difficulty="Easy")
    _pool(client, db, 5, difficulty="Hard")
    d = _summary(client, questions_per_paper=25, coders=10)["difficulty_outlook"]
    assert "Hard" in d["short_buckets"]
    assert "Medium" in d["short_buckets"]
    assert any("filled from the other levels" in n for n in d["notes"])


def test_a_balanced_pool_raises_nothing(client, db):
    for diff in ("Easy", "Medium", "Hard"):
        _pool(client, db, 40, difficulty=diff)
    d = _summary(client, questions_per_paper=25, coders=10)["difficulty_outlook"]
    assert d["short_buckets"] == []
    assert d["notes"] == []
