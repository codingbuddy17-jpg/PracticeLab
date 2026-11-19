"""
The post-submit review: what was right as well as wrong, and its Excel export.

Grading's `feedback` lists only what lost points. These tests pin the full
side-by-side that both review screens and the workbook render from
services/practice_review.build_review — and, for E/M, that the element rows
explain the reasoning points (the "6.7 of 10" a trainer could not reproduce).
"""
import io
import json

from openpyxl import load_workbook
from sqlalchemy import text

from conftest import make_chart
from models import Specialty
from routers.practicelab_pkg.em_grading import (
    COPA_FIELDS, DR_FIELDS, RISK_FIELDS, grade_em_chart,
)
from routers.practicelab_pkg.practice_sessions import (
    _em_feedback_items, _em_submission_dict,
)
from services.practice_review import ELEMENT_LABELS, build_review
from test_practice_submission_phase3a import _add_answer_key, _coder_session, _entry

CFG = {"line1_weight": 70.0, "line2_weight": 30.0, "em_level_weight": 23.33,
       "cpt_weight": 23.33, "dx_weight": 23.34, "copa_weight": 10.0,
       "dr_weight": 10.0, "risk_weight": 10.0, "pass_threshold": 80.0,
       "overcoding_penalty": True}

AK = {"em_code": "99214", "em_category": None, "level_method": "MDM",
      "patient_type": "ESTABLISHED",
      "dx_codes": json.dumps(["E11.9", "I10", "J45.909"]), "procedure_cpts": "[]",
      "copa_stable_chronic": 1, "copa_chronic_exacerbation": 1,
      "copa_acute_uncomplicated": 1, "dr_review_test_results": 2,
      "risk_prescription_drug_mgmt": 1,
      "copa_level": "Moderate", "dr_level": "Limited", "risk_level": "Moderate"}

EM = {"em_code": "99214", "level_method": "MDM", "patient_type": "ESTABLISHED",
      "em_dx": [{"code": "I10"}, {"code": "E11.9"}], "em_cpt": [],
      "copa_stable_chronic": True, "copa_chronic_exacerbation": True,
      "copa_undiagnosed_new": True, "dr_review_test_results": 3,
      "risk_prescription_drug_mgmt": True}


def _em_review():
    scoring = grade_em_chart(AK, _em_submission_dict(EM), CFG)
    r = {"specialty": "E/M",
         "feedback": _em_feedback_items(scoring, AK, EM, CFG),
         "sdx_submitted": EM["em_dx"],
         "sdx_answer_key": [{"code": c} for c in json.loads(AK["dx_codes"])],
         "cpt_submitted": [], "cpt_answer_key": []}
    return scoring, build_review(r, AK, EM, CFG)


def _sec(review, key):
    return next(s for s in review["sections"] if s["key"] == key)


def _row(section, item):
    return next(r for r in section["rows"] if r["item"] == item)


# ── every scored element can be shown ─────────────────────────────────────────

def test_every_scored_mdm_element_has_a_review_label():
    """
    Per FIELD, not per file: an element the grader scores but the review cannot
    name would leave its points unexplained — the exact complaint this fixes.
    """
    for field in COPA_FIELDS + DR_FIELDS + RISK_FIELDS:
        assert field in ELEMENT_LABELS, field


# ── E/M: the reasoning points explain themselves ──────────────────────────────

def test_copa_two_of_three_elements_reads_as_six_point_seven():
    scoring, review = _em_review()
    assert scoring["copa_element_score"] == 6.67
    copa = _sec(review, "copa")
    assert copa["points"] == 6.7
    assert copa["max_points"] == 10.0
    assert "Matched 2 of 3" in copa["note"]


def test_an_element_the_key_lacks_is_shown_as_extra_and_unpenalised():
    _, review = _em_review()
    row = _row(_sec(review, "copa"), "Undiagnosed new problem (Moderate)")
    assert row["status"] == "extra"
    assert "Not penalised" in row["note"]


def test_a_missed_element_is_shown_as_missed():
    _, review = _em_review()
    row = _row(_sec(review, "copa"), "Acute, uncomplicated illness/injury (Low)")
    assert (row["key"], row["coded"], row["status"]) == ("Yes", "", "missed")


