"""
Phase 2 manual answer-key entry regression.

Upload and hand-entry use different endpoints and payload shapes. These tests
prove that keys created through the trainer UI path survive read/edit/delete
and can still drive coder grading plus auditor allocation/mutation.
"""
import pytest
from sqlalchemy import text

from conftest import make_chart
from models import AnswerKey, AuditBatch, BatchStatus, Specialty
from routers.auditor_pkg.shared import audit_key_for, chart_pool
from routers.practicelab_pkg.chart_grading import _grade_chart_for_sp
from routers.practicelab_pkg.em_grading import grade_em_chart
from routers.practicelab_pkg.shared import _is_dx_only, _is_ip, _is_single_path
from services.audit_mutation import Corpus, MUTATION_KINDS, MutationConfig, generate
from services.grading_engine import DEFAULT_EDSP_CFG, DEFAULT_IP_CFG, DEFAULT_OP_CFG

PASS = "test-passphrase"

STANDARD_SPECIALTIES = [
    Specialty.IP_DRG,
    Specialty.SDS,
    Specialty.ED_FACILITY,
    Specialty.SURGERY,
    Specialty.ED_SINGLE_PATH,
    Specialty.ANCILLARY,
]
EM_SPECIALTIES = [Specialty.EM, Specialty.ED_PROFEE]


def _standard_payload(spec: Specialty, **overrides) -> dict:
    payload = {
        "pdx_code": "J18.9" if _is_ip(spec) else "E11.9",
        "pdx_poa": "Y" if _is_ip(spec) else "",
        "sdx": [{"code": "I10", "poa": "Y", "ccmcc": "CC"}] if _is_ip(spec)
               else [{"code": "I10"}],
        "pcs": [{"code": "0DTJ4ZZ"}] if _is_ip(spec) else [],
        "cpt": [] if (_is_ip(spec) or _is_dx_only(spec)) else [
            {"code": "11042", "modifier": "59", "units": 2,
             "pointers": ["1"] if spec == Specialty.SURGERY else []}
        ],
        "facility_level": "99283" if _is_single_path(spec) else None,
        "profee_level": "99284" if _is_single_path(spec) else None,
        "entered_by": "QA",
        "passphrase": PASS,
    }
    payload.update(overrides)
    return payload


def _perfect_standard_submission(ak: AnswerKey, spec: Specialty) -> dict:
    sub = {
        "pdx_code": ak.pdx_code or "",
        "pdx_poa": ak.pdx_poa or "",
        "sdx": ak.sdx or [],
        "pcs": ak.pcs or [],
        "cpt": ak.cpt or [],
    }
    if _is_single_path(spec):
        sub["facility_level"] = ak.facility_level or ""
        sub["profee_level"] = ak.profee_level or ""
    return sub


def _only_mutation(kind: str) -> MutationConfig:
    zeros = {field: 0 for _kind, field in MUTATION_KINDS}
    zeros[dict(MUTATION_KINDS)[kind]] = 100
    return MutationConfig(**zeros)


def _em_payload(chart_id: int, spec: Specialty, **overrides) -> dict:
    payload = {
        "chart_id": chart_id,
        "copa_self_limited": 0,
        "copa_stable_acute": 0,
        "copa_stable_chronic": 2,
        "copa_acute_uncomplicated": 0,
        "copa_chronic_exacerbation": 0,
        "copa_undiagnosed_new": 0,
        "copa_acute_systemic": 0,
        "copa_acute_complicated_injury": 0,
        "copa_chronic_severe": 0,
        "copa_threat_to_life": 0,
        "copa_level_overridden": False,
        "copa_level_override": "",
        "dr_prior_external_notes": 1,
        "dr_review_test_results": 1,
        "dr_order_tests": 1,
        "dr_independent_historian": False,
        "dr_independent_interpretation": False,
        "dr_external_discussion": False,
        "dr_level_overridden": False,
        "dr_level_override": "",
        "risk_low": False,
        "risk_prescription_drug_mgmt": True,
        "risk_minor_surgery_with_factors": False,
        "risk_elective_major_no_factors": False,
        "risk_hospitalization": False,
        "risk_sdoh": False,
        "risk_drug_intensive_monitoring": False,
        "risk_elective_major_with_factors": False,
        "risk_emergency_major_surgery": False,
        "risk_hospitalization_escalation": False,
        "risk_dnr_deescalate": False,
        "risk_parenteral_controlled": False,
        "risk_level_overridden": False,
        "risk_level_override": "",
        "em_code": "99214" if spec == Specialty.EM else "99284",
        "em_modifier": "",
        "patient_type": "ESTABLISHED" if spec == Specialty.EM else "NA",
        "level_method": "MDM",
        "total_time": None,
        "em_category": "office" if spec == Specialty.EM else "emergency",
        "critical_care_minutes": None,
        "dx_codes": ["E11.9", "I10"],
        "procedure_cpts": [{"code": "20610", "modifier": "RT",
                            "pointers": ["1"], "units": 1}],
        "entered_by": "QA",
    }
    payload.update(overrides)
    return payload


