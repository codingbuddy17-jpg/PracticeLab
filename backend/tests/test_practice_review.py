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
    assert keys == ["em_level", "pdx", "sdx", "copa", "dr", "risk"]
    groups = {s["key"]: s["group"] for s in review["sections"]}
    assert groups["em_level"] == "Coding" and groups["copa"] == "Reasoning"


def test_dx_order_is_noted_but_never_marked_wrong():
    """E/M scores diagnoses as a set. The primary row must not contradict that."""
    _, review = _em_review()
    pdx = _row(_sec(review, "pdx"), "Primary Dx")
    assert pdx["status"] == "order"
    sdx = _sec(review, "sdx")
    assert [(r["key"], r["status"]) for r in sdx["rows"]] == [
        ("I10", "correct"), ("J45.909", "missed")]


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
    assert review["summary"] == {"correct": 2, "missed": 1, "extra": 1, "different": 1}


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
                'Moderate', 'Minimal', 'Moderate', 1, 1, 1, 1, 't')"""),
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
    assert {"E/M Level", "Primary Diagnosis", "Problems Addressed (COPA)",
            "Data Reviewed and Analysed", "Risk of Patient Management"} <= sections
    assert any(r[7] == "Correct" for r in review) and any(r[7] == "Missed" for r in review)


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
