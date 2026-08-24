"""
The mutation engine must produce claims a coder could plausibly have written.

Random-but-valid mutation is the failure mode: it yields claims nobody would
ever produce, so auditors learn to spot the generator instead of learning the
job. These tests pin the constraints that keep a claim believable, and the
determinism that makes a disputed finding reproducible months later.
"""
import random
import pytest

from models.charts import Specialty
from services.audit_mutation import (
    Corpus, MUTATION_KINDS, MutationConfig, claim_from_key, generate,
    planting_budget, total_codes, _mutate_pcs_code, _substitute_dx,
    PCS_MUTABLE_POSITIONS,
)


class FakeKey:
    def __init__(self, pdx_code="J18.9", pdx_poa="Y", sdx=None, pcs=None, cpt=None,
                 mdm=None, em_category=None, level_method="MDM", em_code=None,
                 mdm_overridden=None):
        self.pdx_code = pdx_code
        self.pdx_poa = pdx_poa
        self.sdx = sdx if sdx is not None else []
        self.pcs = pcs if pcs is not None else []
        self.cpt = cpt if cpt is not None else []
        self.facility_level = None
        self.profee_level = None
        self.mdm = mdm or {}
        self.em_category = em_category
        self.level_method = level_method
        self.em_code = em_code or ((self.cpt[0] or {}).get("code") if self.cpt else "")
        self.mdm_overridden = mdm_overridden or {}


def ip_key(n_sdx=8, n_pcs=3):
    return FakeKey(
        sdx=[{"code": f"E11.{i}", "poa": "Y", "ccmcc": "CC" if i % 3 == 0 else "-"}
             for i in range(n_sdx)],
        pcs=[{"code": f"0DTJ{i}ZZ"} for i in range(n_pcs)],
    )


def op_key(n_sdx=5, n_cpt=4):
    return FakeKey(
        sdx=[{"code": f"M17.{i}", "poa": "", "ccmcc": ""} for i in range(n_sdx)],
        cpt=[{"code": f"2744{i}", "modifier": "RT" if i % 2 else "", "units": 1}
             for i in range(n_cpt)],
    )


CORPUS = Corpus(
    dx_codes=[f"E11.{i}" for i in range(30)] + [f"I50.{i}" for i in range(10)]
             + ["N17.9", "I10", "J44.1"],
    pcs_codes=[f"0DTJ{c}ZZ" for c in "0123456789"] + ["0DT60ZZ", "0DB70ZX"],
    modifiers=["59", "51", "25", "RT", "LT"],
)


def _sections(gt):
    return [(r["section"], r["action"]) for r in gt]


# ── determinism ──────────────────────────────────────────────────────────────

class TestDeterminism:

    def test_the_same_seed_rebuilds_the_same_claim(self):
        """
        The whole freeze/dispute story depends on this. If a seed did not
        reproduce, a finding disputed months later could not be re-examined.
        """
        a = generate(ip_key(), Specialty.IP_DRG, seed=4242, corpus=CORPUS)
        b = generate(ip_key(), Specialty.IP_DRG, seed=4242, corpus=CORPUS)
        assert a == b

    def test_different_seeds_give_different_claims(self):
        """Otherwise a chart in a later cycle carries the identical errors."""
        results = {
            str(generate(ip_key(), Specialty.IP_DRG, seed=s, corpus=CORPUS)[1])
            for s in range(20)
        }
        assert len(results) > 1

    def test_the_generator_never_touches_global_random_state(self):
        random.seed(99)
        expected = random.random()
        random.seed(99)
        generate(ip_key(), Specialty.IP_DRG, seed=1, corpus=CORPUS)
        assert random.random() == expected


# ── constraints that keep a claim believable ─────────────────────────────────

