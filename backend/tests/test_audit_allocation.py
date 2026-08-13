"""
Allocation decides what each auditor actually sees, and freezes it.

The rules that matter most here are the ones that would fail silently:

  * Clean is drawn as a QUOTA. As a per-chart coin flip, a five-chart session
    comes up all-clean or all-planted about 3% of the time each — and an
    auditor with five clean charts learns nothing that session.
  * Clean is a property of the ASSIGNMENT, never of the chart. A fixed subset
    of clean charts teaches auditors which numbers to skim, and the restraint
    measurement collapses.
  * The seed comes from (chart, cycle) and NOT the auditor, so two auditors on
    one chart see identical errors and their work is comparable.
  * A trainer's authored set is played BACKWARDS into the claim: an "Add"
    instruction means the code is missing from what the auditor sees.
"""
import random
import pytest

from models.auditor import AuditSource
from models.charts import Specialty
from services.audit_allocation import (
    Quotas, apply_manual_set, assignment_seed, build_assignment, build_corpus,
    clean_quota, new_token, resolve_quotas, resolve_source,
)
from tests.test_audit_mutation import CORPUS, FakeKey, ip_key


class FakeChart:
    def __init__(self, id_, specialty=Specialty.IP_DRG):
        self.id = id_
        self.specialty = specialty


class FakeSet:
    _next = [1]

    def __init__(self, mutations=None, query_expected=None, always_plant=False, id_=None):
        self.id = id_ if id_ is not None else FakeSet._next[0]
        FakeSet._next[0] = self.id + 1
        self.mutations = mutations or []
        self.query_expected = query_expected
        self.always_plant = always_plant


# ── the clean quota ──────────────────────────────────────────────────────────

class TestCleanQuota:

    @pytest.mark.parametrize("total,share,expected", [
        (5, 50, 2),    # 2.5 rounds DOWN
        (4, 50, 2),
        (3, 50, 1),
        (2, 50, 1),
        (1, 50, 0),
        (7, 50, 3),
        (10, 50, 5),
        (5, 70, 3),
        (5, 0, 0),
    ])
    def test_it_rounds_down(self, total, share, expected):
        assert clean_quota(total, share) == expected

    @pytest.mark.parametrize("total", range(1, 21))
    @pytest.mark.parametrize("share", [10, 30, 50, 70, 90, 99])
    def test_every_session_keeps_at_least_one_opportunity_chart(self, total, share):
        """
        The property that flooring buys: at any share below 100%, a session can
        never come out entirely clean, so it always measures detection as well
        as restraint.
        """
        assert clean_quota(total, share) < total

    def test_a_hundred_percent_share_is_still_honoured(self):
        assert clean_quota(5, 100) == 5

    def test_zero_charts_does_not_divide_by_zero(self):
        assert clean_quota(0, 50) == 0


# ── modes ────────────────────────────────────────────────────────────────────

class TestModes:

    def test_automatic_splits_clean_from_the_rest(self):
        q = resolve_quotas("auto", want=5, clean_share=50)
        assert (q.clean, q.auto) == (2, 3)
        assert q.total == 5

    def test_guided_takes_the_trainers_numbers_as_the_quota(self):
        q = resolve_quotas("guided", want=5, clean_share=50,
                           quota_clean=2, quota_manual=1, quota_auto=2)
        assert (q.clean, q.manual, q.auto) == (2, 1, 2)

    def test_guided_numbers_that_fall_short_top_up_with_auto(self):
        """
        Rather than silently shrinking the allocation — a trainer who typed 2
        and 1 for a five-chart batch still gets five charts.
        """
        q = resolve_quotas("guided", want=5, clean_share=50,
                           quota_clean=2, quota_manual=1, quota_auto=0)
        assert q.total == 5
        assert q.auto == 2

    def test_guided_with_no_numbers_falls_back_to_the_automatic_split(self):
        q = resolve_quotas("guided", want=6, clean_share=50)
        assert (q.clean, q.auto) == (3, 3)


