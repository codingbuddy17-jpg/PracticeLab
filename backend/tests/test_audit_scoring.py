"""
Auditor scoring: Add 40 / Revise 40 / Delete 20, renormalised over what exists.

The rules most worth pinning, because each is a quiet wrong answer if it slips:

  * NA is not zero. A chart with no spurious codes planted has no Delete
    accuracy, and its weight redistributes. Scoring it 0 marks the auditor
    wrong for an opportunity that never existed.
  * Flagging is not identifying. A finding only counts when the correction is
    right — that requirement, not any penalty, is what stops an auditor
    marking every line wrong and scoring well.
  * Component accuracies are POOLED across a session; audit accuracy is
    AVERAGED. Mixing the two bases is how a rate starts meaning something
    other than what it says.
"""
import pytest

from services.audit_scoring import (
    ChartScore, ScoringConfig, score_chart, score_session,
)


def add(code, drg=False):
    return {"section": "SDx", "action": "Add", "correct_value": code,
            "drg_impacting": drg}


def revise(line, was, now, field="code", section="SDx", drg=False):
    return {"section": section, "action": "Revise", "field": field, "line": line,
            "claim_value": was, "correct_value": now, "drg_impacting": drg}


def delete(line, code):
    return {"section": "SDx", "action": "Delete", "line": line,
            "claim_value": code, "drg_impacting": False}


# ── the weighted mean ────────────────────────────────────────────────────────

class TestWeighting:

    def test_the_worked_example_from_the_design(self):
        """4 omissions, 2 revisions, 1 spurious → 75/50/100 → 70%."""
        gt = [add("A1"), add("A2"), add("A3"), add("A4"),
              revise(0, "X", "R1"), revise(1, "Y", "R2"),
              delete(5, "D1")]
        findings = [
            {"section": "SDx", "action": "Add", "correct_value": "A1"},
            {"section": "SDx", "action": "Add", "correct_value": "A2"},
            {"section": "SDx", "action": "Add", "correct_value": "A3"},
            {"section": "SDx", "action": "Revise", "field": "code", "line": 0,
             "correct_value": "R1"},
            {"section": "SDx", "action": "Delete", "line": 5, "claim_value": "D1"},
        ]
        s = score_chart(gt, findings)
        assert s.add_accuracy == 75.0
        assert s.revise_accuracy == 50.0
        assert s.delete_accuracy == 100.0
        assert s.audit_accuracy == 70.0

    def test_a_component_with_nothing_planted_is_NA_not_zero(self):
        """
        The single most expensive thing to get wrong here. A chart with no
        spurious codes has no Delete opportunity; scoring it zero would mark
        the auditor wrong for something that never existed.
        """
        s = score_chart([add("A1"), revise(0, "X", "R1")],
                        [{"section": "SDx", "action": "Add", "correct_value": "A1"},
                         {"section": "SDx", "action": "Revise", "field": "code",
                          "line": 0, "correct_value": "R1"}])
        assert s.delete_planted == 0
        assert s.delete_accuracy is None
        assert s.audit_accuracy == 100.0

    def test_delete_weight_redistributes_when_absent(self):
        """Add and Revise take 50/50 rather than 40/40 of a missing 100."""
        s = score_chart([add("A1"), revise(0, "X", "R1")],
                        [{"section": "SDx", "action": "Add", "correct_value": "A1"}])
        assert s.add_accuracy == 100.0 and s.revise_accuracy == 0.0
        assert s.audit_accuracy == 50.0

    def test_a_single_component_carries_the_whole_weight(self):
        s = score_chart([add("A1"), add("A2")],
                        [{"section": "SDx", "action": "Add", "correct_value": "A1"}])
        assert s.audit_accuracy == 50.0

    def test_an_omission_only_auditor_caps_at_the_add_weight(self):
        """
        The reason components beat a flat findings ratio: ~75% of plantings are
        omissions, so a flat ratio rewards someone who only hunts missing
        codes. Here they cap at 40.
        """
        gt = [add("A1"), add("A2"), add("A3"), add("A4"), add("A5"), add("A6"),
              revise(0, "X", "R1"), delete(3, "D1")]
        findings = [{"section": "SDx", "action": "Add", "correct_value": c}
                    for c in ("A1", "A2", "A3", "A4", "A5", "A6")]
        s = score_chart(gt, findings)
        assert s.add_accuracy == 100.0
        assert s.audit_accuracy == 40.0

    def test_weights_are_configurable(self):
        """
        Add missed, Delete found, Revise absent. Renormalisation runs over the
        components that exist — Add 10 and Delete 80 share a base of 90, so
        the answer is 8000/90, not 80. Revise's share is not silently lost.
        """
        cfg = ScoringConfig(add_weight=10, revise_weight=10, delete_weight=80)
        s = score_chart([add("A1"), delete(0, "D1")],
                        [{"section": "SDx", "action": "Delete", "line": 0,
                          "claim_value": "D1"}], cfg=cfg)
        assert s.audit_accuracy == 88.89