class TestConstraints:

    @pytest.mark.parametrize("seed", range(40))
    def test_a_section_is_never_emptied(self, seed):
        """
        A claim with no secondaries at all is not a flawed claim, it is a
        broken one — and no coder would submit it.
        """
        claim, gt = generate(ip_key(), Specialty.IP_DRG, seed=seed, corpus=CORPUS)
        assert claim["sdx"], f"seed {seed} emptied SDx"
        assert claim["pcs"], f"seed {seed} emptied PCS"

    @pytest.mark.parametrize("seed", range(40))
    def test_pdx_is_never_blanked(self, seed):
        """PDx can be wrong. It cannot be absent."""
        claim, _ = generate(ip_key(), Specialty.IP_DRG, seed=seed, corpus=CORPUS)
        assert claim["pdx_code"]

    @pytest.mark.parametrize("seed", range(40))
    def test_one_mutation_per_line(self, seed):
        """
        Two errors on one line make the correct finding ambiguous and the
        scoring arbitrary.
        """
        _, gt = generate(ip_key(), Specialty.IP_DRG, seed=seed, corpus=CORPUS)
        touched = [(r["section"], r["line"]) for r in gt if "line" in r]
        assert len(touched) == len(set(touched)), f"seed {seed}: {touched}"

    @pytest.mark.parametrize("seed", range(30))
    def test_a_two_code_chart_is_barely_touched(self, seed):
        """
        Density scales with the key. Breaking one of two codes is half the
        chart — that reads as broken, not flawed.
        """
        key = FakeKey(sdx=[{"code": "I10", "poa": "Y", "ccmcc": "-"}])
        claim, gt = generate(key, Specialty.IP_DRG, seed=seed, corpus=CORPUS)
        assert len(gt) <= 1
        assert claim["sdx"]

    def test_the_budget_never_exceeds_the_configured_cap(self):
        cfg = MutationConfig(max_auto_plantings=3, max_section_share=90)
        for seed in range(30):
            _, gt = generate(ip_key(n_sdx=25, n_pcs=10), Specialty.IP_DRG,
                             seed=seed, cfg=cfg, corpus=CORPUS)
            assert len(gt) <= 3

    def test_a_rich_chart_can_reach_the_generation_cap_of_six(self):
        """Auto generation has an absolute ceiling; manual authored versions do not."""
        best = max(
            len(generate(ip_key(n_sdx=30, n_pcs=12), Specialty.IP_DRG,
                         seed=s, corpus=CORPUS)[1])
            for s in range(40)
        )
        assert best == 6

    def test_the_budget_never_exceeds_the_platform_cap_even_if_config_is_higher(self):
        cfg = MutationConfig(max_auto_plantings=12, max_section_share=90)
        best = max(
            len(generate(ip_key(n_sdx=30, n_pcs=12), Specialty.IP_DRG,
                         seed=s, cfg=cfg, corpus=CORPUS)[1])
            for s in range(40)
        )
        assert best == 6


# ── ground truth is usable ───────────────────────────────────────────────────

class TestGroundTruth:

    @pytest.mark.parametrize("seed", range(40))
    def test_every_recorded_line_points_at_a_real_row(self, seed):
        """
        The bug this guards: a removal or insertion shifts every later line,
        and a finding still pointing at the old index would score as a miss no
        matter what the auditor did.
        """
        claim, gt = generate(ip_key(), Specialty.IP_DRG, seed=seed, corpus=CORPUS)
        for rec in gt:
            if "line" not in rec:
                continue
            rows = {"SDx": claim["sdx"], "PCS": claim["pcs"],
                    "CPT": claim["cpt"], "PDx": [claim]}[rec["section"]]
            assert 0 <= rec["line"] < len(rows), f"seed {seed}: {rec}"

    @pytest.mark.parametrize("seed", range(40))
    def test_a_revise_records_what_the_claim_actually_shows(self, seed):
        """
        claim_value must match the flawed claim, or the auditor is told to
        correct something that is not on their screen.
        """
        claim, gt = generate(ip_key(), Specialty.IP_DRG, seed=seed, corpus=CORPUS)
        for rec in gt:
            if rec["action"] != "Revise":
                continue
            if rec["section"] == "SDx":
                row = claim["sdx"][rec["line"]]
                got = row.get(rec["field"] if rec["field"] != "code" else "code")
            elif rec["section"] == "PCS":
                got = claim["pcs"][rec["line"]]["code"]
            elif rec["section"] == "CPT":
                got = claim["cpt"][rec["line"]].get(rec["field"])
            else:
                got = claim["pdx_code"] if rec["field"] == "code" else claim["pdx_poa"]
            assert str(got or "") == str(rec["claim_value"] or ""), f"seed {seed}: {rec}"

    @pytest.mark.parametrize("seed", range(40))
    def test_an_add_names_a_code_that_is_no_longer_on_the_claim(self, seed):
        claim, gt = generate(ip_key(), Specialty.IP_DRG, seed=seed, corpus=CORPUS)
        present = {s["code"] for s in claim["sdx"]} | {p["code"] for p in claim["pcs"]}
        for rec in gt:
            if rec["action"] == "Add":
                assert rec["correct_value"] not in present, f"seed {seed}: {rec}"

    @pytest.mark.parametrize("seed", range(40))
    def test_a_delete_names_a_code_that_IS_on_the_claim(self, seed):
        claim, gt = generate(ip_key(), Specialty.IP_DRG, seed=seed, corpus=CORPUS)
        for rec in gt:
            if rec["action"] == "Delete":
                assert claim["sdx"][rec["line"]]["code"] == rec["claim_value"]

    def test_a_pdx_swap_is_one_finding_not_two(self):
        """
        An auditor thinks "wrong principal diagnosis", and on IP-DRG it is the
        single most valuable catch. Two findings would double-count it.
        """
        cfg = MutationConfig(mix_swap_pdx=100, mix_omit_sdx=0, mix_omit_proc=0,
                             mix_modifier_missing=0, mix_modifier_wrong=0,
                             mix_substitute=0, mix_units=0, mix_poa=0,
                             mix_spurious=0)
        claim, gt = generate(ip_key(), Specialty.IP_DRG, seed=7, cfg=cfg,
                             corpus=CORPUS, budget=1)
        assert len(gt) == 1
        assert gt[0]["section"] == "PDx" and gt[0]["action"] == "Revise"
        # The displaced principal really did land in the secondaries.
        assert gt[0]["correct_value"] in {s["code"] for s in claim["sdx"]}

    def test_a_swap_only_draws_from_the_leading_secondaries(self):
        """
        Swapping with the ninth secondary produces a claim that is obviously
        wrong rather than arguably wrong, which teaches nothing.
        """
        cfg = MutationConfig(mix_swap_pdx=100, mix_omit_sdx=0, mix_omit_proc=0,
                             mix_modifier_missing=0, mix_modifier_wrong=0,
                             mix_substitute=0, mix_units=0, mix_poa=0,
                             mix_spurious=0)
        for seed in range(25):
            _, gt = generate(ip_key(n_sdx=12), Specialty.IP_DRG, seed=seed,
                             cfg=cfg, corpus=CORPUS, budget=1)
            if gt:
                assert gt[0]["swapped_with_line"] < 3


