"""
Unit tests for the core randomisation logic in generation.py.
These run without a database — pure function logic only.
Tests cover:
  - _shuffle (Fisher-Yates)
  - _per_coder_pool (independent shuffle + LRU ordering)
  - _stratified_pick (difficulty distribution with cascade overflow)
  - _shuffle_options (option re-ordering with correct-answer tracking)
  - compute_randomisation_stats (uniqueness %, pool utilisation %)
"""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

import pytest
from datetime import datetime, timezone, timedelta
from collections import Counter

from routers.assessment_pkg.generation import (
    _shuffle, _per_coder_pool, _stratified_pick, _shuffle_options,
)
from services.randomisation_stats import compute_randomisation_stats


# ── Helpers ───────────────────────────────────────────────────────────────────

def make_q(qid, difficulty="Medium", last_used_at=None):
    """Mock question object with the attributes generation.py reads."""
    class Q:
        pass
    q = Q()
    q.id = qid
    q.difficulty = difficulty
    q.last_used_at = last_used_at
    q.option_a = "Option A"
    q.option_b = "Option B"
    q.option_c = "Option C"
    q.option_d = "Option D"
    q.correct_answer = "A"
    q.question_text = f"Question {qid}"
    q.question_id = str(qid)
    q.topic = "Test"
    q.specialty = "IPDRG"
    q.shuffle_options = True
    return q


def make_pool(n=12, difficulties=None):
    if difficulties is None:
        difficulties = ["Easy"] * 4 + ["Medium"] * 4 + ["Hard"] * 4
    return [make_q(i + 1, difficulties[i]) for i in range(n)]


# ── _shuffle tests ─────────────────────────────────────────────────────────────

class TestShuffle:
    def test_same_elements(self):
        lst = list(range(20))
        original = list(lst)
        _shuffle(lst)
        assert sorted(lst) == sorted(original), "Shuffle must not add or remove elements"

    def test_returns_list(self):
        lst = [1, 2, 3]
        result = _shuffle(lst)
        assert result is lst, "_shuffle should return the same list (in-place)"

    def test_produces_variation(self):
        """Over 50 runs, a 20-element list should NOT always stay in original order."""
        original = list(range(20))
        unchanged = sum(1 for _ in range(50) if _shuffle(list(original)) == original)
        assert unchanged < 5, "Shuffle produces no variation — broken RNG?"

    def test_single_element(self):
        lst = [42]
        _shuffle(lst)
        assert lst == [42]

    def test_empty_list(self):
        lst = []
        _shuffle(lst)
        assert lst == []


# ── _per_coder_pool tests ─────────────────────────────────────────────────────

class TestPerCoderPool:
    def test_same_elements(self):
        pool = make_pool(12)
        result = _per_coder_pool(pool)
        assert {q.id for q in result} == {q.id for q in pool}

    def test_does_not_mutate_original(self):
        pool = make_pool(6)
        ids_before = [q.id for q in pool]
        _per_coder_pool(pool)
        assert [q.id for q in pool] == ids_before, "_per_coder_pool must not mutate the input"

    def test_independent_per_coder(self):
        """Two calls on the same pool should return different orderings at least sometimes."""
        pool = make_pool(12)
        orders = [tuple(q.id for q in _per_coder_pool(pool)) for _ in range(30)]
        unique_orders = len(set(orders))
        assert unique_orders > 1, "Per-coder pool always returns the same order — shuffle not working"

    def test_lru_never_used_comes_first(self):
        """Questions never used (last_used_at=None) should sort before recently used ones."""
        now = datetime.now(timezone.utc)
        never = [make_q(i, last_used_at=None) for i in range(1, 5)]
        used = [make_q(i, last_used_at=now - timedelta(days=1)) for i in range(5, 9)]
        pool = used + never

        # Run many times; never-used should always appear in the top half
        for _ in range(20):
            result = _per_coder_pool(pool)
            never_ids = {q.id for q in never}
            top_half_ids = {q.id for q in result[:4]}
            assert never_ids == top_half_ids, \
                f"Never-used questions not prioritised: top-half={top_half_ids}"


# ── _stratified_pick tests ────────────────────────────────────────────────────

class TestStratifiedPick:
    def setup_method(self):
        self.pool = make_pool(12, ["Easy"]*4 + ["Medium"]*4 + ["Hard"]*4)
        self.ratios = {"easy": 1/3, "medium": 1/3, "hard": 1/3}

    def test_returns_target_count(self):
        result = _stratified_pick(self.pool, 6, self.ratios)
        assert len(result) == 6

    def test_no_duplicates(self):
        result = _stratified_pick(self.pool, 6, self.ratios)
        assert len({q.id for q in result}) == 6

    def test_difficulty_distribution(self):
        """6 questions with 1/3 each → 2 Easy, 2 Medium, 2 Hard."""
        result = _stratified_pick(self.pool, 6, self.ratios)
        counts = Counter(q.difficulty for q in result)
        assert counts["Easy"] == 2
        assert counts["Medium"] == 2
        assert counts["Hard"] == 2

    def test_cascade_overflow_when_difficulty_scarce(self):
        """If a difficulty bucket is empty, deficit carries to next bucket."""
        # Pool with no Hard questions — deficit should fill from Easy/Medium
        pool_no_hard = make_pool(8, ["Easy"]*4 + ["Medium"]*4)
        result = _stratified_pick(pool_no_hard, 6, self.ratios)
        assert len(result) == 6, "Should still return 6 despite missing Hard bucket"

    def test_returns_subset_of_pool(self):
        pool_ids = {q.id for q in self.pool}
        result = _stratified_pick(self.pool, 6, self.ratios)
        for q in result:
            assert q.id in pool_ids

    def test_target_larger_than_pool(self):
        """When target > pool size, should return all available without error."""
        small_pool = make_pool(3)
        result = _stratified_pick(small_pool, 10, self.ratios)
        assert len(result) <= 3