# ── clean charts ─────────────────────────────────────────────────────────────

class TestCleanCharts:

    def test_a_clean_chart_left_alone_scores_100(self):
        s = score_chart([], [])
        assert s.is_clean and s.audit_accuracy == 100.0
        assert (s.add_accuracy, s.revise_accuracy, s.delete_accuracy) == (None, None, None)

    def test_a_clean_chart_with_a_non_revenue_over_call_loses_5(self):
        s = score_chart([], [{"section": "SDx", "action": "Add",
                              "correct_value": "I10"}])
        assert s.over_call_tier == "non_revenue"
        assert s.audit_accuracy == 95.0

    def test_a_clean_chart_with_a_revenue_over_call_loses_20(self):
        s = score_chart([], [{"section": "PDx", "action": "Revise",
                              "field": "code", "line": 0, "correct_value": "J18.9"}])
        assert s.over_call_tier == "revenue"
        assert s.audit_accuracy == 80.0

    def test_a_clean_chart_bottoms_out_at_80(self):
        """
        There is nothing to fail at, only something to leave alone — so the
        floor is the deduction, not zero.
        """
        s = score_chart([], [{"section": "PDx", "action": "Revise", "field": "code",
                              "line": 0, "correct_value": "X"}] * 9)
        assert s.audit_accuracy == 80.0


# ── the over-call deduction ──────────────────────────────────────────────────

class TestOverCalls:

    def test_the_deduction_is_flat_not_per_finding(self):
        one = score_chart([], [{"section": "SDx", "action": "Add", "correct_value": "I10"}])
        six = score_chart([], [{"section": "SDx", "action": "Add", "correct_value": f"I1{i}"}
                               for i in range(6)])
        assert one.audit_accuracy == six.audit_accuracy == 95.0
        assert six.over_calls == 6

    def test_the_higher_tier_wins_and_they_do_not_stack(self):
        s = score_chart([], [
            {"section": "SDx", "action": "Add", "correct_value": "I10"},
            {"section": "PCS", "action": "Revise", "field": "code", "line": 0,
             "correct_value": "0DTJ0ZZ"},
        ])
        assert s.over_call_tier == "revenue"
        assert s.audit_accuracy == 80.0

    def test_modifier_and_units_count_as_revenue_impacting(self):
        """
        Inferred rather than stated by the user: a wrong modifier drives
        denials and wrong units are overbilling. Configurable if that changes.
        """
        for fld in ("modifier", "units"):
            s = score_chart([], [{"section": "CPT", "action": "Revise",
                                  "field": fld, "line": 0, "correct_value": "51"}])
            assert s.over_call_tier == "revenue", fld

    def test_a_cc_mcc_secondary_over_call_is_revenue_impacting(self):
        s = score_chart([], [{"section": "SDx", "action": "Revise", "field": "code",
                              "line": 0, "correct_value": "E11.22", "ccmcc": "MCC"}])
        assert s.over_call_tier == "revenue"

    def test_the_deduction_applies_on_opportunity_charts_too(self):
        s = score_chart([add("A1"), add("A2")],
                        [{"section": "SDx", "action": "Add", "correct_value": "A1"},
                         {"section": "SDx", "action": "Add", "correct_value": "ZZZ"}])
        assert s.add_accuracy == 50.0
        assert s.over_calls == 1
        assert s.audit_accuracy == 45.0

    def test_a_score_never_goes_below_zero(self):
        s = score_chart([add("A1")],
                        [{"section": "PDx", "action": "Revise", "field": "code",
                          "line": 0, "correct_value": "X"}],
                        query_expected=True, query_flagged=False)
        assert s.audit_accuracy == 0.0


# ── found AND corrected ──────────────────────────────────────────────────────

