"""
Unit tests for the grading engine (services/grading_engine.py).
Pure function tests — no database needed. Covers IP and OP grading,
DRG flag triggers, DPO scoring, and edge cases.
"""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

import pytest
from services.grading_engine import (
    grade_ip, grade_op,
    compute_dpo_ip, compute_dpo_op, compute_dpo_ed_single_path,
    finalize_ip_score,
    IPAnswerKey, OPAnswerKey, EDSinglePathAnswerKey,
    IPSubmission, OPSubmission, EDSinglePathSubmission,
    IPScoringCfg, OPScoringCfg,
    norm_dx, norm_pcs, norm_cpt,
)


# ── Code normalisation ─────────────────────────────────────────────────────────

class TestNormalisation:
    def test_norm_dx_basic(self):
        # norm_dx strips dots and spaces, uppercases
        result = norm_dx("J18.9")
        assert result == result.upper()           # always uppercase
        assert norm_dx("j18.9") == norm_dx("J18.9")  # case insensitive
        assert norm_dx("") == ""

    def test_norm_dx_uppercases(self):
        result = norm_dx("j18.9")
        assert result == result.upper()

    def test_norm_pcs_strips_spaces(self):
        result = norm_pcs("0BH N3BZ")
        assert " " not in result
        assert result == "0BHN3BZ"

    def test_norm_cpt_strips_spaces(self):
        assert norm_cpt(" 99213 ") == "99213"

    def test_norm_pcs_replaces_letter_o_with_zero(self):
        # O→0 and I→1 substitution
        result = norm_pcs("OBHN3BZ")
        assert "O" not in result

    def test_norm_dx_handles_none(self):
        result = norm_dx(None)
        assert result == ""


# ── IP Grading ─────────────────────────────────────────────────────────────────

class TestIPGrading:
    """grade_ip returns IPGradingResult: pdx_score, sdx_score, pcs_score, drg_flag, feedback.
       Total score and pass/fail come from finalize_ip_score."""

    def _ak(self, pdx="J18.9", sdx=None, pcs=None):
        return IPAnswerKey(
            pdx_code=pdx,
            pdx_poa="Y",
            sdx=sdx if sdx is not None else [{"code": "E11.65", "poa": "Y", "ccmcc": "CC"}],
            pcs=pcs if pcs is not None else [{"code": "3E0336Z"}],
        )

    def _sub(self, pdx="J18.9", sdx=None, pcs=None):
        return IPSubmission(
            pdx_code=pdx,
            pdx_poa="Y",
            sdx=sdx if sdx is not None else [{"code": "E11.65", "poa": "Y"}],
            pcs=pcs if pcs is not None else [{"code": "3E0336Z"}],
        )

    def _total(self, result, cfg=None):
        cfg = cfg or IPScoringCfg()
        total, _, _ = finalize_ip_score(
            result.pdx_score, result.sdx_score, result.pcs_score,
            result.drg_flag, cfg.drg_weight, cfg.pass_threshold
        )
        return total

    def _passed(self, result, cfg=None):
        cfg = cfg or IPScoringCfg()
        _, pass_fail, _ = finalize_ip_score(
            result.pdx_score, result.sdx_score, result.pcs_score,
            result.drg_flag, cfg.drg_weight, cfg.pass_threshold
        )
        return pass_fail == "PASS"

    def test_perfect_score(self):
        result = grade_ip(self._ak(), self._sub())
        assert self._total(result) == 100

    def test_wrong_pdx_loses_points(self):
        result = grade_ip(self._ak(), self._sub(pdx="A41.9"))
        assert result.pdx_score == 0
        assert self._total(result) < 100

    def test_correct_pdx_full_points(self):
        result = grade_ip(self._ak(), self._sub())
        assert result.pdx_score == IPScoringCfg().pdx_weight

    def test_missing_pcs_when_ak_has_pcs(self):
        result = grade_ip(self._ak(), self._sub(pcs=[]))
        assert result.pcs_score < IPScoringCfg().pcs_weight

    def test_extra_pcs_overcoding_penalty(self):
        sub = self._sub(pcs=[{"code": "3E0336Z"}, {"code": "0DT64ZZ"}])
        result = grade_ip(self._ak(pcs=[{"code": "3E0336Z"}]), sub)
        assert result.pcs_score < IPScoringCfg().pcs_weight

    def test_drg_flag_on_pdx_mismatch(self):
        result = grade_ip(self._ak(), self._sub(pdx="A41.9"))
        assert result.drg_flag is True

    def test_no_drg_flag_on_perfect(self):
        result = grade_ip(self._ak(), self._sub())
        assert result.drg_flag is False

    def test_pass_at_perfect_score(self):
        result = grade_ip(self._ak(), self._sub())
        assert self._passed(result) is True

    def test_fail_when_pdx_and_pcs_wrong(self):
        result = grade_ip(self._ak(), self._sub(pdx="WRONG", pcs=[]))
        assert self._passed(result) is False

    def test_case_insensitive_dx_codes(self):
        result = grade_ip(self._ak(pdx="J18.9"), self._sub(pdx="j18.9"))
        assert result.pdx_score == IPScoringCfg().pdx_weight

    def test_sdx_partial_credit(self):
        ak = self._ak(sdx=[
            {"code": "E11.65", "poa": "Y", "ccmcc": "CC"},
            {"code": "I10",    "poa": "Y", "ccmcc": ""},
        ])
        sub = self._sub(sdx=[{"code": "E11.65", "poa": "Y"}])
        result = grade_ip(ak, sub)
        assert 0 < result.sdx_score < IPScoringCfg().sdx_weight

    def test_feedback_populated_on_error(self):
        result = grade_ip(self._ak(), self._sub(pdx="A41.9"))
        assert len(result.feedback) > 0


