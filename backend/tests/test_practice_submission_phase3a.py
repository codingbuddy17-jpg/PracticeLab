"""
Phase 3A practice submission regression.

This file exercises the workflow routes, not just the grading engines:
batch -> allocation -> access token -> draft/submit -> stored results.
"""

import json

import pytest
from sqlalchemy import text

from conftest import make_chart
from models import (
    AnswerKey, AuditAssignment, AuditSession, GradingResult, Specialty,
)

PASS = "test-passphrase"

STANDARD_SPECIALTIES = [
    Specialty.IP_DRG,
    Specialty.SDS,
    Specialty.ED_FACILITY,
    Specialty.SURGERY,
    Specialty.ED_SINGLE_PATH,
    Specialty.ANCILLARY,
]


def _key_for(spec: Specialty) -> dict:
    return {
        "pdx_code": "J18.9" if spec == Specialty.IP_DRG else "E11.9",
        "pdx_poa": "Y" if spec == Specialty.IP_DRG else "",
        "sdx": (
            [{"code": "I10", "poa": "Y", "ccmcc": "CC"}]
            if spec == Specialty.IP_DRG else [{"code": "I10"}]
        ),
        "pcs": [{"code": "0DTJ4ZZ"}] if spec == Specialty.IP_DRG else [],
        "cpt": [] if spec in (Specialty.IP_DRG, Specialty.ANCILLARY) else [
            {"code": "11042", "modifier": "59", "units": 1,
             "pointers": ["1"] if spec == Specialty.SURGERY else []}
        ],
        "facility_level": "99283" if spec == Specialty.ED_SINGLE_PATH else None,
        "profee_level": "99284" if spec == Specialty.ED_SINGLE_PATH else None,
    }


def _entry(chart_id: int, spec: Specialty, **overrides) -> dict:
    key = _key_for(spec)
    entry = {
        "chart_id": chart_id,
        "pdx_code": key["pdx_code"],
        "pdx_poa": key["pdx_poa"],
        "sdx": key["sdx"],
        "pcs": key["pcs"],
        "cpt": key["cpt"],
        "facility_level": key["facility_level"],
        "profee_level": key["profee_level"],
        "flagged": False,
        "coder_notes": "",
    }
    entry.update(overrides)
    return entry


def _add_answer_key(db, chart, spec: Specialty):
    key = _key_for(spec)
    db.add(AnswerKey(
        chart_id=chart.id,
        specialty=spec,
        entered_by="QA",
        **key,
    ))
    db.commit()


def _coder_session(client, spec: Specialty, chart_id: int, show_results=True) -> dict:
    created = client.post("/practicelab/batches", json={
        "name": f"Phase 3A {spec.value}",
        "specialty": spec.value,
        "charts_per_coder": 1,
        "coders": [{"name": "Coder One", "emp_id": "EMP-1"}],
        "created_by": "QA",
        "use_weighted": True,
        "use_dpo": spec in {
            Specialty.IP_DRG, Specialty.SDS, Specialty.ED_FACILITY,
            Specialty.SURGERY, Specialty.ED_SINGLE_PATH, Specialty.ANCILLARY,
        },
    })
    assert created.status_code == 200, created.text
    batch_id = created.json()["batch_id"]

    allocated = client.post(f"/practicelab/batches/{batch_id}/run-allocation",
                            json={"manual_chart_ids": [chart_id], "run_by": "QA"})
    assert allocated.status_code == 200, allocated.text

    tokens = client.post("/practicelab/practice-sessions/generate-tokens",
                         json={"batch_id": batch_id,
                               "cycle_id": allocated.json()["cycle_id"],
                               "show_results_to_coder": show_results})
    assert tokens.status_code == 200, tokens.text
    token = tokens.json()["tokens"][0]["token"]

    opened = client.get(f"/practicelab/practice-sessions/by-token/{token}")
    assert opened.status_code == 200, opened.text
    return {**opened.json(), "batch_id": batch_id, "token": token}