# ── PCS: one character, and it means something ───────────────────────────────

class TestPCSMutation:

    def test_exactly_one_character_changes(self):
        rng = random.Random(3)
        for _ in range(50):
            out, _what = _mutate_pcs_code("0DTJ4ZZ", CORPUS, rng)
            assert len(out) == 7
            diffs = [i for i in range(7) if out[i] != "0DTJ4ZZ"[i]]
            assert len(diffs) == 1

    def test_section_and_body_system_are_never_touched(self):
        """
        Changing character 1 or 2 lands in a different chapter entirely, which
        reads as a typo rather than a coding decision.
        """
        rng = random.Random(11)
        for _ in range(60):
            out, _ = _mutate_pcs_code("0DTJ4ZZ", CORPUS, rng)
            assert out[:2] == "0D"

    def test_the_changed_character_is_named(self):
        """
        "Revise PCS line 2, root operation" is a self-explaining finding;
        "revise PCS line 2" is not.
        """
        rng = random.Random(5)
        seen = {_mutate_pcs_code("0DTJ4ZZ", CORPUS, rng)[1] for _ in range(80)}
        assert seen <= set(PCS_MUTABLE_POSITIONS.values())
        assert len(seen) >= 3


class TestPCSMutationStaysInsideTheTables:
    """
    PCS only exists in the combinations the CMS tables define. Changing one
    character therefore usually lands on nothing: measured against FY2026,
    66% of structural mutations produced a string that is not a code.

    That is the wrong error to plant. Spotting "that is not a code" is not the
    skill being measured — the finding is free, and detection reads higher than
    the auditor's judgement warrants. When the tables are loaded the mutation
    must produce a REAL code.
    """

    # A small stand-in for one PCS table: same first three characters, varying
    # body part, approach and qualifier — the shape the real tables have.
    REAL = {"0DTJ0ZZ", "0DTJ4ZZ", "0DTJ7ZZ", "0DTJ8ZZ",
            "0DT80ZZ", "0DT90ZZ", "0DTE0ZZ"}

    def test_every_mutation_is_a_code_that_exists(self):
        corpus = Corpus(pcs_codes=sorted(self.REAL), valid_pcs=set(self.REAL))
        rng = random.Random(4)
        for _ in range(80):
            out, _what = _mutate_pcs_code("0DTJ4ZZ", corpus, rng)
            assert out in self.REAL
            assert out != "0DTJ4ZZ"

    def test_it_still_changes_exactly_one_character(self):
        corpus = Corpus(pcs_codes=sorted(self.REAL), valid_pcs=set(self.REAL))
        rng = random.Random(9)
        for _ in range(60):
            out, _ = _mutate_pcs_code("0DTJ4ZZ", corpus, rng)
            diffs = [i for i in range(7) if out[i] != "0DTJ4ZZ"[i]]
            assert len(diffs) == 1

    def test_the_changed_character_is_still_named(self):
        corpus = Corpus(pcs_codes=sorted(self.REAL), valid_pcs=set(self.REAL))
        rng = random.Random(2)
        seen = {_mutate_pcs_code("0DTJ4ZZ", corpus, rng)[1] for _ in range(60)}
        assert seen and seen <= set(PCS_MUTABLE_POSITIONS.values())

    def test_no_tables_loaded_falls_back_rather_than_refusing(self):
        """
        Reference data being absent must never stop a batch being built. With
        an empty set the generator behaves exactly as it did before this
        existed.
        """
        rng = random.Random(6)
        out, _ = _mutate_pcs_code("0DTJ4ZZ", Corpus(valid_pcs=set()), rng)
        assert len(out) == 7 and out != "0DTJ4ZZ"

    def test_a_code_with_no_real_neighbour_still_gets_an_error(self):
        """
        Some codes are alone in their row. Refusing to mutate would quietly
        leave the chart clean, which is worse than an implausible code — the
        trainer asked for an error on it.
        """
        corpus = Corpus(valid_pcs={"0DTJ4ZZ"})
        rng = random.Random(8)
        out, _ = _mutate_pcs_code("0DTJ4ZZ", corpus, rng)
        assert len(out) == 7 and out != "0DTJ4ZZ"

    def test_axis_data_prefers_nearby_root_operation_confusions(self):
        corpus = Corpus(
            valid_pcs={"0DBJ4ZZ", "0DTJ4ZZ", "0DWJ4ZZ"},
            pcs_axes={
                "0DTJ4ZZ": {"body_system": "Gastrointestinal System",
                            "root_operation": "Resection",
                            "body_part": "Appendix", "approach": "Percutaneous Endoscopic"},
                "0DBJ4ZZ": {"body_system": "Gastrointestinal System",
                            "root_operation": "Excision",
                            "body_part": "Appendix", "approach": "Percutaneous Endoscopic"},
                "0DWJ4ZZ": {"body_system": "Gastrointestinal System",
                            "root_operation": "Revision",
                            "body_part": "Appendix", "approach": "Percutaneous Endoscopic"},
            },
        )
        rng = random.Random(1)
        seen = {_mutate_pcs_code("0DTJ4ZZ", corpus, rng)[0] for _ in range(20)}
        assert seen == {"0DBJ4ZZ"}


