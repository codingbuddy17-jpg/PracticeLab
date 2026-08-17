"""
Planting the errors real coders actually made, rather than errors we imagine.

Everything else in the mutation engine is an educated guess. This reads what
coders did on the same chart and plants that instead — so an auditor is
learning to catch what their own colleagues get wrong.

The two rules worth defending in tests:

  * Diff against the CURRENT answer key, never the snapshot stored beside the
    submission. An error recorded six months ago against an older key may not
    be an error today, and planting it manufactures exactly the false finding
    the whole design tries to avoid.
  * One coder making one mistake is a data point. Two or more making the same
    one is a trend, and only a trend earns extra weight — otherwise a single
    careless session distorts what the module teaches.
"""
import json
import pytest

from models.charts import Specialty
from services.audit_mutation import MutationConfig, generate
from services.audit_observations import (
    TREND_THRESHOLD, Observation, observations_for_chart, summarise,
)
from tests.test_audit_mutation import CORPUS, FakeKey


def key_of(sdx_codes=("E11.9", "I10", "N17.9"), pdx="J18.9", pcs=(), cpt=()):
    return FakeKey(
        pdx_code=pdx,
        sdx=[{"code": c, "poa": "Y", "ccmcc": "CC" if i == 0 else "-"}
             for i, c in enumerate(sdx_codes)],
        pcs=[{"code": c} for c in pcs],
        cpt=[dict(c) for c in cpt],
    )


def submission(pdx="J18.9", sdx=(), pcs=(), cpt=()):
    """One coder's work, in the shape practice_results stores it."""
    return {
        "pdx_submitted": pdx,
        "sdx_submitted": json.dumps([
            s if isinstance(s, dict) else {"code": s, "poa": "Y"} for s in sdx]),
        "pcs_submitted": json.dumps([
            p if isinstance(p, dict) else {"code": p} for p in pcs]),
        "cpt_submitted": json.dumps([dict(c) for c in cpt]),
    }


def find(obs, action, code=None, field=None):
    return [o for o in obs
            if o.action == action
            and (code is None or o.code == code)
            and (field is None or o.field == field)]


# ── the diff ─────────────────────────────────────────────────────────────────

class TestHarvest:

    def test_a_missed_code_becomes_an_add(self):
        obs = observations_for_chart(
            [submission(sdx=["E11.9", "I10"])], key_of())
        assert find(obs, "Add", "N17.9")
        assert find(obs, "Add", "N17.9")[0].correct_value == "N17.9"

    def test_an_invented_code_becomes_a_delete(self):
        """
        Recoverable only from the submitted JSON. grading_feedback records
        over-coding as a COUNT — "3 extra code(s) submitted" — without saying
        which, so a Delete planting cannot be built from it.
        """
        obs = observations_for_chart(
            [submission(sdx=["E11.9", "I10", "N17.9", "J44.1"])], key_of())
        d = find(obs, "Delete", "J44.1")
        assert d and d[0].claim_value == "J44.1"

    def test_a_wrong_principal_becomes_a_revise(self):
        obs = observations_for_chart(
            [submission(pdx="J44.1", sdx=["E11.9", "I10", "N17.9"])], key_of())
        r = find(obs, "Revise")[0]
        assert r.section == "PDx"
        assert (r.claim_value, r.correct_value) == ("J44.1", "J18.9")

    def test_a_wrong_poa_becomes_a_field_revise(self):
        """
        POA is a field on a line, not a section — so getting it wrong is a
        Revise on that line, the same shape the auditor's finding takes.
        """
        obs = observations_for_chart([submission(sdx=[
            {"code": "E11.9", "poa": "N"}, {"code": "I10", "poa": "Y"},
            {"code": "N17.9", "poa": "Y"}])], key_of())
        r = find(obs, "Revise", "E11.9", "poa")
        assert r and (r[0].claim_value, r[0].correct_value) == ("N", "Y")

    def test_a_wrong_modifier_becomes_a_field_revise(self):
        key = key_of(sdx_codes=["E11.9"], cpt=[{"code": "27447", "modifier": "RT", "units": 1}])
        obs = observations_for_chart(
            [submission(sdx=["E11.9"],
                        cpt=[{"code": "27447", "modifier": "LT", "units": 1}])], key)
        r = find(obs, "Revise", "27447", "modifier")
        assert r and (r[0].claim_value, r[0].correct_value) == ("LT", "RT")

    def test_units_are_not_observed_for_auditor_planting(self):
        """Units are not part of auditor planting scope."""
        key = key_of(sdx_codes=["E11.9"], cpt=[{"code": "27447", "modifier": "", "units": 1}])
        obs = observations_for_chart(
            [submission(sdx=["E11.9"], cpt=[{"code": "27447", "modifier": "", "units": 3}])], key)
        assert not find(obs, "Revise", field="units")

    def test_a_correct_submission_yields_nothing(self):
        obs = observations_for_chart(
            [submission(sdx=["E11.9", "I10", "N17.9"])], key_of())
        assert obs == []

    def test_no_answer_key_yields_nothing(self):
        assert observations_for_chart([submission(sdx=["E11.9"])], None) == []

    def test_code_formatting_differences_are_not_mistakes(self):
        obs = observations_for_chart(
            [submission(sdx=["e119", " I10 ", "N17.9"])], key_of())
        assert obs == []