class TestCorrectionRequired:

    def test_the_right_line_with_the_wrong_correction_does_not_count(self):
        """
        A finding that reaches the wrong corrected code does not fix the claim.
        This requirement is what makes flagging-everything worthless.
        """
        s = score_chart([revise(2, "0DTJ4ZZ", "0DTJ0ZZ", section="PCS")],
                        [{"section": "PCS", "action": "Revise", "field": "code",
                          "line": 2, "correct_value": "0DTJ9ZZ"}])
        assert s.revise_found == 0
        assert s.revise_accuracy == 0.0
        assert s.detected_not_corrected == 1

    def test_detected_but_wrongly_corrected_is_reported_not_scored(self):
        """
        "Found 4 of 4, corrected 2" and "found 2 of 4" both come out at 50% and
        are entirely different coaching conversations.
        """
        gt = [revise(0, "a", "A"), revise(1, "b", "B")]
        wrong = score_chart(gt, [
            {"section": "SDx", "action": "Revise", "field": "code", "line": 0,
             "correct_value": "A"},
            {"section": "SDx", "action": "Revise", "field": "code", "line": 1,
             "correct_value": "ZZZ"},
        ])
        missed = score_chart(gt, [
            {"section": "SDx", "action": "Revise", "field": "code", "line": 0,
             "correct_value": "A"},
        ])
        assert wrong.audit_accuracy == missed.audit_accuracy == 50.0
        assert wrong.detected_not_corrected == 1
        assert missed.detected_not_corrected == 0

    def test_deleting_needs_no_correction(self):
        """The action IS the correction — there is nothing to supply."""
        s = score_chart([delete(3, "I10")],
                        [{"section": "SDx", "action": "Delete", "line": 3}])
        assert s.delete_accuracy == 100.0

    def test_a_wrongly_corrected_finding_is_not_also_an_over_call(self):
        """
        They looked in the right place and got the judgement wrong. That is a
        miss, not an invention, and the deduction is about invention.
        """
        s = score_chart([revise(0, "a", "A")],
                        [{"section": "SDx", "action": "Revise", "field": "code",
                          "line": 0, "correct_value": "WRONG"}])
        assert s.over_calls == 0
        assert s.over_call_deduction == 0.0
        assert s.audit_accuracy == 0.0

    def test_the_right_action_on_the_wrong_field_does_not_match(self):
        s = score_chart([revise(0, "Y", "N", field="poa")],
                        [{"section": "SDx", "action": "Revise", "field": "code",
                          "line": 0, "correct_value": "N"}])
        assert s.revise_found == 0
        assert s.over_calls == 1

    def test_formatting_differences_do_not_fail_a_correct_answer(self):
        s = score_chart([revise(0, "E119", "E1122")],
                        [{"section": "SDx", "action": "Revise", "field": "code",
                          "line": 0, "correct_value": " e11.22 "}])
        assert s.revise_accuracy == 100.0


# ── matching rules ───────────────────────────────────────────────────────────

class TestMatching:

    def test_an_add_is_matched_on_the_code_not_a_line(self):
        """A missing code has no line, and the auditor chooses where to put it."""
        s = score_chart([add("N17.9")],
                        [{"section": "SDx", "action": "Add",
                          "correct_value": "N17.9", "line": 99}])
        assert s.add_accuracy == 100.0

    def test_a_delete_matches_on_the_code_when_the_index_has_moved(self):
        s = score_chart([delete(4, "I10")],
                        [{"section": "SDx", "action": "Delete", "line": 2,
                          "claim_value": "I10"}])
        assert s.delete_accuracy == 100.0

    def test_one_finding_cannot_satisfy_two_plantings(self):
        s = score_chart([add("A1"), add("A1")],
                        [{"section": "SDx", "action": "Add", "correct_value": "A1"}])
        assert s.add_found == 1
        assert s.add_accuracy == 50.0

    def test_the_wrong_action_on_the_right_line_is_a_miss_and_an_over_call(self):
        s = score_chart([revise(0, "a", "A")],
                        [{"section": "SDx", "action": "Delete", "line": 0,
                          "claim_value": "a"}])
        assert s.revise_found == 0
        assert s.over_calls == 1


# ── query ────────────────────────────────────────────────────────────────────