# ── the weights behave as the observations describe ──────────────────────────

class TestMix:

    def test_diagnosis_substitution_prefers_cms_specificity_neighbours(self):
        corpus = Corpus(
            dx_codes=["E11.19", "I10"],
            dx_candidates_by_prefix={
                "E111": ["E11.19", "E11.11"],
                "E11": ["E11.19", "E11.22", "E11.29"],
            },
        )
        assert _substitute_dx("E11.19", corpus, random.Random(4)) == "E11.11"

    def test_omissions_dominate(self):
        """
        ~80% of real audit findings are missed codes, and 90-95% of the
        secondary-diagnosis ones are missing SDx.
        """
        adds = total = 0
        for seed in range(150):
            _, gt = generate(ip_key(), Specialty.IP_DRG, seed=seed, corpus=CORPUS)
            adds += sum(1 for r in gt if r["action"] == "Add")
            total += len(gt)
        assert total > 0
        assert 0.45 <= adds / total <= 0.80, adds / total

    def test_cc_mcc_secondaries_are_preferred_for_omission(self):
        """
        Preferred, not exclusive — an auditor who learns only CC/MCC codes go
        missing has learned the generator.
        """
        key_fn = lambda: FakeKey(
            sdx=[{"code": f"E11.{i}", "poa": "Y",
                  "ccmcc": "CC" if i < 4 else "-"} for i in range(8)],
            pcs=[{"code": "0DTJ0ZZ"}, {"code": "0DTJ1ZZ"}],
        )
        cc = plain = 0
        for seed in range(120):
            _, gt = generate(key_fn(), Specialty.IP_DRG, seed=seed, corpus=CORPUS)
            for r in gt:
                if r["action"] == "Add" and r["section"] == "SDx":
                    if str((r["entry"] or {}).get("ccmcc")).upper() in ("CC", "MCC"):
                        cc += 1
                    else:
                        plain += 1
        assert cc > plain, f"CC/MCC {cc} vs plain {plain}"
        assert plain > 0, "plain secondaries must still be drawn sometimes"

    def test_pcs_character_mutation_actually_fires(self):
        """
        Regression: substitute_pcs began life as a fallback INSIDE substitute,
        which made it unreachable — diagnosis substitution nearly always
        succeeded first, so the most realistic procedure error there is never
        appeared in a single generated claim. It needs its own weight.
        """
        kinds = []
        for seed in range(300):
            _, gt = generate(ip_key(), Specialty.IP_DRG, seed=seed, corpus=CORPUS)
            kinds += [r["kind"] for r in gt]
        pcs_share = kinds.count("substitute_pcs") / len(kinds)
        assert pcs_share > 0.03, f"only {pcs_share:.1%} — is it reachable?"

    def test_a_pcs_revision_names_which_character_moved(self):
        for seed in range(200):
            _, gt = generate(ip_key(), Specialty.IP_DRG, seed=seed, corpus=CORPUS)
            for r in gt:
                if r["kind"] == "substitute_pcs":
                    assert r["pcs_character"] in PCS_MUTABLE_POSITIONS.values()
                    assert len(r["claim_value"]) == len(r["correct_value"])

    def test_a_kind_the_corpus_cannot_support_gives_up_its_weight(self):
        """
        Feasibility is corpus-aware. Without that, the draw keeps selecting
        substitution on a chart with no prefix siblings, fails, and burns the
        retry budget — so the chart ends up with fewer plantings than asked
        for and the effective mix drifts away from the config.
        """
        # M17.x has no family in CORPUS, so substitution is impossible here.
        key = FakeKey(pdx_code="M17.0",
                      sdx=[{"code": f"M17.{i}", "poa": "", "ccmcc": ""}
                           for i in range(1, 9)],
                      cpt=[{"code": f"2744{i}", "modifier": "RT", "units": 1}
                           for i in range(4)])
        short = 0
        for seed in range(60):
            _, gt = generate(key, Specialty.SURGERY, seed=seed, corpus=CORPUS,
                             budget=3)
            if len(gt) < 3:
                short += 1
            assert all(r["kind"] != "substitute" for r in gt)
        assert short == 0, f"{short}/60 charts came up short of their budget"

    def test_the_advanced_tier_pulls_in_the_harder_kinds(self):
        def share(tier):
            hard = total = 0
            for seed in range(120):
                _, gt = generate(ip_key(), Specialty.IP_DRG, seed=seed,
                                 corpus=CORPUS, tier=tier)
                hard += sum(1 for r in gt
                            if r["kind"] in ("swap_pdx", "substitute", "substitute_pcs"))
                total += len(gt)
            return hard / max(total, 1)
        assert share("advanced") > share("foundational")

    def test_spurious_codes_survive_on_a_diagnosis_only_chart(self):
        """
        Spurious never renormalises out — you can always add a code that should
        not be there — so it grows on sparse charts rather than vanishing.
        """
        key = FakeKey(sdx=[{"code": f"E11.{i}", "poa": "", "ccmcc": ""}
                           for i in range(4)], pcs=[], cpt=[])
        kinds = set()
        for seed in range(60):
            _, gt = generate(key, Specialty.ANCILLARY, seed=seed, corpus=CORPUS)
            kinds |= {r["kind"] for r in gt}
        assert "spurious" in kinds