# ── OP Grading ─────────────────────────────────────────────────────────────────

class TestOPGrading:
    """grade_op returns OPGradingResult which DOES have total_score and pass_fail directly."""

    def _ak(self):
        return OPAnswerKey(
            pdx_code="M79.3",
            sdx=[{"code": "E11.65"}],
            cpt=[{"code": "20610", "modifier": ""}],
        )

    def _sub(self, pdx="M79.3", cpt=None):
        return OPSubmission(
            pdx_code=pdx,
            sdx=[{"code": "E11.65"}],
            cpt=cpt if cpt is not None else [{"code": "20610", "modifier": ""}],
        )

    def test_perfect_op_score(self):
        result = grade_op(self._ak(), self._sub())
        assert result.total_score == 100

    def test_wrong_op_pdx(self):
        result = grade_op(self._ak(), self._sub(pdx="M54.5"))
        assert result.pdx_score == 0
        assert result.total_score < 100

    def test_wrong_cpt(self):
        result = grade_op(self._ak(), self._sub(cpt=[{"code": "99213", "modifier": ""}]))
        assert result.cpt_score < OPScoringCfg().cpt_weight

    def test_op_pass_threshold(self):
        result = grade_op(self._ak(), self._sub())
        assert result.pass_fail == "PASS"

    def test_op_fail_wrong_pdx(self):
        result = grade_op(self._ak(), self._sub(pdx="WRONG", cpt=[]))
        assert result.pass_fail == "FAIL"


# ── finalize_ip_score ──────────────────────────────────────────────────────────