def test_a_count_off_by_one_is_why_data_review_scored_zero():
    scoring, review = _em_review()
    assert scoring["dr_element_score"] == 0.0
    row = _row(_sec(review, "dr"), "Test results reviewed (count)")
    assert (row["key"], row["coded"], row["status"]) == ("2", "3", "different")


def test_each_mdm_table_reports_key_level_against_derived_level():
    _, review = _em_review()
    lvl = _row(_sec(review, "copa"), "Level")
    assert (lvl["key"], lvl["coded"], lvl["status"]) == ("Moderate", "Moderate", "correct")


def test_em_is_classified_into_the_sections_a_trainer_reads():
    _, review = _em_review()
    keys = [s["key"] for s in review["sections"]]
    assert keys == ["em_level", "dx", "copa", "dr", "risk"]
    groups = {s["key"]: s["group"] for s in review["sections"]}
    assert groups["em_level"] == "Coding" and groups["copa"] == "Reasoning"


def test_primary_coded_second_earns_no_primary_credit_and_says_why():
    """Key E11.9, I10, J45.909; coder I10, E11.9. Primary must be listed first."""
    _, review = _em_review()
    dx = _sec(review, "dx")
    # primary 0 of 17.5 + secondaries 1 of 2 (I10) = 8.75
    assert (dx["points"], dx["max_points"]) == (8.8, 35.0)
    rows = [(r["item"], r["key"], r["coded"], r["status"]) for r in dx["rows"]]
    assert rows == [("Primary Dx", "E11.9", "I10", "wrong"),
                    ("Secondary Dx", "I10", "I10", "correct"),
                    ("Secondary Dx", "J45.909", "", "missed")]
    assert "position 2" in dx["rows"][0]["note"]
    assert dx["note"].startswith("Primary 0.0 of 17.5 pts (must be listed first)")
    assert "Secondary 1 of 2 coded, 8.8 of 17.5 pts" in dx["note"]


def test_a_result_scored_under_the_old_rule_says_so():
    """Past scores were left as graded; the review must not pretend otherwise."""
    _, review = _em_review()
    r = {"specialty": "E/M", "sdx_submitted": EM["em_dx"],
         "sdx_answer_key": [{"code": c} for c in json.loads(AK["dx_codes"])],
         "cpt_submitted": [], "cpt_answer_key": [],
         "feedback": [{"section": "Coding Accuracy", "issue": "Dx: 23.3/35.0 pts",
                       "ak_code": "", "coder_code": ""}]}
    note = _sec(build_review(r, AK, EM, CFG), "dx")["note"]
    assert "earlier rule" in note and "Re-grade" in note


# ── the grader: primary diagnosis is a scoring factor ─────────────────────────

def _dx(sub, key=("E11.9", "I10", "J45.909"), w=35.0, over=True):
    from routers.practicelab_pkg.em_grading import score_em_dx
    return round(score_em_dx(list(key), list(sub), w, over)["score"], 2)


def test_all_codes_with_the_primary_first_earn_the_full_weight():
    assert _dx(["E11.9", "J45.909", "I10"]) == 35.0


def test_the_same_codes_with_the_primary_not_first_lose_the_primary_half():
    assert _dx(["I10", "E11.9", "J45.909"]) == 17.5


def test_only_the_primary_right_earns_half():
    assert _dx(["E11.9"]) == 17.5


def test_a_single_diagnosis_key_puts_the_whole_weight_on_the_primary():
    assert _dx(["E11.9"], key=("E11.9",)) == 35.0
    assert _dx(["I10"], key=("E11.9",)) == 0.0


def test_over_coding_still_costs_one_key_code_share():
    # full 35, one extra code beyond three: -35/3
    assert _dx(["E11.9", "I10", "J45.909", "R05.9"]) == round(35 - 35 / 3, 2)


def test_no_key_diagnoses_still_earns_full_credit():
    assert _dx(["I10"], key=()) == 35.0


def test_the_grader_applies_the_primary_rule_end_to_end():
    ak = dict(AK)
    first = grade_em_chart(ak, _em_submission_dict(dict(EM, em_dx=[{"code": "E11.9"}, {"code": "I10"}, {"code": "J45.909"}])), CFG)
    second = grade_em_chart(ak, _em_submission_dict(dict(EM, em_dx=[{"code": "I10"}, {"code": "E11.9"}, {"code": "J45.909"}])), CFG)
    assert round(first["dx_score"], 1) == 35.0
    assert round(second["dx_score"], 1) == 17.5