@pytest.mark.parametrize("spec", STANDARD_SPECIALTIES, ids=lambda s: s.value)
def test_coder_standard_submit_writes_results_and_reporting_rows(client, db, spec):
    chart = make_chart(db, specialty=spec.value,
                       chart_number=f"P3A{spec.name[:8]}")
    _add_answer_key(db, chart, spec)

    session = _coder_session(client, spec, chart.id)
    entry = _entry(chart.id, spec)

    draft = client.post(
        f"/practicelab/practice-sessions/{session['session_id']}/save-draft",
        json={"entries": [entry]},
    )
    assert draft.status_code == 200, draft.text
    reopened = client.get(f"/practicelab/practice-sessions/by-token/{session['token']}").json()
    assert str(chart.id) in reopened["drafts"] or chart.id in reopened["drafts"]
    draft_row = reopened["drafts"].get(str(chart.id), reopened["drafts"].get(chart.id))
    assert draft_row["pdx_code"] == entry["pdx_code"]

    submitted = client.post(
        f"/practicelab/practice-sessions/{session['session_id']}/submit",
        json={"entries": [entry]},
    )
    assert submitted.status_code == 200, submitted.text
    body = submitted.json()
    assert body["submitted"] is True
    assert body["show_results"] is True
    assert body["results"][0]["total_score"] == 100
    assert body["results"][0]["pass_fail"] == "PASS"

    review = client.get(
        f"/practicelab/practice-sessions/{session['session_id']}/review"
    )
    assert review.status_code == 200, review.text
    assert review.json()["charts"][0]["total_score"] == 100

    stored = db.execute(text(
        "SELECT total_score, pass_fail FROM practice_results "
        "WHERE session_id=:s AND chart_id=:c"
    ), {"s": session["session_id"], "c": chart.id}).fetchone()
    assert tuple(stored) == (100, "PASS")

    mirrored = db.query(GradingResult).filter_by(
        batch_id=session["batch_id"], coder_name="Coder One", chart_id=chart.id,
    ).one()
    assert mirrored.total_score == 100
    assert mirrored.pass_fail.value == "PASS"
    assert mirrored.emp_id == "EMP-1"

    grid = client.get(
        f"/practicelab/practice-sessions/batch/{session['batch_id']}/grid"
    )
    assert grid.status_code == 200, grid.text
    assert grid.json()["grid"][0]["avg_score"] == 100


def _em_key_payload(chart_id: int, spec: Specialty) -> dict:
    return {
        "chart_id": chart_id,
        "copa_stable_chronic": 2,
        "dr_prior_external_notes": 1,
        "dr_review_test_results": 1,
        "dr_order_tests": 1,
        "risk_prescription_drug_mgmt": True,
        "em_code": "99214" if spec == Specialty.EM else "99284",
        "patient_type": "ESTABLISHED" if spec == Specialty.EM else "NA",
        "level_method": "MDM",
        "em_category": "office" if spec == Specialty.EM else "emergency",
        "dx_codes": ["E11.9", "I10"],
        "procedure_cpts": [{"code": "20610", "modifier": "RT",
                            "pointers": ["1"], "units": 1}],
        "entered_by": "QA",
    }


def _em_entry(chart_id: int, spec: Specialty) -> dict:
    return {
        "chart_id": chart_id,
        "em_data": {
            "em_code": "99214" if spec == Specialty.EM else "99284",
            "em_modifier": "",
            "patient_type": "ESTABLISHED" if spec == Specialty.EM else "NA",
            "level_method": "MDM",
            "copa_stable_chronic": 2,
            "dr_prior_external_notes": 1,
            "dr_review_test_results": 1,
            "dr_order_tests": 1,
            "risk_prescription_drug_mgmt": True,
            "em_dx": [{"code": "E11.9"}, {"code": "I10"}],
            "em_cpt": [{"code": "20610", "modifier": "RT",
                        "pointers": ["1"], "units": 1}],
        },
    }


@pytest.mark.parametrize("spec", [Specialty.EM, Specialty.ED_PROFEE],
                         ids=lambda s: s.value)
def test_coder_em_submit_uses_em_key_and_mirrors_result(client, db, spec):
    chart = make_chart(db, specialty=spec.value, chart_number=f"P3A{spec.name}")
    db.commit()
    saved = client.post("/practicelab/em/answer-key",
                        json=_em_key_payload(chart.id, spec))
    assert saved.status_code == 200, saved.text

    session = _coder_session(client, spec, chart.id)
    submitted = client.post(
        f"/practicelab/practice-sessions/{session['session_id']}/submit",
        json={"entries": [_em_entry(chart.id, spec)]},
    )
    assert submitted.status_code == 200, submitted.text
    result = submitted.json()["results"][0]
    assert result["total_score"] == 100
    assert result["pass_fail"] == "PASS"

    mirrored = db.query(GradingResult).filter_by(
        batch_id=session["batch_id"], coder_name="Coder One", chart_id=chart.id,
    ).one()
    assert mirrored.total_score == 100
    assert mirrored.specialty == spec

    stored = db.execute(text("""
        SELECT sdx_submitted, sdx_answer_key, cpt_submitted, cpt_answer_key, feedback
        FROM practice_results
        WHERE session_id=:s AND chart_id=:c
    """), {"s": session["session_id"], "c": chart.id}).mappings().one()
    assert json.loads(stored["sdx_submitted"]) == [{"code": "E11.9"}, {"code": "I10"}]
    assert json.loads(stored["sdx_answer_key"]) == [{"code": "E11.9"}, {"code": "I10"}]
    assert json.loads(stored["cpt_submitted"]) == [
        {"code": "20610", "modifier": "RT", "pointers": ["1"], "units": 1}
    ]
    assert json.loads(stored["cpt_answer_key"]) == [
        {"code": "20610", "modifier": "RT", "pointers": ["1"], "units": 1}
    ]
    cpt_feedback = [f for f in json.loads(stored["feedback"]) if f["issue"].startswith("CPT:")]
    assert cpt_feedback and cpt_feedback[0]["ak_code"] != "" and cpt_feedback[0]["coder_code"] != ""