class TestFinalizeIPScore:
    # finalize_ip_score(pdx, sdx, pcs, drg_error: bool, drg_weight=40, pass_threshold=80)
    def test_perfect_returns_100(self):
        cfg = IPScoringCfg()
        total, pass_fail, _ = finalize_ip_score(
            cfg.pdx_weight, cfg.sdx_weight, cfg.pcs_weight,
            False, cfg.drg_weight, cfg.pass_threshold
        )
        assert total == 100
        assert pass_fail == "PASS"

    def test_drg_flag_removes_drg_score(self):
        cfg = IPScoringCfg()
        total_no_flag, _, _ = finalize_ip_score(
            cfg.pdx_weight, cfg.sdx_weight, cfg.pcs_weight,
            False, cfg.drg_weight, cfg.pass_threshold
        )
        total_with_flag, _, _ = finalize_ip_score(
            cfg.pdx_weight, cfg.sdx_weight, cfg.pcs_weight,
            True, cfg.drg_weight, cfg.pass_threshold
        )
        assert total_with_flag < total_no_flag

    def test_all_zero_with_drg_error(self):
        # drg_error=True means DRG score is 0, so all components zero → total=0
        total, pass_fail, drg_score = finalize_ip_score(0, 0, 0, True, 40, 80)
        assert drg_score == 0
        assert total == 0
        assert pass_fail == "FAIL"

    def test_custom_pass_threshold(self):
        # PDx(20) + SDx(20) + PCS(20) = 60 pts, drg_error=False → DRG(40) → total=100
        # Lower that: PDx(20)+SDx(20)+PCS(0), drg_error=True → drg=0 → total=40
        _, pass_easy, _ = finalize_ip_score(20, 20, 0, True, 40, 30)   # 40 >= 30 → PASS
        _, pass_hard, _ = finalize_ip_score(20, 20, 0, True, 40, 50)   # 40 < 50 → FAIL
        assert pass_easy == "PASS"
        assert pass_hard == "FAIL"


# ── DPO scoring ────────────────────────────────────────────────────────────────

class TestDPOScoring:
    """DPOResult has: dx, poa, proc (DPOSection), overall_accuracy (float 0–100)."""

    def test_dpo_ip_perfect_overall_accuracy(self):
        ak = IPAnswerKey(
            pdx_code="J18.9", pdx_poa="Y",
            sdx=[{"code": "E11.65", "poa": "Y", "ccmcc": "CC"}],
            pcs=[{"code": "3E0336Z"}],
        )
        sub = IPSubmission(
            pdx_code="J18.9", pdx_poa="Y",
            sdx=[{"code": "E11.65", "poa": "Y"}],
            pcs=[{"code": "3E0336Z"}],
        )
        result = compute_dpo_ip(ak, sub, overcoding_penalty=True)
        assert result.overall_accuracy == pytest.approx(100.0, abs=0.1)

    def test_dpo_ip_wrong_pdx_reduces_accuracy(self):
        ak = IPAnswerKey(pdx_code="J18.9", pdx_poa="Y", sdx=[], pcs=[])
        sub = IPSubmission(pdx_code="A41.9", pdx_poa="Y", sdx=[], pcs=[])
        result = compute_dpo_ip(ak, sub, overcoding_penalty=True)
        assert result.overall_accuracy < 100.0

    def test_dpo_op_perfect(self):
        ak = OPAnswerKey(pdx_code="M79.3", sdx=[], cpt=[{"code": "20610", "modifier": ""}])
        sub = OPSubmission(pdx_code="M79.3", sdx=[], cpt=[{"code": "20610", "modifier": ""}])
        result = compute_dpo_op(ak, sub, overcoding_penalty=True)
        assert result.overall_accuracy == pytest.approx(100.0, abs=0.1)

    def test_dpo_ed_single_path_counts_levels_without_pointers(self):
        ak = EDSinglePathAnswerKey(
            pdx_code="S61.401A",
            sdx=[],
            cpt=[{"code": "12001", "modifier": "", "pointers": ["A"]}],
            facility_level="99283",
            profee_level="99284",
        )
        sub = EDSinglePathSubmission(
            pdx_code="S61.401A",
            sdx=[],
            cpt=[{"code": "12001", "modifier": "", "pointers": ["B"]}],
            facility_level="99283",
            profee_level="99282",
        )
        result = compute_dpo_ed_single_path(ak, sub, overcoding_penalty=True)
        assert result.proc.opportunities == 3
        assert result.proc.defects == 1

    def test_dpo_result_has_sections(self):
        ak = IPAnswerKey(pdx_code="J18.9", pdx_poa="Y", sdx=[], pcs=[])
        sub = IPSubmission(pdx_code="J18.9", pdx_poa="Y", sdx=[], pcs=[])
        result = compute_dpo_ip(ak, sub, overcoding_penalty=True)
        assert hasattr(result, "dx")
        assert hasattr(result, "poa")
        assert hasattr(result, "proc")
        assert hasattr(result.dx, "opportunities")
        assert hasattr(result.dx, "defects")