def _em_cfg() -> dict:
    return {
        "line1_weight": 70,
        "line2_weight": 30,
        "em_level_weight": 23.33,
        "cpt_weight": 23.33,
        "dx_weight": 23.34,
        "copa_weight": 10.0,
        "dr_weight": 10.0,
        "risk_weight": 10.0,
        "pass_threshold": 80,
        "overcoding_penalty": True,
    }


@pytest.mark.parametrize("spec", STANDARD_SPECIALTIES, ids=lambda s: s.value)
def test_manual_standard_key_save_grades_and_allocates(client, db, spec):
    chart = make_chart(db, specialty=spec.value, chart_number=f"MAN{spec.name[:5]}")
    db.commit()

    r = client.put(f"/practicelab/answer-key/{chart.id}",
                   json=_standard_payload(spec))
    assert r.status_code == 200, r.text
    assert r.json()["saved"] is True
    assert r.json()["created"] is True

    detail = client.get(f"/practicelab/answer-key/{chart.id}/detail").json()
    assert detail["exists"] is True
    assert detail["pdx_code"] == _standard_payload(spec)["pdx_code"]

    ak = db.query(AnswerKey).filter(AnswerKey.chart_id == chart.id).one()
    result, feedback = _grade_chart_for_sp(
        chart, ak, _perfect_standard_submission(ak, spec),
        DEFAULT_IP_CFG, DEFAULT_OP_CFG, DEFAULT_EDSP_CFG,
    )
    assert result["weighted_score"] == 100
    assert result["pass_fail"] == "PASS"
    assert feedback == []

    batch = AuditBatch(name="Manual QA", specialty=spec, charts_per_auditor=1,
                       created_by="QA", status=BatchStatus.OPEN)
    db.add(batch)
    db.commit()
    assert [c.id for c in chart_pool(db, batch)] == [chart.id]

    claim, planted = generate(
        audit_key_for(db, chart), spec, seed=9, cfg=_only_mutation("spurious"),
        budget=1, corpus=Corpus(dx_codes=["J18.9", "E11.9", "I10", "Z99.89"]),
    )
    assert claim["pdx_code"]
    assert planted


def test_manual_standard_key_edit_is_passphrase_gated_and_replaces(client, db):
    chart = make_chart(db, specialty="SDS", chart_number="MANEDIT")
    db.commit()
    first = client.put(f"/practicelab/answer-key/{chart.id}",
                       json=_standard_payload(Specialty.SDS, pdx_code="E11.9"))
    assert first.status_code == 200, first.text

    blocked = client.put(f"/practicelab/answer-key/{chart.id}",
                         json=_standard_payload(Specialty.SDS, pdx_code="J18.9",
                                                passphrase="wrong"))
    assert blocked.status_code == 403
    assert db.query(AnswerKey).filter_by(chart_id=chart.id).one().pdx_code == "E11.9"

    updated = client.put(f"/practicelab/answer-key/{chart.id}",
                         json=_standard_payload(Specialty.SDS, pdx_code="J18.9"))
    assert updated.status_code == 200, updated.text
    assert updated.json()["created"] is False
    assert db.query(AnswerKey).filter_by(chart_id=chart.id).count() == 1
    assert db.query(AnswerKey).filter_by(chart_id=chart.id).one().pdx_code == "J18.9"


