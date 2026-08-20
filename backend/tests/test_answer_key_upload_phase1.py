"""
Phase 1 answer-key upload regression.

These tests exercise the real upload endpoints, not just the parsers. A key
that parses but is invisible to PracticeLab or Auditor is still broken: coders
cannot be graded from it, and auditors cannot allocate from it.
"""
import io

import pytest
from openpyxl import Workbook, load_workbook

from conftest import make_chart
from models import AnswerKey, AuditBatch, BatchStatus, Specialty
from routers.auditor_pkg.shared import chart_pool
from routers.practicelab_pkg.shared import (
    _is_dx_only, _is_ip, _is_single_path, _uses_pointers, _uses_units,
)
from services.em_audit_key import EM_KEY_SPECIALTIES
from services.excel_service import (
    EM_KEY_COLUMNS, generate_answer_key_template,
)

PASS = "test-passphrase"


STANDARD_KEY_SPECIALTIES = [
    Specialty.IP_DRG,
    Specialty.SDS,
    Specialty.ED_FACILITY,
    Specialty.SURGERY,
    Specialty.ED_SINGLE_PATH,
    Specialty.ANCILLARY,
]


def _headers(data: bytes) -> list[str]:
    ws = load_workbook(io.BytesIO(data)).worksheets[0]
    return [str(c.value).split("\n")[0] if c.value else "" for c in ws[1]]


def _template(spec: Specialty) -> bytes:
    return generate_answer_key_template(
        "IP" if _is_ip(spec) else "OP",
        with_pointers=_uses_pointers(spec),
        single_path=_is_single_path(spec),
        dx_only=_is_dx_only(spec),
        with_units=_uses_units(spec),
    )


def _fill(data: bytes, values: dict) -> bytes:
    wb = load_workbook(io.BytesIO(data))
    ws = wb.worksheets[0]
    at = {str(c.value).split("\n")[0]: c.column for c in ws[1] if c.value}
    for header, value in values.items():
        assert header in at, f"{header} not in template: {sorted(at)}"
        ws.cell(2, at[header], value)
    out = io.BytesIO()
    wb.save(out)
    return out.getvalue()


def _standard_key_file(spec: Specialty, chart_number: str) -> bytes:
    values = {"Chart_Number": chart_number, "PDx_Code": "E11.9", "SDx_1": "I10"}
    if _is_ip(spec):
        values.update({
            "PDx_POA": "Y",
            "SDx_1_POA": "Y",
            "SDx_1_CCMCC": "CC",
            "PCS_1": "0DTJ4ZZ",
        })
    else:
        if _is_single_path(spec):
            values["Facility_ED_Level"] = "99283"
            values["Profee_ED_Level"] = "99284"
        if not _is_dx_only(spec):
            values["CPT_1"] = "11042"
            values["CPT_1_Modifier"] = "59"
            if _uses_units(spec):
                values["CPT_1_Units"] = 2
            if _uses_pointers(spec):
                values["CPT_1_DxPointers"] = "1,2"
    return _fill(_template(spec), values)


def _upload_standard(client, spec: Specialty, data: bytes, replace=False,
                     passphrase=PASS):
    return client.post(
        "/practicelab/answer-key/upload",
        files={"file": ("keys.xlsx", data,
                        "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")},
        data={
            "specialty": spec.value,
            "entered_by": "QA",
            "replace": str(replace).lower(),
            "passphrase": passphrase,
        },
    )


def _em_values(chart_number: str, code: str) -> tuple[list[str], list]:
    headers = [h for _field, h in EM_KEY_COLUMNS]
    at = {field: i for i, (field, _header) in enumerate(EM_KEY_COLUMNS)}
    values = [""] * len(headers)
    for field, value in {
        "chart_number": chart_number,
        "copa_stable_chronic": 2,
        "dr_review_test_results": 1,
        "dr_independent_interpretation": "Y",
        "risk_prescription_drug_mgmt": "Y",
        "em_code": code,
        "patient_type": "Established",
        "level_method": "MDM",
        "dx_1": "E11.9",
        "dx_2": "I10",
        "cpt_1": "20610",
        "cpt_1_modifier": "RT",
        "cpt_1_units": 1,
        "cpt_1_pointers": "A",
        "em_category": "office" if code.startswith("9921") else "emergency",
        "entered_by": "QA",
    }.items():
        values[at[field]] = value
    return headers, values


def _workbook(headers, *rows) -> bytes:
    wb = Workbook()
    ws = wb.active
    for c, header in enumerate(headers, 1):
        ws.cell(1, c, header)
    for r, row in enumerate(rows, 2):
        for c, value in enumerate(row, 1):
            ws.cell(r, c, value)
    out = io.BytesIO()
    wb.save(out)
    return out.getvalue()


def _em_key_file(chart_number: str, spec: Specialty) -> bytes:
    code = "99214" if spec == Specialty.EM else "99284"
    headers, values = _em_values(chart_number, code)
    return _workbook(headers, values)


def _upload_em(client, data: bytes, replace=False, passphrase=PASS):
    return client.post(
        "/practicelab/em/answer-key/upload",
        files={"file": ("em_keys.xlsx", data,
                        "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")},
        data={
            "entered_by": "QA",
            "replace": str(replace).lower(),
            "passphrase": passphrase,
        },
    )