# ── source resolution ────────────────────────────────────────────────────────

class TestSourceResolution:

    def test_a_chart_with_no_version_and_no_clean_roll_generates(self):
        src, chosen = resolve_source(1, False, {}, cycle_number=1)
        assert src == AuditSource.AUTO and chosen is None

    def test_a_chart_with_a_version_uses_it(self):
        s = FakeSet()
        src, chosen = resolve_source(1, False, {1: [s]}, cycle_number=1)
        assert src == AuditSource.MANUAL and chosen is s

    def test_a_curated_chart_can_still_come_up_clean(self):
        """
        Clean is a property of the assignment, not the chart. A chart with a
        beautiful hand-authored version must sometimes be handed over
        untouched, or the curated charts become a tell.
        """
        s = FakeSet()
        src, chosen = resolve_source(1, True, {1: [s]}, cycle_number=1)
        assert src == AuditSource.CLEAN and chosen is None

    def test_always_plant_overrides_the_clean_roll(self):
        s = FakeSet(always_plant=True)
        src, chosen = resolve_source(1, True, {1: [s]}, cycle_number=1)
        assert src == AuditSource.MANUAL and chosen is s

    def test_the_version_depends_on_the_cycle_and_nothing_else(self):
        """
        The bug this replaced: the choice was per-auditor, so four auditors on
        one chart in one cycle got three different versions and their answers
        could not be compared. Same cycle must mean same version, always.
        """
        sets = [FakeSet(), FakeSet(), FakeSet()]
        for cycle in range(1, 8):
            picks = {resolve_source(1, False, {1: sets}, cycle_number=cycle)[1]
                     for _ in range(20)}
            assert len(picks) == 1

    def test_each_cycle_rotates_to_the_next_version(self):
        sets = [FakeSet(), FakeSet(), FakeSet()]
        picked = [resolve_source(1, False, {1: sets}, cycle_number=c)[1]
                  for c in range(1, 4)]
        assert picked == sets

    def test_the_rotation_wraps_once_every_version_is_used(self):
        """Running dry is not a reason to drop the chart from the rotation."""
        sets = [FakeSet(), FakeSet()]
        assert resolve_source(1, False, {1: sets}, cycle_number=3)[1] is sets[0]
        assert resolve_source(1, False, {1: sets}, cycle_number=4)[1] is sets[1]

    def test_the_rotation_is_stable_as_the_library_grows(self):
        """
        Ordered by id, so authoring a fourth version does not reshuffle which
        version cycle 2 hands out.
        """
        a, b, c = FakeSet(), FakeSet(), FakeSet()
        assert resolve_source(1, False, {1: [c, a, b]}, cycle_number=2)[1] is b


# ── the seed ─────────────────────────────────────────────────────────────────

class TestSeed:

    def test_the_same_chart_in_the_same_cycle_seeds_identically(self):
        """
        Two auditors on one chart must see the SAME errors — it is the only way
        their answers on it can be compared.
        """
        assert assignment_seed(42, 3) == assignment_seed(42, 3)

    def test_the_same_chart_in_a_later_cycle_seeds_differently(self):
        """Otherwise a recycled chart carries the identical errors."""
        seeds = {assignment_seed(42, c) for c in range(1, 12)}
        assert len(seeds) == 11

    def test_different_charts_seed_differently_within_a_cycle(self):
        assert len({assignment_seed(c, 1) for c in range(1, 40)}) == 39


# ── freezing ─────────────────────────────────────────────────────────────────