def test_manual_standard_key_delete_is_passphrase_gated(client, db):
    chart = make_chart(db, specialty="SDS", chart_number="MANDEL")
    db.commit()
    client.put(f"/practicelab/answer-key/{chart.id}",
               json=_standard_payload(Specialty.SDS))

    blocked = client.delete(f"/practicelab/answer-key/{chart.id}",
                            params={"passphrase": "wrong"})
    assert blocked.status_code == 403
    assert db.query(AnswerKey).filter_by(chart_id=chart.id).count() == 1

    deleted = client.delete(f"/practicelab/answer-key/{chart.id}",
                            params={"passphrase": PASS})
    assert deleted.status_code == 200, deleted.text
    assert db.query(AnswerKey).filter_by(chart_id=chart.id).count() == 0


def test_manual_standard_key_requires_entered_by(client, db):
    chart = make_chart(db, specialty="SDS", chart_number="MANWHO")
    db.commit()

    r = client.put(f"/practicelab/answer-key/{chart.id}",
                   json=_standard_payload(Specialty.SDS, entered_by=" "))

    assert r.status_code == 400
    assert "entered_by" in r.json()["detail"]


@pytest.mark.parametrize("spec", EM_SPECIALTIES, ids=lambda s: s.value)
def test_manual_em_key_save_grades_and_allocates(client, db, spec):
    chart = make_chart(db, specialty=spec.value, chart_number=f"MAN{spec.name}")
    db.commit()

    r = client.post("/practicelab/em/answer-key", json=_em_payload(chart.id, spec))
    assert r.status_code == 200, r.text
    assert r.json()["status"] == "ok"

    stored = client.get(f"/practicelab/em/answer-key/{chart.id}")
    assert stored.status_code == 200, stored.text
    ak = stored.json()
    assert ak["em_code"] == _em_payload(chart.id, spec)["em_code"]

    sub = {
        "sub_em_code": ak["em_code"],
        "sub_em_modifier": ak["em_modifier"] or "",
        "sub_patient_type": ak["patient_type"],
        "sub_level_method": ak["level_method"],
        "sub_dx_codes": ak["dx_codes"],
        "sub_procedure_cpts": ak["procedure_cpts"],
        "sub_copa_stable_chronic": 2,
        "sub_dr_prior_external_notes": 1,
        "sub_dr_review_test_results": 1,
        "sub_dr_order_tests": 1,
        "sub_dr_independent_interpretation": False,
        "sub_risk_prescription_drug_mgmt": True,
    }
    scoring = grade_em_chart(ak, sub, _em_cfg())
    assert round(scoring["total_score"], 1) == 100.0

    batch = AuditBatch(name="Manual EM QA", specialty=spec, charts_per_auditor=1,
                       created_by="QA", status=BatchStatus.OPEN)
    db.add(batch)
    db.commit()
    assert [c.id for c in chart_pool(db, batch)] == [chart.id]

    claim, planted = generate(
        audit_key_for(db, chart), spec, seed=5, cfg=_only_mutation("mdm_shift"),
        budget=1,
    )
    assert set(claim["mdm"]) == {"copa", "dr", "risk"}
    assert planted and planted[0]["section"] == "MDM"


def test_manual_em_key_edit_replaces_the_existing_row(client, db):
    chart = make_chart(db, specialty="E/M", chart_number="MANEMEDIT")
    db.commit()
    assert client.post("/practicelab/em/answer-key",
                       json=_em_payload(chart.id, Specialty.EM)).status_code == 200

    r = client.post("/practicelab/em/answer-key",
                    json=_em_payload(chart.id, Specialty.EM, em_code="99215"))
    assert r.status_code == 200, r.text

    rows = db.execute(text(
        "SELECT em_code FROM em_answer_keys WHERE chart_id=:c"),
        {"c": chart.id}).fetchall()
    assert [row[0] for row in rows] == ["99215"]


def test_manual_em_key_delete_is_passphrase_gated(client, db):
    chart = make_chart(db, specialty="E/M", chart_number="MANEMDEL")
    db.commit()
    client.post("/practicelab/em/answer-key",
                json=_em_payload(chart.id, Specialty.EM))

    blocked = client.delete(f"/practicelab/em/answer-key/{chart.id}",
                            params={"passphrase": "wrong"})
    assert blocked.status_code == 403

    deleted = client.delete(f"/practicelab/em/answer-key/{chart.id}",
                            params={"passphrase": PASS})
    assert deleted.status_code == 200, deleted.text
    assert db.execute(text(
        "SELECT COUNT(*) FROM em_answer_keys WHERE chart_id=:c"),
        {"c": chart.id}).scalar() == 0