def test_time_levelled_chart_shows_a_time_section_not_mdm():
    ak = dict(AK, level_method="TIME", total_time=35)
    em = dict(EM, level_method="TIME", total_time="35")
    scoring = grade_em_chart(ak, _em_submission_dict(em), CFG)
    r = {"specialty": "E/M", "feedback": _em_feedback_items(scoring, ak, em, CFG),
         "sdx_submitted": [], "sdx_answer_key": [], "cpt_submitted": [], "cpt_answer_key": []}
    keys = [s["key"] for s in build_review(r, ak, em, CFG)["sections"]]
    assert "time" in keys and "copa" not in keys


def test_ed_profee_takes_the_em_path():
    r = {"specialty": "ED Profee", "feedback": [], "sdx_submitted": [],
         "sdx_answer_key": [], "cpt_submitted": [], "cpt_answer_key": []}
    keys = [s["key"] for s in build_review(r, AK, EM, CFG)["sections"]]
    assert keys[0] == "em_level"


# ── IP / OP: right as well as wrong ───────────────────────────────────────────

def test_ip_review_lists_correct_missed_extra_and_poa_differences():
    r = {"specialty": "IP-DRG", "pdx_submitted": "J18.9", "pdx_answer_key": "J18.9",
         "sdx_answer_key": [{"code": "I10", "poa": "Y"}, {"code": "E11.9", "poa": "Y"}],
         "sdx_submitted": [{"code": "I10", "poa": "N"}, {"code": "N17.9", "poa": "Y"}],
         "pcs_answer_key": [{"code": "0DTJ4ZZ"}], "pcs_submitted": [{"code": "0DTJ4ZZ"}],
         "cpt_answer_key": [], "cpt_submitted": [], "feedback": []}
    review = build_review(r)
    assert _sec(review, "pdx")["rows"][0]["status"] == "correct"
    statuses = {(x["key"] or x["coded"]): x["status"] for x in _sec(review, "sdx")["rows"]}
    assert statuses == {"I10  POA Y": "different", "E11.9  POA Y": "missed",
                        "N17.9  POA Y": "extra"}
    assert _sec(review, "pcs")["rows"][0]["status"] == "correct"
    assert review["summary"] == {"correct": 2, "wrong": 0, "missed": 1, "extra": 1, "different": 1}


def test_cpt_modifier_difference_is_reported_as_differs():
    r = {"specialty": "SDS", "pdx_submitted": "", "pdx_answer_key": "",
         "sdx_answer_key": [], "sdx_submitted": [], "pcs_answer_key": [], "pcs_submitted": [],
         "cpt_answer_key": [{"code": "11042", "modifier": "59"}],
         "cpt_submitted": [{"code": "11042", "modifier": ""}], "feedback": []}
    row = _sec(build_review(r), "cpt")["rows"][0]
    assert row["status"] == "different" and "Modifier" in row["note"]


# ── through the real routes ───────────────────────────────────────────────────

def test_review_endpoint_carries_the_review_for_a_standard_chart(client, db):
    chart = make_chart(db, specialty=Specialty.IP_DRG.value, chart_number="RVW-IP-1")
    _add_answer_key(db, chart, Specialty.IP_DRG)
    session = _coder_session(client, Specialty.IP_DRG, chart.id)
    entry = _entry(chart.id, Specialty.IP_DRG)
    client.post(f"/practicelab/practice-sessions/{session['session_id']}/submit",
                json={"entries": [entry]})
    body = client.get(f"/practicelab/practice-sessions/{session['session_id']}/review").json()
    review = body["charts"][0]["review"]
    assert review["summary"]["missed"] == 0
    assert review["summary"]["correct"] >= 3          # PDx, SDx, PCS all right


def _em_chart_with_key(db, number):
    chart = make_chart(db, specialty=Specialty.EM.value, chart_number=number)
    db.execute(text("""
        INSERT INTO em_answer_keys
          (chart_id, em_code, em_modifier, dx_codes, procedure_cpts, level_method,
           patient_type, copa_level, dr_level, risk_level,
           copa_stable_chronic, copa_chronic_exacerbation, copa_acute_uncomplicated,
           risk_prescription_drug_mgmt, entered_by)
        VALUES (:c, '99214', '', :dx, '[]', 'MDM', 'ESTABLISHED',
                'Moderate', 'Minimal', 'Moderate', 1, 1, 1, TRUE, 't')"""),
        {"c": chart.id, "dx": json.dumps(["E11.9", "I10"])})
    db.commit()
    return chart