class TestBuildAssignment:

    def test_a_clean_assignment_is_the_answer_key_untouched(self):
        key = ip_key()
        a = build_assignment(FakeChart(1), key, AuditSource.CLEAN, None,
                             cycle_number=1, corpus=CORPUS)
        assert a["ground_truth"] == []
        assert a["claim"]["pdx_code"] == key.pdx_code
        assert len(a["claim"]["sdx"]) == len(key.sdx)
        assert a["seed"] is None

    def test_an_auto_assignment_records_its_seed(self):
        """Without it a disputed finding cannot be re-derived months later."""
        a = build_assignment(FakeChart(7), ip_key(), AuditSource.AUTO, None,
                             cycle_number=2, corpus=CORPUS)
        assert a["seed"] == assignment_seed(7, 2)
        assert a["ground_truth"]

    def test_a_chart_with_no_answer_key_is_never_planted(self):
        """There is no truth to mutate, and nothing to audit against."""
        a = build_assignment(FakeChart(1), None, AuditSource.AUTO, None,
                             cycle_number=1, corpus=CORPUS)
        assert a["source"] == AuditSource.CLEAN
        assert a["ground_truth"] == []

    def test_a_manual_assignment_carries_its_query_expectation(self):
        s = FakeSet(mutations=[], query_expected=True)
        a = build_assignment(FakeChart(1), ip_key(), AuditSource.MANUAL, s,
                             cycle_number=1, corpus=CORPUS)
        assert a["query_expected"] is True
        assert a["set_id"] == s.id

    def test_an_auto_assignment_has_no_query_expectation(self):
        """
        The system can read an answer key; it cannot read whether the
        documentation supported the code. An unauthored answer is NA, and must
        never be stored as False.
        """
        a = build_assignment(FakeChart(1), ip_key(), AuditSource.AUTO, None,
                             cycle_number=1, corpus=CORPUS)
        assert a["query_expected"] is None


# ── a trainer's authored set ─────────────────────────────────────────────────

class TestManualSet:

    def test_an_add_instruction_removes_the_code_from_the_claim(self):
        """
        The set says what the AUDITOR must do, so building the claim plays it
        backwards: "Add E11.3" means the claim is missing E11.3.
        """
        key = ip_key(n_sdx=5)
        s = FakeSet(mutations=[{"section": "SDx", "action": "Add",
                                "correct_value": "E11.3"}])
        claim, truth = apply_manual_set(key, s)
        assert "E11.3" not in [r["code"] for r in claim["sdx"]]
        assert len(claim["sdx"]) == 4
        assert truth[0]["action"] == "Add"
        assert truth[0]["entry"]["code"] == "E11.3"

    def test_a_delete_instruction_inserts_a_spurious_code(self):
        key = ip_key(n_sdx=4)
        s = FakeSet(mutations=[{"section": "SDx", "action": "Delete",
                                "line": 1, "claim_value": "I10"}])
        claim, truth = apply_manual_set(key, s)
        assert claim["sdx"][1]["code"] == "I10"
        assert len(claim["sdx"]) == 5
        assert truth[0]["line"] == 1

    def test_a_revise_instruction_puts_the_wrong_value_on_the_claim(self):
        key = ip_key(n_sdx=4)
        original = key.sdx[2]["code"]
        s = FakeSet(mutations=[{"section": "SDx", "action": "Revise", "field": "code",
                                "line": 2, "claim_value": "E11.99"}])
        claim, truth = apply_manual_set(key, s)
        assert claim["sdx"][2]["code"] == "E11.99"
        assert truth[0]["correct_value"] == original

    def test_a_pdx_revision_is_supported(self):
        key = ip_key()
        s = FakeSet(mutations=[{"section": "PDx", "action": "Revise", "field": "code",
                                "line": 0, "claim_value": "J44.1"}])
        claim, truth = apply_manual_set(key, s)
        assert claim["pdx_code"] == "J44.1"
        assert truth[0]["correct_value"] == "J18.9"

    def test_line_numbers_survive_a_later_removal(self):
        """
        The same bug the generator had: an Add removes a row, and every finding
        recorded against a later line slides. A stale line scores as a miss
        whatever the auditor does.
        """
        key = ip_key(n_sdx=6)
        target = key.sdx[4]["code"]
        s = FakeSet(mutations=[
            {"section": "SDx", "action": "Revise", "field": "code",
             "line": 4, "claim_value": "ZZZ"},
            {"section": "SDx", "action": "Add", "correct_value": key.sdx[1]["code"]},
        ])
        claim, truth = apply_manual_set(key, s)
        revise = next(r for r in truth if r["action"] == "Revise")
        assert claim["sdx"][revise["line"]]["code"] == "ZZZ"
        assert revise["correct_value"] == target

    def test_line_numbers_survive_a_later_insertion(self):
        key = ip_key(n_sdx=6)
        s = FakeSet(mutations=[
            {"section": "SDx", "action": "Revise", "field": "code",
             "line": 3, "claim_value": "ZZZ"},
            {"section": "SDx", "action": "Delete", "line": 0, "claim_value": "I10"},
        ])
        claim, truth = apply_manual_set(key, s)
        revise = next(r for r in truth if r["action"] == "Revise")
        delete = next(r for r in truth if r["action"] == "Delete")
        assert claim["sdx"][revise["line"]]["code"] == "ZZZ"
        assert claim["sdx"][delete["line"]]["code"] == "I10"

    def test_an_add_naming_a_code_not_on_the_key_is_skipped(self):
        """
        Otherwise the auditor is asked to add a code the chart never supported,
        and can never score it.
        """
        s = FakeSet(mutations=[{"section": "SDx", "action": "Add",
                                "correct_value": "NOTONKEY"}])
        claim, truth = apply_manual_set(ip_key(), s)
        assert truth == []

    def test_a_set_with_no_mutations_is_a_curated_clean_chart(self):
        """
        A correctly coded claim that still needs a query. This is why "clean"
        and "manual" stopped being mutually exclusive.
        """
        s = FakeSet(mutations=[], query_expected=True)
        claim, truth = apply_manual_set(ip_key(), s)
        assert truth == []
        assert len(claim["sdx"]) == 8

    def test_a_manual_set_is_not_capped(self):
        """
        No ceiling applies to manual plantings — a trainer authoring a set has
        read the chart and has a reason.
        """
        key = ip_key(n_sdx=20)
        s = FakeSet(mutations=[{"section": "SDx", "action": "Add",
                                "correct_value": key.sdx[i]["code"]}
                               for i in range(15)])
        _claim, truth = apply_manual_set(key, s)
        assert len(truth) == 15