# ── _shuffle_options tests ────────────────────────────────────────────────────

class TestShuffleOptions:
    """_shuffle_options takes ORM objects (attribute access, not dict keys)."""

    def make_orm_q(self, correct="A"):
        class Q:
            option_a = "Apple"; option_b = "Banana"
            option_c = "Cherry"; option_d = "Date"
            shuffle_options = True
            question_text = "Q1"; question_id = "Q1"
            topic = "Test"; specialty = "IPDRG"; difficulty = "Medium"; question_type = "Conceptual"; id = 1
        q = Q(); q.correct_answer = correct
        return q

    def test_correct_answer_text_preserved(self):
        """After shuffling, the 'correct_answer' key must point to the same text."""
        for _ in range(50):
            q = self.make_orm_q(correct="B")
            result = _shuffle_options(q)
            new_correct_letter = result["correct_answer"]
            new_correct_text = result[f"option_{new_correct_letter.lower()}"]
            assert new_correct_text == "Banana", \
                f"Correct answer text changed after shuffle: got '{new_correct_text}'"

    def test_all_options_present(self):
        """All 4 option texts must survive the shuffle."""
        q = self.make_orm_q()
        result = _shuffle_options(q)
        result_texts = {result["option_a"], result["option_b"],
                        result["option_c"], result["option_d"]}
        assert result_texts == {"Apple", "Banana", "Cherry", "Date"}

    def test_produces_variation(self):
        """Over 50 runs, the correct answer letter should NOT always stay 'A'."""
        q = self.make_orm_q(correct="A")
        letters = {_shuffle_options(q)["correct_answer"] for _ in range(50)}
        assert len(letters) > 1, "Options never shuffled — always stays at position A"

    def test_returns_dict(self):
        q = self.make_orm_q()
        result = _shuffle_options(q)
        assert isinstance(result, dict)


# ── compute_randomisation_stats tests ────────────────────────────────────────

class TestRandomisationStats:
    def test_zero_overlap(self):
        """Perfectly disjoint sets → 100% uniqueness, 100% pool utilisation."""
        coder_sets = {"Alice": {1, 2, 3}, "Bob": {4, 5, 6}, "Charlie": {7, 8, 9}}
        stats = compute_randomisation_stats(coder_sets, pool_size=9)
        assert stats["avg_uniqueness_pct"] == 100.0
        assert stats["pool_utilisation_pct"] == 100.0

    def test_full_overlap(self):
        """Identical sets → 0% uniqueness."""
        coder_sets = {"Alice": {1, 2, 3}, "Bob": {1, 2, 3}}
        stats = compute_randomisation_stats(coder_sets, pool_size=6)
        assert stats["avg_uniqueness_pct"] == 0.0

    def test_pool_utilisation(self):
        """Pool of 10, only 6 used → 60% utilisation."""
        coder_sets = {"Alice": {1, 2, 3}, "Bob": {4, 5, 6}}
        stats = compute_randomisation_stats(coder_sets, pool_size=10)
        assert stats["pool_utilisation_pct"] == 60.0

    def test_structure(self):
        coder_sets = {"Alice": {1, 2}, "Bob": {2, 3}}
        stats = compute_randomisation_stats(coder_sets, pool_size=5)
        assert "avg_uniqueness_pct" in stats
        assert "pool_utilisation_pct" in stats
        assert "per_coder" in stats
        assert "top_overlaps" in stats
        assert stats["coder_count"] == 2

    def test_partial_overlap(self):
        """Alice has Q1,Q2,Q3. Bob has Q2,Q3,Q4. Q2+Q3 are shared."""
        coder_sets = {"Alice": {1, 2, 3}, "Bob": {2, 3, 4}}
        stats = compute_randomisation_stats(coder_sets, pool_size=4)
        # Alice unique: {1}, Bob unique: {4} → each has 1/3 unique → 33.3%
        assert stats["avg_uniqueness_pct"] == pytest.approx(33.33, abs=0.1)

    def test_single_coder(self):
        """Single coder — nothing to compare, uniqueness undefined but shouldn't crash."""
        coder_sets = {"Solo": {1, 2, 3}}
        stats = compute_randomisation_stats(coder_sets, pool_size=3)
        assert "avg_uniqueness_pct" in stats