def test_em_review_through_the_routes_explains_the_copa_points(client, db):
    chart = _em_chart_with_key(db, "RVW-EM-1")
    session = _coder_session(client, Specialty.EM, chart.id)
    em = dict(EM, em_dx=[{"code": "E11.9"}, {"code": "I10"}], dr_review_test_results=0)
    entry = {"chart_id": chart.id, "em_data": em, "flagged": False, "coder_notes": ""}
    sub = client.post(f"/practicelab/practice-sessions/{session['session_id']}/submit",
                      json={"entries": [entry]})
    assert sub.status_code == 200, sub.text
    charts = client.get(f"/practicelab/practice-sessions/{session['session_id']}/review").json()["charts"]
    copa = _sec(charts[0]["review"], "copa")
    assert copa["points"] == 6.7 and "Matched 2 of 3" in copa["note"]
    # E11.9 listed first: primary earned
    assert _sec(charts[0]["review"], "dx")["rows"][0]["status"] == "correct"
    # The coder's own result screen gets the same review, not a lesser one.
    assert sub.json()["results"][0]["review"] == charts[0]["review"]


# ── the export ────────────────────────────────────────────────────────────────

def test_trainer_export_is_a_two_sheet_workbook_with_every_line(client, db):
    chart = _em_chart_with_key(db, "RVW-EM-2")
    session = _coder_session(client, Specialty.EM, chart.id)
    entry = {"chart_id": chart.id, "em_data": EM, "flagged": False, "coder_notes": ""}
    client.post(f"/practicelab/practice-sessions/{session['session_id']}/submit",
                json={"entries": [entry]})
    res = client.get(f"/practicelab/practice-sessions/{session['session_id']}/review/export")
    assert res.status_code == 200, res.text
    assert "spreadsheetml" in res.headers["content-type"]
    wb = load_workbook(io.BytesIO(res.content))
    assert wb.sheetnames == ["Summary", "Review"]
    review = [[c.value for c in row] for row in wb["Review"].iter_rows(min_row=2)]
    sections = {r[2] for r in review}
    assert {"E/M Level", "Diagnoses", "Problems Addressed (COPA)",
            "Data Reviewed and Analysed", "Risk of Patient Management"} <= sections
    assert any(r[9] == "Correct" for r in review) and any(r[9] == "Missed" for r in review)


def test_coder_export_needs_results_released(client, db):
    chart = make_chart(db, specialty=Specialty.SDS.value, chart_number="RVW-SDS-1")
    _add_answer_key(db, chart, Specialty.SDS)
    session = _coder_session(client, Specialty.SDS, chart.id, show_results=False)
    url = f"/practicelab/practice-sessions/by-token/{session['token']}/review/export"
    assert client.get(url).status_code == 400            # not submitted yet
    client.post(f"/practicelab/practice-sessions/{session['session_id']}/submit",
                json={"entries": [_entry(chart.id, Specialty.SDS)]})
    assert client.get(url).status_code == 403            # submitted, not released


def test_coder_export_works_once_released(client, db):
    chart = make_chart(db, specialty=Specialty.SDS.value, chart_number="RVW-SDS-2")
    _add_answer_key(db, chart, Specialty.SDS)
    session = _coder_session(client, Specialty.SDS, chart.id, show_results=True)
    client.post(f"/practicelab/practice-sessions/{session['session_id']}/submit",
                json={"entries": [_entry(chart.id, Specialty.SDS)]})
    res = client.get(f"/practicelab/practice-sessions/by-token/{session['token']}/review/export")
    assert res.status_code == 200
    assert load_workbook(io.BytesIO(res.content)).sheetnames == ["Summary", "Review"]


def test_trainer_export_refuses_an_unsubmitted_session(client, db):
    chart = make_chart(db, specialty=Specialty.SDS.value, chart_number="RVW-SDS-3")
    _add_answer_key(db, chart, Specialty.SDS)
    session = _coder_session(client, Specialty.SDS, chart.id)
    res = client.get(f"/practicelab/practice-sessions/{session['session_id']}/review/export")
    assert res.status_code == 400