# ── _shuffle_options via grade path ────────────────────────────────────────────

class TestShuffleOptions:
    """_shuffle_options takes an ORM AssessmentQuestion object."""

    def make_orm_q(self, correct="A"):
        class Q:
            option_a = "Apple"
            option_b = "Banana"
            option_c = "Cherry"
            option_d = "Date"
            correct_answer = correct
            shuffle_options = True
            question_text = "Q1"
            question_id = "Q1"
            topic = "Test"
            specialty = "IPDRG"
            difficulty = "Medium"
            question_type = "Conceptual"
            id = 1
        return Q()

    def test_correct_answer_text_preserved(self):
        from routers.assessment_pkg.generation import _shuffle_options
        for _ in range(50):
            q = self.make_orm_q(correct="B")
            result = _shuffle_options(q)
            new_letter = result["correct_answer"]
            new_text = result[f"option_{new_letter.lower()}"]
            assert new_text == "Banana", \
                f"Correct answer text changed: 'Banana' → '{new_text}'"

    def test_all_options_present_after_shuffle(self):
        from routers.assessment_pkg.generation import _shuffle_options
        q = self.make_orm_q()
        result = _shuffle_options(q)
        result_texts = {result["option_a"], result["option_b"],
                        result["option_c"], result["option_d"]}
        assert result_texts == {"Apple", "Banana", "Cherry", "Date"}

    def test_returns_dict(self):
        from routers.assessment_pkg.generation import _shuffle_options
        q = self.make_orm_q()
        result = _shuffle_options(q)
        assert isinstance(result, dict)

    def test_produces_variation_over_runs(self):
        from routers.assessment_pkg.generation import _shuffle_options
        q = self.make_orm_q(correct="A")
        letters = {_shuffle_options(q)["correct_answer"] for _ in range(50)}
        assert len(letters) > 1, "Options never reshuffled — shuffle not working"


# ── Edge cases ─────────────────────────────────────────────────────────────────

class TestEdgeCases:
    def test_empty_ip_submission_scores_zero_where_ak_has_codes(self):
        ak = IPAnswerKey(
            pdx_code="J18.9", pdx_poa="Y",
            sdx=[{"code": "E11.65", "poa": "Y", "ccmcc": "CC"}],
            pcs=[{"code": "3E0336Z"}],
        )
        sub = IPSubmission(pdx_code="", pdx_poa="", sdx=[], pcs=[])
        result = grade_ip(ak, sub)
        assert result.pdx_score == 0
        cfg = IPScoringCfg()
        total, pass_fail, _ = finalize_ip_score(
            result.pdx_score, result.sdx_score, result.pcs_score,
            result.drg_flag, cfg.drg_weight, cfg.pass_threshold
        )
        assert total == 0
        assert pass_fail == "FAIL"

    def test_whitespace_codes_match(self):
        ak = IPAnswerKey(pdx_code="J18.9", pdx_poa="Y", sdx=[], pcs=[])
        sub = IPSubmission(pdx_code=" J18.9 ", pdx_poa="Y", sdx=[], pcs=[])
        result = grade_ip(ak, sub)
        assert result.pdx_score == IPScoringCfg().pdx_weight

    def test_grade_ip_does_not_raise_on_empty_ak(self):
        ak = IPAnswerKey(pdx_code="", pdx_poa="", sdx=[], pcs=[])
        sub = IPSubmission(pdx_code="J18.9", pdx_poa="Y",
                           sdx=[{"code": "E11.65", "poa": "Y"}],
                           pcs=[{"code": "3E0336Z"}])
        result = grade_ip(ak, sub)
        assert isinstance(result.pdx_score, int)