def _audit_chart(db, n: int):
    chart = make_chart(db, specialty=Specialty.IP_DRG.value,
                       chart_number=f"P3AAUD{n}", category="Audit")
    db.add(AnswerKey(
        chart_id=chart.id, specialty=Specialty.IP_DRG,
        pdx_code="J18.9", pdx_poa="Y",
        sdx=[{"code": "I10", "poa": "Y", "ccmcc": "CC"},
             {"code": "E11.9", "poa": "Y", "ccmcc": "-"}],
        pcs=[{"code": "0DTJ4ZZ"}], cpt=[], entered_by="QA",
    ))
    db.commit()
    return chart


def _audit_batch(client, chart_ids, clean_share: int) -> dict:
    created = client.post("/auditor/batches", json={
        "name": "Phase 3A Audit",
        "specialty": "IP-DRG",
        "charts_per_auditor": len(chart_ids),
        "auditors": [{"name": "Auditor One", "emp_id": "AUD-1"}],
        "created_by": "QA",
        "allocation_mode": "guided",
        "clean_share": clean_share,
        "show_results_to_auditor": True,
    })
    assert created.status_code == 200, created.text
    batch_id = created.json()["batch_id"]
    allocated = client.post(f"/auditor/batches/{batch_id}/run-allocation",
                            json={"manual_chart_ids": chart_ids, "run_by": "QA"})
    assert allocated.status_code == 200, allocated.text
    token = allocated.json()["access_codes"][0]["token"]
    opened = client.get(f"/auditor/sessions/by-token/{token}")
    assert opened.status_code == 200, opened.text
    return {**opened.json(), "batch_id": batch_id}


def _truth(client, batch_id: int) -> dict[int, list[dict]]:
    rows = client.get(f"/auditor/batches/{batch_id}/plantings").json()["plantings"]
    return {r["chart_id"]: r["ground_truth"] for r in rows}


def _audit_work(opened: dict, truth: dict[int, list[dict]], perfect=True) -> dict:
    charts = []
    sections = [s["key"] for s in opened["form"]["sections"]]
    for chart in opened["charts"]:
        findings = []
        if perfect:
            for planting in truth.get(chart["chart_id"], []):
                finding = {"section": planting["section"],
                           "action": planting["action"]}
                if planting["action"] == "Add":
                    finding["correct_value"] = planting["correct_value"]
                    entry = planting.get("entry") or {}
                    if entry.get("poa"):
                        finding["poa"] = entry["poa"]
                    if entry.get("ccmcc"):
                        finding["ccmcc"] = entry["ccmcc"]
                elif planting["action"] == "Delete":
                    finding["line"] = planting["line"]
                    finding["claim_value"] = planting["claim_value"]
                else:
                    finding["line"] = planting["line"]
                    finding["field"] = planting.get("field", "code")
                    finding["correct_value"] = planting["correct_value"]
                findings.append(finding)
        touched = {f["section"] for f in findings}
        charts.append({
            "chart_id": chart["chart_id"],
            "section_verdicts": {
                s: "needs_changes" if s in touched else "no_changes"
                for s in sections
            },
            "findings": findings,
        })
    return {"charts": charts}


def test_auditor_opportunity_submit_writes_scores_and_review(client, db):
    chart = _audit_chart(db, 1)
    opened = _audit_batch(client, [chart.id], clean_share=0)

    submitted = client.post(
        f"/auditor/sessions/{opened['session_id']}/submit",
        json=_audit_work(opened, _truth(client, opened["batch_id"])),
    )

    assert submitted.status_code == 200, submitted.text
    summary = submitted.json()["summary"]
    assert summary["audit_score"] == 100.0
    assert summary["review_score"] == 100.0
    assert summary["pass_fail"] == "PASS"

    review = client.get(f"/auditor/sessions/{opened['session_id']}/review")
    assert review.status_code == 200, review.text
    assert review.json()["summary"]["audit_score"] == 100.0


def test_auditor_clean_submit_scores_restraint_without_findings(client, db):
    chart = _audit_chart(db, 2)
    opened = _audit_batch(client, [chart.id], clean_share=100)
    assignment = db.query(AuditAssignment).filter_by(batch_id=opened["batch_id"]).one()
    assignment.ground_truth = []
    db.commit()

    submitted = client.post(
        f"/auditor/sessions/{opened['session_id']}/submit",
        json=_audit_work(opened, {chart.id: []}, perfect=False),
    )

    assert submitted.status_code == 200, submitted.text
    summary = submitted.json()["summary"]
    assert summary["clean_charts"] == 1
    assert summary["audit_score"] == 100.0
    assert summary["over_calls"] == 0

    row = db.query(AuditSession).filter_by(id=opened["session_id"]).one()
    assert row.status == "submitted"
    db.refresh(assignment)
    assert assignment.ground_truth == []