def test_a_builder_fault_never_takes_down_the_results(client, db, monkeypatch):
    """The review is additive; the results beside it worked before it existed."""
    import services.practice_review as pr

    def boom(*a, **k):
        raise RuntimeError("legacy row")
    monkeypatch.setattr(pr, "build_review", boom)
    chart = make_chart(db, specialty=Specialty.SDS.value, chart_number="RVW-SDS-4")
    _add_answer_key(db, chart, Specialty.SDS)
    session = _coder_session(client, Specialty.SDS, chart.id)
    client.post(f"/practicelab/practice-sessions/{session['session_id']}/submit",
                json={"entries": [_entry(chart.id, Specialty.SDS)]})
    res = client.get(f"/practicelab/practice-sessions/{session['session_id']}/review")
    assert res.status_code == 200
    c = res.json()["charts"][0]
    assert c["review"] is None and c["total_score"] == 100


def test_a_dotless_diagnosis_scores_like_the_dotted_one():
    """The coder's Dx box says 'dot optional'; the grader must agree."""
    assert _dx(["E119", "I10", "J45909"]) == 35.0
    ak = dict(AK)
    sub = _em_submission_dict(dict(EM, em_dx=[{"code": "E119"}, {"code": "I10"}, {"code": "J45909"}]))
    assert round(grade_em_chart(ak, sub, CFG)["dx_score"], 1) == 35.0


# ── descriptions ──────────────────────────────────────────────────────────────

def _describe(db, system, code, text_):
    from models.codes import CodeDescription
    db.add(CodeDescription(code_system=system, code=code, description=text_))
    db.commit()


def test_review_rows_carry_what_each_code_means(client, db):
    _describe(db, "ICD10CM", "J189", "Pneumonia, unspecified organism")
    _describe(db, "ICD10CM", "I10", "Essential (primary) hypertension")
    chart = make_chart(db, specialty=Specialty.IP_DRG.value, chart_number="RVW-DESC-1")
    _add_answer_key(db, chart, Specialty.IP_DRG)
    session = _coder_session(client, Specialty.IP_DRG, chart.id)
    client.post(f"/practicelab/practice-sessions/{session['session_id']}/submit",
                json={"entries": [_entry(chart.id, Specialty.IP_DRG)]})
    charts = client.get(f"/practicelab/practice-sessions/{session['session_id']}/review").json()["charts"]
    pdx = _sec(charts[0]["review"], "pdx")["rows"][0]
    assert pdx["key_desc"] == pdx["coded_desc"] == "Pneumonia, unspecified organism"
    sdx = _sec(charts[0]["review"], "sdx")["rows"][0]
    assert sdx["key_desc"] == "Essential (primary) hypertension"
    # An unknown code is silent, never an error.
    pcs = _sec(charts[0]["review"], "pcs")["rows"][0]
    assert pcs["key_desc"] == ""

    wb = load_workbook(io.BytesIO(client.get(
        f"/practicelab/practice-sessions/{session['session_id']}/review/export").content))
    header = [c.value for c in wb["Review"][1]]
    assert header[6] == "Key description" and header[8] == "Coded description"
    assert any(r[6] == "Pneumonia, unspecified organism"
               for r in wb["Review"].iter_rows(min_row=2, values_only=True))


def test_em_level_and_mdm_rows_are_never_described():
    """E/M codes are CPT (AMA) and MDM rows are not codes."""
    _, review = _em_review()
    assert all("key_desc" not in r for s in review["sections"]
               if s["key"] in ("em_level", "copa", "dr", "risk") for r in s["rows"])



# ── near misses: wrong code, not missed (Z77.9 entered for Z77.8) ────────────

def _ipr(sdx_k, sdx_c, pcs_k=(), pcs_c=()):
    return {"specialty": "IP-DRG", "pdx_submitted": "J18.9", "pdx_answer_key": "J18.9",
            "sdx_answer_key": [{"code": c, "poa": "Y"} for c in sdx_k],
            "sdx_submitted": [{"code": c, "poa": "Y"} for c in sdx_c],
            "pcs_answer_key": [{"code": c} for c in pcs_k], "pcs_submitted": [{"code": c} for c in pcs_c],
            "cpt_answer_key": [], "cpt_submitted": [], "feedback": []}


def test_review_shows_a_same_category_code_as_wrong_code_not_missed():
    rows = _sec(build_review(_ipr(["Z77.8"], ["Z77.9"])), "sdx")["rows"]
    assert [(r["key"], r["coded"], r["status"]) for r in rows] == [("Z77.8  POA Y", "Z77.9  POA Y", "wrong")]
    assert "Same category Z77" in rows[0]["note"]