@pytest.mark.parametrize("spec", STANDARD_KEY_SPECIALTIES, ids=lambda s: s.value)
def test_standard_specialty_upload_is_visible_to_coder_and_auditor(client, db, spec):
    chart = make_chart(db, specialty=spec.value, chart_number=f"QA{spec.name[:5]}")
    db.commit()

    r = _upload_standard(client, spec, _standard_key_file(spec, chart.chart_number))

    assert r.status_code == 200, r.text
    body = r.json()
    assert body["stored"] == [chart.chart_number]
    assert body["wrong_specialty"] == []
    assert body["not_found"] == []

    status = client.get("/practicelab/answer-key/status",
                        params={"specialty": spec.value}).json()
    assert status["with_answer_key"] == 1
    assert status["without_answer_key"] == 0

    audit_status = client.get("/auditor/keys/status",
                              params={"specialty": spec.value}).json()
    assert audit_status["auditable"] == 1
    assert audit_status["no_answer_key"] == 0

    batch = AuditBatch(name="QA", specialty=spec, charts_per_auditor=1,
                       created_by="QA", status=BatchStatus.OPEN)
    db.add(batch)
    db.commit()
    assert [c.id for c in chart_pool(db, batch)] == [chart.id]


@pytest.mark.parametrize("spec", sorted(EM_KEY_SPECIALTIES, key=lambda s: s.value),
                         ids=lambda s: s.value)
def test_em_store_upload_is_visible_to_coder_and_auditor_pool(client, db, spec):
    chart = make_chart(db, specialty=spec.value, chart_number=f"QA{spec.name}")
    db.commit()

    r = _upload_em(client, _em_key_file(chart.chart_number, spec))

    assert r.status_code == 200, r.text
    assert r.json()["stored"] == [chart.chart_number]

    status = client.get("/practicelab/answer-key/status",
                        params={"specialty": spec.value}).json()
    assert status["key_store"] == "em"
    assert status["with_answer_key"] == 1
    assert status["without_answer_key"] == 0

    batch = AuditBatch(name="QA EM", specialty=spec, charts_per_auditor=1,
                       created_by="QA", status=BatchStatus.OPEN)
    db.add(batch)
    db.commit()
    assert [c.id for c in chart_pool(db, batch)] == [chart.id]


def test_standard_upload_reports_wrong_specialty_without_storing(client, db):
    chart = make_chart(db, specialty="Surgery", chart_number="QAWRONG")
    db.commit()

    r = _upload_standard(client, Specialty.SDS,
                         _standard_key_file(Specialty.SDS, chart.chart_number))

    assert r.status_code == 200, r.text
    assert r.json()["stored"] == []
    assert r.json()["wrong_specialty"] == [chart.chart_number]
    assert db.query(AnswerKey).count() == 0


def test_standard_duplicate_key_is_skipped_then_replaced_with_passphrase(client, db):
    chart = make_chart(db, specialty="SDS", chart_number="QADUP")
    db.commit()
    first = _standard_key_file(Specialty.SDS, chart.chart_number)
    assert _upload_standard(client, Specialty.SDS, first).json()["stored"] == ["QADUP"]

    second = _fill(_template(Specialty.SDS), {
        "Chart_Number": chart.chart_number,
        "PDx_Code": "J18.9",
        "SDx_1": "I10",
        "CPT_1": "11042",
        "CPT_1_Modifier": "59",
        "CPT_1_Units": 1,
    })
    skipped = _upload_standard(client, Specialty.SDS, second)
    assert skipped.status_code == 200, skipped.text
    assert skipped.json()["skipped_duplicates"] == ["QADUP"]
    assert db.query(AnswerKey).filter_by(chart_id=chart.id).one().pdx_code == "E11.9"

    blocked = _upload_standard(client, Specialty.SDS, second, replace=True,
                               passphrase="wrong")
    assert blocked.status_code == 403

    replaced = _upload_standard(client, Specialty.SDS, second, replace=True)
    assert replaced.status_code == 200, replaced.text
    assert replaced.json()["replaced"] == ["QADUP"]
    assert db.query(AnswerKey).filter_by(chart_id=chart.id).one().pdx_code == "J18.9"


def test_standard_upload_fails_clearly_when_chart_number_header_is_missing(client, db):
    make_chart(db, specialty="SDS", chart_number="QAMISS")
    db.commit()
    data = _workbook(["PDx_Code", "SDx_1"], ["E11.9", "I10"])

    r = _upload_standard(client, Specialty.SDS, data)

    assert r.status_code in (400, 422)
    assert "Chart_Number" in r.json()["detail"]


def test_em_upload_reports_wrong_specialty_separately(client, db):
    chart = make_chart(db, specialty="Surgery", chart_number="QAEMWRONG")
    db.commit()

    r = _upload_em(client, _em_key_file(chart.chart_number, Specialty.EM))

    assert r.status_code == 200, r.text
    assert r.json()["stored"] == []
    assert r.json()["not_found"] == []
    assert r.json()["wrong_specialty"] == [chart.chart_number]