# ── shape-driven feasibility ─────────────────────────────────────────────────

class TestFeasibility:

    def test_a_chart_with_no_procedures_never_draws_a_procedure_mutation(self):
        key = FakeKey(sdx=[{"code": f"E11.{i}", "poa": "", "ccmcc": ""}
                           for i in range(6)], pcs=[], cpt=[])
        for seed in range(60):
            _, gt = generate(key, Specialty.ANCILLARY, seed=seed, corpus=CORPUS)
            assert all(r["section"] in ("SDx", "PDx") for r in gt)

    def test_auto_planting_never_draws_a_units_mutation(self):
        """Units are not part of the auditor coding-practice planting scope."""
        for spec, key in ((Specialty.IP_DRG, ip_key()), (Specialty.SURGERY, op_key())):
            for seed in range(60):
                _, gt = generate(key, spec, seed=seed, corpus=CORPUS)
                assert all(r.get("field") != "units" for r in gt)

    def test_a_chart_with_no_modifiers_never_draws_a_modifier_mutation(self):
        key = FakeKey(sdx=[{"code": "M17.1", "poa": "", "ccmcc": ""},
                           {"code": "M17.2", "poa": "", "ccmcc": ""}],
                      cpt=[{"code": "27447", "modifier": "", "units": 1},
                           {"code": "27448", "modifier": "", "units": 1}])
        for seed in range(60):
            _, gt = generate(key, Specialty.SURGERY, seed=seed, corpus=CORPUS)
            assert all(r.get("field") != "modifier" for r in gt)

    def test_an_outpatient_chart_can_draw_modifiers(self):
        fields = set()
        for seed in range(80):
            _, gt = generate(op_key(), Specialty.SURGERY, seed=seed, corpus=CORPUS)
            fields |= {r.get("field") for r in gt}
        assert "modifier" in fields

    def test_an_empty_key_yields_an_empty_claim_and_no_findings(self):
        claim, gt = generate(FakeKey(pdx_code="", sdx=[], pcs=[], cpt=[]),
                             Specialty.IP_DRG, seed=1, corpus=CORPUS)
        assert gt == []
        assert total_codes(claim) == 0

    def test_an_empty_corpus_still_produces_a_valid_claim(self):
        """
        A fresh install has no other keys to draw plausible wrong codes from.
        It must degrade to structural mutation, not crash.
        """
        for seed in range(30):
            claim, gt = generate(ip_key(), Specialty.IP_DRG, seed=seed,
                                 corpus=Corpus())
            assert claim["sdx"] and claim["pdx_code"]