# ── the current key, not the stored snapshot ─────────────────────────────────

class TestStaleness:

    def test_an_error_against_an_older_key_is_not_planted_today(self):
        """
        The trap this design avoids by construction. A coder was marked wrong
        for coding I50.9 when the key said I50.21. If the key has since been
        corrected TO I50.9, that coder was right all along — and planting the
        old "error" would ask an auditor to change a correct code.

        Diffing against the live key rather than the stored snapshot means the
        observation simply disappears when the key is fixed.
        """
        corrected = key_of(sdx_codes=["I50.9", "I10", "N17.9"])
        obs = observations_for_chart(
            [submission(sdx=["I50.9", "I10", "N17.9"])], corrected)
        assert obs == []

    def test_a_key_correction_creates_new_observations_for_what_is_now_wrong(self):
        """The mirror image: everyone who coded the OLD value is now wrong."""
        corrected = key_of(sdx_codes=["I50.21", "I10", "N17.9"])
        obs = observations_for_chart(
            [submission(sdx=["I50.9", "I10", "N17.9"])] * 3, corrected)
        assert find(obs, "Add", "I50.21")[0].coders == 3
        assert find(obs, "Delete", "I50.9")[0].coders == 3


# ── frequency ────────────────────────────────────────────────────────────────

class TestTrends:

    def test_coders_making_the_same_mistake_are_counted_together(self):
        obs = observations_for_chart(
            [submission(sdx=["E11.9", "I10"])] * 7, key_of())
        assert find(obs, "Add", "N17.9")[0].coders == 7

    def test_one_coder_is_a_candidate_not_a_trend(self):
        """
        It might just be someone having a bad afternoon. Still worth planting;
        not worth weighting.
        """
        o = observations_for_chart([submission(sdx=["E11.9", "I10"])], key_of())[0]
        assert o.coders == 1
        assert o.is_trend is False
        assert o.weight == 1.0

    def test_two_coders_make_it_a_trend(self):
        obs = observations_for_chart(
            [submission(sdx=["E11.9", "I10"])] * TREND_THRESHOLD, key_of())
        assert obs[0].is_trend is True
        assert obs[0].weight > 1.0

    def test_the_commonest_mistakes_come_first(self):
        obs = observations_for_chart(
            [submission(sdx=["E11.9", "I10"])] * 5        # missing N17.9 x5
            + [submission(sdx=["E11.9", "N17.9"])],       # missing I10   x1
            key_of())
        assert obs[0].coders >= obs[-1].coders
        assert obs[0].code == "N17.9"

    def test_summarise_reports_coverage(self):
        obs = observations_for_chart(
            [submission(sdx=["E11.9", "I10"])] * 3
            + [submission(sdx=["E11.9", "I10", "N17.9", "J44.1"])],
            key_of())
        s = summarise(obs)
        assert s["observations"] == 2
        assert s["trends"] == 1
        assert s["max_coders"] == 3
        assert s["by_action"]["Add"] == 1 and s["by_action"]["Delete"] == 1


# ── planting them ────────────────────────────────────────────────────────────