class TestQuery:

    def test_no_authored_answer_means_NA_and_no_deduction(self):
        """
        Auto-planted charts carry no query ground truth. The system cannot read
        whether documentation supported a code, so an unauthored answer is not
        an answer — and must not be scored as False.
        """
        s = score_chart([], [], query_expected=None, query_flagged=True)
        assert s.query_correct is None
        assert s.query_deduction == 0.0
        assert s.audit_accuracy == 100.0

    def test_missing_a_needed_query_costs_20(self):
        s = score_chart([], [], query_expected=True, query_flagged=False)
        assert s.query_correct is False
        assert s.audit_accuracy == 80.0

    def test_raising_an_unnecessary_query_also_costs_20(self):
        """Symmetric by decision — wrong either way is one error of judgement."""
        s = score_chart([], [], query_expected=False, query_flagged=True)
        assert s.audit_accuracy == 80.0

    def test_a_correct_query_call_costs_nothing(self):
        for expected in (True, False):
            s = score_chart([], [], query_expected=expected, query_flagged=expected)
            assert s.query_correct is True
            assert s.audit_accuracy == 100.0

    def test_query_applies_to_clean_charts_too(self):
        """
        A correctly coded claim can still be one where documentation is
        ambiguous — which is what gives clean charts a second job beyond
        restraint.
        """
        s = score_chart([], [], query_expected=True, query_flagged=True)
        assert s.is_clean and s.audit_accuracy == 100.0

    def test_query_and_over_call_deductions_both_apply(self):
        s = score_chart([], [{"section": "SDx", "action": "Add", "correct_value": "I10"}],
                        query_expected=True, query_flagged=False)
        assert s.audit_accuracy == 75.0


# ── the session ──────────────────────────────────────────────────────────────

def _clean(score=100.0):
    c = ChartScore(is_clean=True)
    c.audit_accuracy = c.base_accuracy = score
    return c


