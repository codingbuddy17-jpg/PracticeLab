"""
CR-012-Nov: every code-graded specialty, end to end, with the payload the
coding screen ACTUALLY sends.

The per-specialty submit tests elsewhere post entries without an E/M form. The
real screen sent a blank one with every chart, and the result writer read that
as "this is E/M": every IP, OP and ED Single Path result stored EMPTY SDx and
CPT lists, the review lost both sections, and the auditor's observed plantings
invented misses for codes the coder had coded. 2,867 tests stayed green.
"""
import pytest
from sqlalchemy import text

from conftest import make_chart
from models import Specialty
from services.audit_observations import load_observations
from test_practice_submission_phase3a import (
    STANDARD_SPECIALTIES, _add_answer_key, _coder_session, _entry,
)
from models import AnswerKey

# What PracticeSession.tsx sent with every chart before CR-012-Nov.
BLANK_EM_FORM = {"copa_self_limited": 0, "dr_order_tests": 0, "risk_low": False,
                 "em_code": "", "em_modifier": "", "patient_type": "NA",
                 "em_category": "", "em_dx": [], "em_cpt": []}


def _submit(client, db, spec, tag, **entry_kw):
    chart = make_chart(db, specialty=spec.value, chart_number=f"SF{tag}{spec.name[:6]}")
    _add_answer_key(db, chart, spec)
    sess = _coder_session(client, spec, chart.id)
    # The coder misses the key's SDx (a CC on IP) and adds one of their own.
    e = _entry(chart.id, spec, sdx=[{"code": "R05.9", "poa": "Y"}], **entry_kw)
    e["em_data"] = BLANK_EM_FORM
    r = client.post(f"/practicelab/practice-sessions/{sess['session_id']}/submit",
                    json={"entries": [e]})
    assert r.status_code == 200, r.text
    return chart, sess


def _review(client, sess):
    c = client.get(f"/practicelab/practice-sessions/{sess['session_id']}/review").json()["charts"][0]
    return {s["key"]: s["rows"] for s in c["review"]["sections"]}


@pytest.mark.parametrize("spec", STANDARD_SPECIALTIES, ids=lambda s: s.value)
def test_the_screen_payload_stores_both_code_lists(client, db, spec):
    _, sess = _submit(client, db, spec, "S")
    row = db.execute(text("SELECT sdx_answer_key, sdx_submitted, cpt_answer_key, cpt_submitted "
                          "FROM practice_results WHERE session_id=:s"),
                     {"s": sess["session_id"]}).fetchone()
    assert "I10" in row[0] and "R05.9" in row[1]
    if spec not in (Specialty.IP_DRG, Specialty.ANCILLARY):
        assert "11042" in row[2] and "11042" in row[3]


@pytest.mark.parametrize("spec", STANDARD_SPECIALTIES, ids=lambda s: s.value)
def test_the_review_shows_the_missed_and_extra_diagnosis(client, db, spec):
    _, sess = _submit(client, db, spec, "R")
    rows = {(r["key"].split("  ")[0], r["coded"].split("  ")[0]): r for r in _review(client, sess)["sdx"]}
    assert rows[("I10", "")]["status"] == "missed"
    assert rows[("", "R05.9")]["status"] == "extra"
    if spec == Specialty.IP_DRG:
        assert rows[("I10", "")]["weight"] == "CC"


def _blank_stored_lists(db, sess):
    """A result as stored between late August and CR-012-Nov."""
    db.execute(text("UPDATE practice_results SET sdx_answer_key='[]', sdx_submitted='[]', "
                    "cpt_answer_key='[]', cpt_submitted='[]' WHERE session_id=:s"),
               {"s": sess["session_id"]})
    db.commit()


@pytest.mark.parametrize("spec", [Specialty.IP_DRG, Specialty.SDS], ids=lambda s: s.value)
def test_a_result_stored_empty_is_repaired_on_read(client, db, spec):
    _, sess = _submit(client, db, spec, "P")
    _blank_stored_lists(db, sess)
    secs = _review(client, sess)
    assert {r["status"] for r in secs["sdx"]} == {"missed", "extra"}
    if spec == Specialty.SDS:
        assert secs["cpt"][0]["status"] == "correct"


def test_observed_plantings_do_not_invent_misses_from_an_empty_stored_list(client, db):
    chart, sess = _submit(client, db, Specialty.SDS, "O")
    _blank_stored_lists(db, sess)
    key = db.query(AnswerKey).filter_by(chart_id=chart.id).first()
    obs = {(o.section, o.action, o.code) for o in load_observations(db, chart.id, key)}
    # The coder coded 11042: no planting may claim they missed it.
    assert ("CPT", "Add", "11042") not in obs
    assert ("SDx", "Add", "I10") in obs and ("SDx", "Delete", "R05.9") in obs


def test_the_principal_diagnosis_poa_is_shown_and_judged(client, db):
    _, sess = _submit(client, db, Specialty.IP_DRG, "Q", pdx_poa="N")
    pdx = _review(client, sess)["pdx"][0]
    assert pdx["key"] == "J18.9  POA Y" and pdx["coded"] == "J18.9  POA N"
    assert pdx["status"] == "different" and pdx["note"] == "POA: key Y, coded N"


def test_a_poa_exempt_code_says_so_and_is_never_marked_wrong():
    from services.practice_review import build_review
    rv = build_review({"specialty": "IP-DRG", "pdx_answer_key": "Z38.00", "pdx_submitted": "Z38.00",
                       "pdx_poa_answer_key": "E", "pdx_poa_submitted": "",
                       "sdx_answer_key": [{"code": "Z37.0", "poa": "E"}],
                       "sdx_submitted": [{"code": "Z37.0", "poa": "Y"}], "feedback": []})
    secs = {s["key"]: s["rows"] for s in rv["sections"]}
    for row in (secs["pdx"][0], secs["sdx"][0]):
        assert row["status"] == "correct"
        assert "POA exempt" in row["note"]