# ── DRG impact is recorded, not inferred later ───────────────────────────────

class TestDRGImpact:

    def test_pcs_and_pdx_findings_are_always_drg_impacting(self):
        for seed in range(40):
            _, gt = generate(ip_key(), Specialty.IP_DRG, seed=seed, corpus=CORPUS)
            for r in gt:
                if r["section"] in ("PDx", "PCS"):
                    assert r["drg_impacting"] is True

    def test_a_plain_secondary_omission_is_not_drg_impacting(self):
        """
        A secondary that is neither CC nor MCC cannot move the DRG — the same
        rule grading_engine already applies to coder submissions.
        """
        seen = False
        for seed in range(80):
            _, gt = generate(ip_key(), Specialty.IP_DRG, seed=seed, corpus=CORPUS)
            for r in gt:
                if r["action"] == "Add" and r["section"] == "SDx":
                    cc = str((r["entry"] or {}).get("ccmcc")).upper()
                    if cc not in ("CC", "MCC"):
                        assert r["drg_impacting"] is False
                        seen = True
        assert seen


class TestDRGImpactIsInpatientOnly:
    """
    A DRG is an inpatient concept. Marking a wrong modifier on a Surgery chart
    "DRG-impacting" put a figure in the analytics that could not be true — the
    column read as though outpatient auditors were missing DRG movement on
    charts that never had a DRG.
    """

    def test_no_outpatient_error_is_ever_drg_impacting(self):
        for seed in range(80):
            _claim, gt = generate(op_key(), Specialty.SURGERY, seed=seed, corpus=CORPUS)
            assert all(r["drg_impacting"] is False for r in gt), \
                [r for r in gt if r["drg_impacting"]]

    def test_inpatient_pdx_and_pcs_errors_still_are(self):
        seen = False
        for seed in range(60):
            _claim, gt = generate(ip_key(), Specialty.IP_DRG, seed=seed, corpus=CORPUS)
            for r in gt:
                if r["section"] in ("PDx", "PCS"):
                    assert r["drg_impacting"] is True
                    seen = True
        assert seen

    def test_outpatient_cpt_modifier_errors_are_still_revenue_impacting(self):
        """
        The distinction the fix draws: no DRG to move, but a wrong modifier
        still drives a denial.
        """
        seen = False
        for seed in range(80):
            _claim, gt = generate(op_key(), Specialty.SURGERY, seed=seed, corpus=CORPUS)
            for r in gt:
                if r.get("field") == "modifier":
                    assert r["revenue_impacting"] is True
                    seen = True
        assert seen

    def test_a_plain_secondary_is_neither(self):
        for seed in range(60):
            _claim, gt = generate(ip_key(), Specialty.IP_DRG, seed=seed, corpus=CORPUS)
            for r in gt:
                if r["action"] == "Add" and r["section"] == "SDx" \
                        and str((r.get("entry") or {}).get("ccmcc")).upper() not in ("CC", "MCC"):
                    assert r["drg_impacting"] is False


# ── E/M levels ────────────────────────────────────────────────────────────────

def _ed_key(cpt=None):
    """An ED Facility claim: a level, and an ordinary procedure beside it."""
    return FakeKey(
        pdx_code="R07.9", pdx_poa="",
        sdx=[{"code": "I10", "poa": "", "ccmcc": ""}],
        pcs=[],
        cpt=cpt if cpt is not None else [
            {"code": "99284", "modifier": "", "units": 1},
            {"code": "36415", "modifier": "", "units": 1},
        ],
    )