def test_a_different_family_stays_missed_and_extra():
    rows = _sec(build_review(_ipr(["Z77.8"], ["N39.0"])), "sdx")["rows"]
    assert [r["status"] for r in rows] == ["missed", "extra"]


def test_pcs_near_miss_names_the_character_that_differs():
    rows = _sec(build_review(_ipr([], [], ["0DTJ4ZZ"], ["0DTJ0ZZ"])), "pcs")["rows"]
    assert rows[0]["status"] == "wrong" and "character 5 (approach)" in rows[0]["note"]


def test_grader_feedback_reports_wrong_code_with_the_coders_code():
    from services.grading_engine import IPAnswerKey, IPSubmission, grade_ip
    ak = IPAnswerKey(pdx_code="J18.9", pdx_poa="Y", sdx=[{"code": "Z77.8", "poa": "Y"}])
    sub = IPSubmission(pdx_code="J18.9", pdx_poa="Y", sdx=[{"code": "Z77.9", "poa": "Y"}])
    fb = [(f.section, f.issue_type, f.ak_code, f.coder_code) for f in grade_ip(ak, sub).feedback]
    assert ("SDx", "Wrong_Code", "Z77.8", "Z77.9") in fb
    assert not any(f[1] == "Missed" for f in fb)


def test_reclassifying_never_changes_the_score():
    from services.grading_engine import IPAnswerKey, IPSubmission, grade_ip
    ak = IPAnswerKey(pdx_code="J18.9", pdx_poa="Y", sdx=[{"code": "Z77.8", "poa": "Y"}, {"code": "I10", "poa": "Y"}])
    near = grade_ip(ak, IPSubmission(pdx_code="J18.9", pdx_poa="Y",
                                     sdx=[{"code": "Z77.9", "poa": "Y"}, {"code": "I10", "poa": "Y"}]))
    far = grade_ip(ak, IPSubmission(pdx_code="J18.9", pdx_poa="Y",
                                    sdx=[{"code": "N39.0", "poa": "Y"}, {"code": "I10", "poa": "Y"}]))
    assert (near.pdx_score, near.sdx_score, near.pcs_score) == (far.pdx_score, far.sdx_score, far.pcs_score)


def test_cpt_same_family_is_wrong_code_and_a_new_family_is_missed():
    from services.grading_engine import _match_cpt
    _, _, fb = _match_cpt([{"code": "99214"}, {"code": "36415"}], [{"code": "99213"}, {"code": "71046"}], True)
    kinds = sorted((f.issue_type, f.ak_code, f.coder_code) for f in fb)
    assert ("Wrong_Code", "99214", "99213") in kinds and ("Missed", "36415", "") in kinds


def test_pcs_grader_and_op_sdx_pair_too():
    from services.grading_engine import _match_pcs, _match_sdx_op
    _, _, fb = _match_pcs([{"code": "0DTJ4ZZ"}], [{"code": "0DTJ0ZZ"}], True)
    assert fb[0].issue_type == "Wrong_Code" and "approach" in fb[0].detail
    _, _, fb = _match_sdx_op([{"code": "E11.22"}], [{"code": "E11.9"}], True)
    assert (fb[0].issue_type, fb[0].coder_code) == ("Wrong_Code", "E11.9")


# ── E/M results stored without code lists (submitted before they were kept) ──

def _blank_lists(db, session_id):
    db.execute(text("UPDATE practice_results SET sdx_answer_key='[]', sdx_submitted='[]', "
                    "cpt_answer_key='[]', cpt_submitted='[]' WHERE session_id=:s"), {"s": session_id})
    db.commit()


def test_em_review_reads_the_diagnoses_when_the_stored_lists_are_empty(client, db):
    """Live case: EM007 showed 'Dx 23.3 of 35' over an empty section."""
    chart = _em_chart_with_key(db, "RVW-EM-OLD")
    session = _coder_session(client, Specialty.EM, chart.id)
    em = dict(EM, em_dx=[{"code": "E11.9"}])        # coded 1 of the key's 2
    client.post(f"/practicelab/practice-sessions/{session['session_id']}/submit",
                json={"entries": [{"chart_id": chart.id, "em_data": em, "flagged": False, "coder_notes": ""}]})
    _blank_lists(db, session["session_id"])
    dx = _sec(client.get(f"/practicelab/practice-sessions/{session['session_id']}/review").json()["charts"][0]["review"], "dx")
    rows = [(r["item"], r["key"], r["coded"], r["status"]) for r in dx["rows"]]
    assert ("Primary Dx", "E11.9", "E11.9", "correct") in rows
    assert ("Secondary Dx", "I10", "", "missed") in rows
    assert "full credit" not in (dx["note"] or "")