# ── the corpus ───────────────────────────────────────────────────────────────

class TestCorpus:

    def test_it_gathers_every_code_the_library_holds(self):
        keys = [
            FakeKey(pdx_code="J18.9",
                    sdx=[{"code": "E11.9"}, {"code": "I10"}],
                    pcs=[{"code": "0DTJ0ZZ"}]),
            FakeKey(pdx_code="I50.9",
                    cpt=[{"code": "27447", "modifier": "RT"}]),
        ]
        c = build_corpus(keys)
        assert set(c.dx_codes) == {"J18.9", "E11.9", "I10", "I50.9"}
        assert c.pcs_codes == ["0DTJ0ZZ"]
        assert c.cpt_codes == ["27447"]
        assert c.modifiers == ["RT"]

    def test_an_empty_library_yields_an_empty_corpus(self):
        c = build_corpus([])
        assert c.dx_codes == [] and c.pcs_codes == []

    def test_malformed_key_rows_are_skipped_not_crashed_on(self):
        keys = [FakeKey(sdx=["not a dict", {"code": "E11.9"}, {}])]
        assert build_corpus(keys).dx_codes == ["E11.9", "J18.9"]


# ── tokens ───────────────────────────────────────────────────────────────────

class TestTokens:

    def test_the_prefix_routes_the_auditor_to_the_right_session(self):
        assert new_token().startswith("AUD-")

    def test_it_has_the_same_shape_as_a_coder_practice_token(self):
        """
        Four letters then four digits, exactly like _gen_token on the coder
        side. An earlier version used its own alphabet, which meant two access
        code formats in one product for no reason anybody could explain.
        """
        import re
        for _ in range(200):
            assert re.fullmatch(r"AUD-[A-Z]{4}\d{4}", new_token())

    def test_tokens_do_not_collide(self):
        assert len({new_token() for _ in range(2000)}) == 2000