class TestPlanting:

    def _obs(self, n=6):
        """A chart where coders reliably missed several secondaries."""
        key = FakeKey(sdx=[{"code": f"E11.{i}", "poa": "Y", "ccmcc": "-"}
                           for i in range(10)],
                      pcs=[{"code": "0DTJ0ZZ"}, {"code": "0DTJ1ZZ"}])
        subs = [submission(sdx=[f"E11.{i}" for i in range(10) if i >= n],
                           pcs=["0DTJ0ZZ", "0DTJ1ZZ"])] * 4
        return key, observations_for_chart(subs, key)

    def test_observed_errors_are_planted_in_preference_to_synthetic(self):
        key, obs = self._obs()
        _claim, gt = generate(key, Specialty.IP_DRG, seed=1, corpus=CORPUS,
                              observations=obs)
        assert gt
        assert all(r.get("origin") == "observed" for r in gt), \
            [r.get("kind") for r in gt]

    def test_a_planted_observation_carries_its_evidence(self):
        """
        So analytics can say "auditors catch 82% of synthetic plantings but
        54% of the errors our coders really make".
        """
        key, obs = self._obs()
        _claim, gt = generate(key, Specialty.IP_DRG, seed=3, corpus=CORPUS,
                              observations=obs)
        assert gt[0]["observed_coders"] == 4
        assert gt[0]["observed_trend"] is True

    def test_synthetic_fills_the_budget_when_observations_run_out(self):
        """
        A chart with one observation and a budget of three still varies —
        otherwise thin coverage would make every cycle identical.
        """
        key = FakeKey(sdx=[{"code": f"E11.{i}", "poa": "Y", "ccmcc": "-"}
                           for i in range(12)],
                      pcs=[{"code": "0DTJ0ZZ"}, {"code": "0DTJ1ZZ"}])
        obs = observations_for_chart(
            [submission(sdx=[f"E11.{i}" for i in range(1, 12)],
                        pcs=["0DTJ0ZZ", "0DTJ1ZZ"])], key)
        assert len(obs) == 1
        _claim, gt = generate(key, Specialty.IP_DRG, seed=5, corpus=CORPUS,
                              observations=obs, budget=4)
        origins = [r.get("origin") for r in gt]
        assert origins.count("observed") == 1
        assert len(gt) == 4

    def test_a_chart_with_no_coder_history_is_entirely_synthetic(self):
        """Coverage grows with time; an uncoded chart falls back cleanly."""
        key = FakeKey(sdx=[{"code": f"E11.{i}", "poa": "Y", "ccmcc": "-"}
                           for i in range(8)], pcs=[{"code": "0DTJ0ZZ"}])
        _claim, gt = generate(key, Specialty.IP_DRG, seed=2, corpus=CORPUS,
                              observations=[])
        assert gt
        assert all(r.get("origin") != "observed" for r in gt)

    def test_the_same_chart_plants_a_different_subset_each_cycle(self):
        """
        Ten observations and a budget of three should not mean the same three
        every time — variety comes from the draw, not from synthetic filler.
        """
        key, obs = self._obs()
        picked = set()
        for seed in range(12):
            _claim, gt = generate(key, Specialty.IP_DRG, seed=seed,
                                  corpus=CORPUS, observations=obs, budget=2)
            picked.add(tuple(sorted(str(r.get("correct_value")) for r in gt)))
        assert len(picked) > 1

    def test_planting_is_still_deterministic_for_a_given_seed(self):
        key, obs = self._obs()
        a = generate(key, Specialty.IP_DRG, seed=9, corpus=CORPUS, observations=obs)
        b = generate(key, Specialty.IP_DRG, seed=9, corpus=CORPUS, observations=obs)
        assert a == b

    def test_trends_are_planted_more_often_than_one_offs(self):
        key = FakeKey(sdx=[{"code": f"E11.{i}", "poa": "Y", "ccmcc": "-"}
                           for i in range(10)])
        common = Observation(section="SDx", action="Add", code="E11.1",
                             correct_value="E11.1", coders=8)
        rare = Observation(section="SDx", action="Add", code="E11.2",
                           correct_value="E11.2", coders=1)
        hits = {"E11.1": 0, "E11.2": 0}
        for seed in range(200):
            _claim, gt = generate(key, Specialty.IP_DRG, seed=seed,
                                  corpus=CORPUS, observations=[common, rare],
                                  budget=1)
            for r in gt:
                if r.get("correct_value") in hits:
                    hits[r["correct_value"]] += 1
        assert hits["E11.1"] > hits["E11.2"], hits
        assert hits["E11.2"] > 0, "a one-off must still be plantable"

    def test_observations_never_empty_a_section(self):
        """
        A coder who missed nine of ten secondaries is a real observation and an
        impossible claim. The constraint still binds.
        """
        key = FakeKey(sdx=[{"code": f"E11.{i}", "poa": "Y", "ccmcc": "-"}
                           for i in range(4)])
        subs = [submission(sdx=["E11.0"])] * 3
        obs = observations_for_chart(subs, key)
        for seed in range(30):
            claim, _gt = generate(key, Specialty.IP_DRG, seed=seed,
                                  corpus=CORPUS, observations=obs)
            assert claim["sdx"], f"seed {seed} emptied SDx"

    def test_observed_plantings_respect_one_mutation_per_line(self):
        key, obs = self._obs()
        for seed in range(30):
            _claim, gt = generate(key, Specialty.IP_DRG, seed=seed,
                                  corpus=CORPUS, observations=obs)
            touched = [(r["section"], r["line"]) for r in gt if "line" in r]
            assert len(touched) == len(set(touched)), f"seed {seed}: {touched}"

    def test_the_share_is_configurable(self):
        """A trainer can dial observed plantings down without losing them."""
        key, obs = self._obs()
        cfg = MutationConfig(observed_share_pct=0)
        _claim, gt = generate(key, Specialty.IP_DRG, seed=1, corpus=CORPUS,
                              cfg=cfg, observations=obs)
        assert all(r.get("origin") != "observed" for r in gt)