def test_regrade_stores_the_em_code_lists(client, db):
    chart = _em_chart_with_key(db, "RVW-EM-RG")
    session = _coder_session(client, Specialty.EM, chart.id)
    client.post(f"/practicelab/practice-sessions/{session['session_id']}/submit",
                json={"entries": [{"chart_id": chart.id, "em_data": EM, "flagged": False, "coder_notes": ""}]})
    _blank_lists(db, session["session_id"])
    res = client.post(f"/practicelab/practice-sessions/{session['session_id']}/regrade", json={})
    assert res.status_code == 200, res.text
    row = db.execute(text("SELECT sdx_answer_key FROM practice_results WHERE session_id=:s"),
                     {"s": session["session_id"]}).scalar()
    assert json.loads(row) == [{"code": "E11.9"}, {"code": "I10"}]


def test_a_partial_dx_score_never_claims_full_credit():
    r = {"specialty": "E/M", "sdx_submitted": [], "sdx_answer_key": [], "cpt_submitted": [], "cpt_answer_key": [],
         "feedback": [{"section": "Coding Accuracy", "issue": "Dx: 23.3/35.0 pts", "ak_code": "", "coder_code": ""}]}
    note = _sec(build_review(r, {"em_code": "99214"}, {}, CFG), "dx")["note"]
    assert "full credit" not in note


# ── CR-011-Nov: the review carries what only the Scoring notes used to ────────
# The notes block is gone from every screen, so each fact it alone held is
# asserted here on the review row that now holds it.

def _ip(**kw):
    r = {"specialty": "IP-DRG", "pdx_answer_key": "J18.9", "pdx_submitted": "J18.9",
         "sdx_answer_key": [], "sdx_submitted": [], "pcs_answer_key": [], "pcs_submitted": [],
         "cpt_answer_key": [], "cpt_submitted": [], "feedback": []}
    r.update(kw)
    return build_review(r)


def test_a_principal_diagnosis_with_the_wrong_poa_does_not_read_correct():
    rv = _ip(feedback=[{"section": "PDx", "issue_type": "Wrong_POA", "ak_code": "J18.9",
                        "coder_code": "J18.9", "detail": "POA: Y vs N"}])
    row = _sec(rv, "pdx")["rows"][0]
    assert row["status"] == "different"
    assert row["note"] == "POA: key Y, coded N"


def test_a_key_line_carries_its_cc_or_mcc_weight():
    rv = _ip(sdx_answer_key=[{"code": "I50.21", "poa": "Y", "ccmcc": "MCC"}, {"code": "I10", "poa": "Y"}],
             sdx_submitted=[{"code": "I10", "poa": "Y"}])
    rows = {r["key"].split("  ")[0]: r for r in _sec(rv, "sdx")["rows"]}
    assert rows["I50.21"]["weight"] == "MCC" and rows["I50.21"]["status"] == "missed"
    assert "weight" not in rows["I10"]


def test_a_cpt_line_with_the_wrong_pointers_does_not_read_correct():
    rv = _ip(specialty="OP", pdx_answer_key="", pdx_submitted="",
             cpt_answer_key=[{"code": "71046", "pointers": [1]}],
             cpt_submitted=[{"code": "71046", "pointers": [2]}])
    row = _sec(rv, "cpt")["rows"][0]
    assert row["status"] == "different" and "Dx pointers: key 1, coded 2" in row["note"]


def test_a_wrong_ed_level_appears_in_the_review():
    rv = _ip(specialty="ED Single Path", feedback=[
        {"section": "CPT", "issue_type": "Wrong_Code", "ak_code": "99285",
         "coder_code": "99284", "detail": "Facility ED level"}])
    sec = rv["sections"][0]
    assert sec["key"] == "ed_level"
    assert sec["rows"][0]["key"] == "99285" and sec["rows"][0]["status"] == "wrong"