def _em_key(code="99214", category="office", level_method="MDM", mdm=None):
    return FakeKey(
        pdx_code="R07.9", pdx_poa="",
        sdx=[{"code": "I10", "poa": "", "ccmcc": ""}],
        pcs=[],
        cpt=[{"code": code, "modifier": "", "units": 1}],
        mdm=mdm or {"copa": "Moderate", "dr": "Moderate", "risk": "Low"},
        em_category=category,
        level_method=level_method,
        em_code=code,
    )


def _only(kind, **over):
    """A config that can draw exactly one kind, so the test is deterministic."""
    zeros = {f: 0 for _k, f in MUTATION_KINDS}
    zeros[dict(MUTATION_KINDS)[kind]] = 100
    zeros.update(over)
    return MutationConfig(**zeros)


class TestLevelShift:
    """
    A level moves along ITS OWN ladder. A random procedure code where an E/M
    level belongs is spotted without reading the chart, which teaches auditors
    to distrust the module rather than to audit with it.
    """

    def test_the_planted_code_is_another_level_on_the_same_ladder(self):
        from services.em_levels import EMERGENCY
        for seed in range(25):
            claim, gt = generate(_ed_key(), Specialty.ED_FACILITY, seed=seed,
                                 cfg=_only("level_shift"), corpus=CORPUS, budget=1)
            if not gt:
                continue
            assert gt[0]["kind"] == "level_shift"
            assert gt[0]["claim_value"] in EMERGENCY
            assert gt[0]["correct_value"] == "99284"
            assert gt[0]["claim_value"] != "99284"

    def test_the_direction_is_recorded(self):
        seen = set()
        for seed in range(60):
            _claim, gt = generate(_ed_key(), Specialty.ED_FACILITY, seed=seed,
                                  cfg=_only("level_shift"), corpus=CORPUS, budget=1)
            if gt:
                seen.add(gt[0]["level_direction"])
        assert seen == {"up", "down"}, "levels must be planted in both directions"

    def test_the_distance_varies(self):
        """
        If every planted level error were one rung out, "check plus or minus
        one" becomes as learnable as "look for the odd code".
        """
        from services.em_levels import EMERGENCY
        steps = set()
        for seed in range(80):
            _claim, gt = generate(_ed_key(), Specialty.ED_FACILITY, seed=seed,
                                  cfg=_only("level_shift"), corpus=CORPUS, budget=1)
            if gt:
                steps.add(abs(EMERGENCY.index(gt[0]["claim_value"])
                              - EMERGENCY.index(gt[0]["correct_value"])))
        assert len(steps) > 1, f"every shift was the same distance: {steps}"

    def test_a_chart_with_no_level_cannot_draw_it(self):
        key = _ed_key(cpt=[{"code": "36415", "modifier": "", "units": 1},
                           {"code": "20610", "modifier": "", "units": 1}])
        _claim, gt = generate(key, Specialty.SDS, seed=3,
                              cfg=_only("level_shift"), corpus=CORPUS, budget=1)
        assert gt == []


class TestMDMShift:
    """
    MDM reasoning errors are fair only where the encounter is actually
    levelled by MDM. Preventive and time-based E/M charts may carry legacy MDM
    columns, but those values are not the work being audited.
    """

    def test_mdm_levelled_em_can_draw_a_reasoning_shift(self):
        claim, gt = generate(_em_key(), Specialty.EM, seed=2,
                             cfg=_only("mdm_shift"), corpus=CORPUS, budget=1)

        assert gt and gt[0]["kind"] == "mdm_shift"
        assert gt[0]["section"] == "MDM"
        assert gt[0]["field"] in {"copa", "dr", "risk"}
        assert claim["mdm"][gt[0]["field"]] == gt[0]["claim_value"]

    def test_preventive_chart_does_not_get_fake_mdm_reasoning(self):
        _claim, gt = generate(_em_key(code="99396", category="preventive"),
                              Specialty.EM, seed=2, cfg=_only("mdm_shift"),
                              corpus=CORPUS, budget=1)

        assert gt == []

    def test_time_levelled_office_chart_does_not_get_mdm_reasoning(self):
        _claim, gt = generate(_em_key(code="99214", category="office",
                                      level_method="TIME"),
                              Specialty.EM, seed=2, cfg=_only("mdm_shift"),
                              corpus=CORPUS, budget=1)

        assert gt == []

    def test_unknown_em_category_abstains_even_with_mdm_columns(self):
        _claim, gt = generate(_em_key(code="99495", category="other"),
                              Specialty.EM, seed=2, cfg=_only("mdm_shift"),
                              corpus=CORPUS, budget=1)

        assert gt == []