class TestSession:

    def test_audit_accuracy_is_the_average_of_chart_scores(self):
        charts = [score_chart([add("A")], [{"section": "SDx", "action": "Add",
                                            "correct_value": "A"}]),
                  score_chart([add("B")], [])]
        s = score_session(charts)
        assert s.audit_accuracy == 50.0

    def test_component_accuracy_is_pooled_not_averaged(self):
        """
        Averaging per-chart rates would let a chart with one planting count as
        much as a chart with six — how a rate quietly starts meaning something
        other than what it says.
        """
        big = score_chart([add(f"A{i}") for i in range(6)],
                          [{"section": "SDx", "action": "Add", "correct_value": "A0"}])
        small = score_chart([add("Z")], [{"section": "SDx", "action": "Add",
                                          "correct_value": "Z"}])
        s = score_session([big, small])
        # Pooled: 2 of 7. Averaged would be (16.67 + 100) / 2 = 58.3%.
        assert s.add_planted == 7 and s.add_found == 2
        assert s.add_accuracy == 28.57

    def test_clean_and_opportunity_charts_are_reported_separately(self):
        """
        Otherwise the headline blends restraint with detection and hides which
        one is weak.
        """
        s = score_session([_clean(100.0), _clean(80.0),
                           score_chart([add("A")], []),
                           score_chart([add("B")], [{"section": "SDx", "action": "Add",
                                                     "correct_value": "B"}])])
        assert s.clean_charts == 2 and s.opportunity_charts == 2
        assert s.clean_accuracy == 90.0
        assert s.opportunity_accuracy == 50.0
        assert s.audit_accuracy == 70.0

    def test_a_session_of_only_clean_charts_reports_no_detection_verdict(self):
        s = score_session([_clean(), _clean(), _clean()])
        assert s.opportunities == 0
        assert s.pass_fail is None
        assert "restraint" in s.verdict_withheld_reason
        assert s.opportunity_accuracy is None

    def test_a_verdict_is_withheld_below_the_opportunity_floor(self):
        """
        Chart scores are quantised by planting count, so a verdict on a
        two-planting session would be noise dressed as judgement.
        """
        charts = [score_chart([add(f"A{i}")], [{"section": "SDx", "action": "Add",
                                                "correct_value": f"A{i}"}])
                  for i in range(4)]
        s = score_session(charts)
        assert s.opportunities == 4
        assert s.pass_fail is None
        assert "review lines for verdict" in s.verdict_withheld_reason

    def test_a_verdict_needs_enough_CODES_REVIEWED_not_enough_errors(self):
        """
        The verdict moved to the Review Score, so the floor is counted in code
        lines rather than plantings. Detection is quantised by planting count —
        a chart with one error can only score 0 or 100 — which made a verdict
        on it noise until a session ran long enough to be impractical.
        """
        claim = {"pdx_code": "J18.9",
                 "sdx": [{"code": f"E11.{i}"} for i in range(9)]}
        perfect = [{"section": "SDx", "action": "Add", "correct_value": "A0"}]
        charts = [score_chart([add("A0")], perfect, claim=claim) for _ in range(6)]
        s = score_session(charts)
        assert s.review_total >= 50
        assert s.review_score == 100.0
        assert s.pass_fail == "PASS"
        assert s.verdict_withheld_reason is None

    def test_a_short_session_withholds_the_verdict(self):
        claim = {"pdx_code": "J18.9", "sdx": [{"code": "E11.1"}]}
        s = score_session([score_chart([], [], claim=claim) for _ in range(2)])
        assert s.pass_fail is None
        assert "review lines for verdict" in (s.verdict_withheld_reason or "")

    def test_the_pass_bar_is_90_on_the_blended_audit_score(self):
        """
        The verdict is decided on the Audit Score — detection and review
        weighted together, 50/50 by default. Missing every error tanks
        detection to 0, so no amount of correct reviewing carries the session.
        """
        claim = {"pdx_code": "J18.9",
                 "sdx": [{"code": f"E11.{i}"} for i in range(9)]}
        gt = [revise(i, "E11.9", "E11.8") for i in range(1)]

        missed = score_session([score_chart(gt, [], claim=claim) for _ in range(6)])
        assert missed.review_score == 90.0        # reviewing was near-perfect
        assert missed.audit_accuracy == 0.0       # but nothing was found
        assert missed.audit_score == 45.0         # 0*0.5 + 90*0.5
        assert missed.pass_fail == "FAIL"

        found = [{"section": "SDx", "action": "Revise", "line": 0,
                  "field": "code", "correct_value": "E11.8"}]
        perfect = score_session(
            [score_chart(gt, found, claim=claim) for _ in range(6)])
        assert perfect.audit_score == 100.0
        assert perfect.pass_fail == "PASS"

    def test_the_weights_are_configurable(self):
        """A trainer who cares more about detection can say so."""
        claim = {"pdx_code": "J18.9",
                 "sdx": [{"code": f"E11.{i}"} for i in range(9)]}
        gt = [revise(0, "E11.9", "E11.8")]
        charts = [score_chart(gt, [], claim=claim) for _ in range(6)]

        even = score_session(charts, ScoringConfig())
        heavy = score_session(charts, ScoringConfig(detection_weight=80,
                                                    review_weight=20))
        assert even.audit_score == 45.0           # 0*.5 + 90*.5
        assert heavy.audit_score == 18.0          # 0*.8 + 90*.2
        assert heavy.audit_score < even.audit_score

    def test_an_absent_half_renormalises_rather_than_dragging_to_zero(self):
        """A session with nothing reviewed reports its detection alone."""
        s = score_session([score_chart([], [])])   # no claim, so no lines
        assert s.review_score is None
        assert s.audit_score == s.audit_accuracy

    def test_drg_impacting_accuracy_is_its_own_number(self):
        """
        Never blended into the headline as a weight — that is the percentage
        without a denominator trap.
        """
        gt = [add("MCC1", drg=True), add("MCC2", drg=True), add("PLAIN")]
        s = score_session([score_chart(gt, [
            {"section": "SDx", "action": "Add", "correct_value": "PLAIN"},
            {"section": "SDx", "action": "Add", "correct_value": "MCC1"},
        ])])
        assert s.add_accuracy == 66.67
        assert s.drg_impacting_planted == 2 and s.drg_impacting_found == 1
        assert s.drg_accuracy == 50.0

    def test_query_accuracy_counts_only_charts_that_authored_an_answer(self):
        charts = [
            score_chart([], [], query_expected=True, query_flagged=True),
            score_chart([], [], query_expected=False, query_flagged=True),
            score_chart([], [], query_expected=None, query_flagged=False),
        ]
        s = score_session(charts)
        assert s.query_charts == 2
        assert s.query_correct == 1
        assert s.query_accuracy == 50.0

    def test_a_session_with_no_queries_reports_NA(self):
        s = score_session([_clean(), _clean()])
        assert s.query_charts == 0
        assert s.query_accuracy is None

    def test_an_empty_session_does_not_divide_by_zero(self):
        s = score_session([])
        assert s.charts == 0 and s.audit_accuracy == 0.0
        assert s.add_accuracy is None