class TestCriticalCareBoundary:
    """
    99285 against 99291 — the hardest question in the ED, and the one planting
    that must never be generated blind.
    """

    def test_it_is_not_planted_unless_the_chart_is_marked_borderline(self):
        """
        The guard the whole design rests on. An answer key says which code is
        right; it cannot say whether the question is fair. Planted on a chart
        where critical care is plainly absent, it is spotted without reading.
        """
        for seed in range(20):
            _claim, gt = generate(_ed_key(cpt=[{"code": "99285", "modifier": "", "units": 1}]),
                                  Specialty.ED_FACILITY, seed=seed,
                                  cfg=_only("cc_boundary"), corpus=CORPUS, budget=1)
            assert gt == [], "planted without a trainer saying the chart is borderline"

    def test_a_borderline_chart_swaps_the_level_for_critical_care(self):
        claim, gt = generate(_ed_key(cpt=[{"code": "99285", "modifier": "", "units": 1}]),
                             Specialty.ED_FACILITY, seed=5,
                             cfg=_only("cc_boundary"), corpus=CORPUS, budget=1,
                             cc_boundary="borderline")
        assert gt and gt[0]["kind"] == "cc_boundary"
        assert gt[0]["correct_value"] == "99285"
        assert gt[0]["claim_value"] == "99291"
        assert gt[0]["level_direction"] == "up"

    def test_it_works_the_other_way_too(self):
        """
        Critical care was right and the claim understates it. Revenue quietly
        gone — the direction nobody watches for.
        """
        claim, gt = generate(_ed_key(cpt=[{"code": "99291", "modifier": "", "units": 1}]),
                             Specialty.ED_FACILITY, seed=5,
                             cfg=_only("cc_boundary"), corpus=CORPUS, budget=1,
                             cc_boundary="borderline")
        assert gt and gt[0]["claim_value"] == "99285"
        assert gt[0]["correct_value"] == "99291"
        assert gt[0]["level_direction"] == "down"

    def test_it_is_revenue_impacting(self):
        _claim, gt = generate(_ed_key(cpt=[{"code": "99285", "modifier": "", "units": 1}]),
                              Specialty.ED_FACILITY, seed=5,
                              cfg=_only("cc_boundary"), corpus=CORPUS, budget=1,
                              cc_boundary="borderline")
        assert gt[0]["revenue_impacting"] is True


class TestTheLevelLineIsNotDeleted:
    def test_omitting_a_procedure_never_removes_the_em_level(self):
        """
        Every encounter carries exactly one level, so a claim without one could
        not have been submitted. It is not an error a coder makes, and spending
        the procedure weight on it teaches nothing.
        """
        key = _ed_key(cpt=[{"code": "99284", "modifier": "", "units": 1},
                           {"code": "36415", "modifier": "", "units": 1},
                           {"code": "20610", "modifier": "", "units": 1}])
        for seed in range(30):
            _claim, gt = generate(key, Specialty.ED_FACILITY, seed=seed,
                                  cfg=_only("omit_proc"), corpus=CORPUS, budget=1)
            for g in gt:
                assert g.get("correct_value") != "99284", \
                    "the E/M level was deleted as if it were an ordinary procedure"

    def test_a_claim_whose_only_procedures_are_levels_cannot_omit(self):
        key = _ed_key(cpt=[{"code": "99284", "modifier": "", "units": 1},
                           {"code": "99291", "modifier": "", "units": 1}])
        _claim, gt = generate(key, Specialty.ED_FACILITY, seed=2,
                              cfg=_only("omit_proc"), corpus=CORPUS, budget=1)
        assert gt == []


class TestNothingChangesUntilTurnedOn:
    def test_em_specific_kinds_default_to_zero_weight(self):
        """
        Batches already in use must plant exactly what they planted before.
        """
        cfg = MutationConfig()
        assert cfg.mix_level_shift == 0
        assert cfg.mix_cc_boundary == 0
        assert cfg.mix_mdm_shift == 0

    def test_a_default_config_never_plants_a_level_error(self):
        kinds = set()
        for seed in range(40):
            _claim, gt = generate(_ed_key(), Specialty.ED_FACILITY, seed=seed,
                                  cfg=MutationConfig(), corpus=CORPUS, budget=2)
            kinds.update(g["kind"] for g in gt)
        assert not {"level_shift", "cc_boundary", "mdm_shift"} & kinds
