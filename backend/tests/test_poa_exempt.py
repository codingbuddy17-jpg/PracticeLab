"""
CMS POA exempt codes: loaded with the code sets, applied everywhere POA is
keyed, graded or planted.

The rule each test pins: a code CMS exempts from POA reporting carries E, is
never a POA error for a coder, and never receives a planted POA error — and
when the list is NOT loaded, nothing changes at all.
"""
import importlib.util
import pathlib
import random

from conftest import make_chart
from models import AnswerKey, Specialty
from models.codes import CodeDescription
from routers.practicelab_pkg.shared import MASTER_PASSPHRASE
from services.audit_mutation import Corpus, MutationConfig, claim_from_key, generate
from services.grading_engine import IPAnswerKey, IPSubmission, compute_dpo_ip, grade_ip
from services.poa_exempt import correct_existing_keys, exempt_among, normalise_key_poa

ROOT = pathlib.Path(__file__).resolve().parents[2]
_spec = importlib.util.spec_from_file_location("ingest", ROOT / "scripts" / "ingest_code_sets.py")
ingest = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(ingest)

EXEMPT = ["Z87891", "Y929", "Z3800"]      # history of nicotine, place NOS, liveborn
REPORTABLE = ["J189", "I10", "E119"]


def _load(db, loaded=True):
    for c in EXEMPT:
        db.add(CodeDescription(code_system="ICD10CM", code=c, description=c,
                               poa_exempt=True if loaded else None))
    for c in REPORTABLE:
        db.add(CodeDescription(code_system="ICD10CM", code=c, description=c,
                               poa_exempt=False if loaded else None))
    db.commit()


# ── the CMS file ─────────────────────────────────────────────────────────────

CMS_SAMPLE = (b"Order27\tPOAexemptCode\tDescription\r\n"
              b"01238\tB90.0\tSequelae of central nervous system tuberculosis\r\n"
              b"13001\tZ87.891\tPersonal history of nicotine dependence\r\n")


def test_the_cms_file_parses_by_its_header_and_drops_dots():
    assert ingest.parse_poa_exempt(CMS_SAMPLE) == {"B900", "Z87891"}


def test_a_folder_holding_both_files_still_loads_the_real_code_set(tmp_path):
    """POAexemptCodesFY27.txt contains 'codes' and sorts first; it must not be read as the CM set."""
    (tmp_path / "POAexemptCodesFY27.txt").write_bytes(CMS_SAMPLE)
    (tmp_path / "icd10cm_codes_2027.txt").write_bytes(b"A000 Cholera\n")
    got = ingest._local(tmp_path, "codes", ".txt", exclude="poa")
    assert got == b"A000 Cholera\n"
    assert ingest._local(tmp_path, "poaexemptcodes", ".txt") == CMS_SAMPLE


def test_the_url_follows_the_fiscal_year():
    import datetime
    urls = ingest.poa_urls(datetime.date(2026, 11, 19))
    assert urls[0].endswith("/2027-poa-exempt-codes.zip")


# ── grading ──────────────────────────────────────────────────────────────────

def _ip(sdx_key, sdx_sub, exempt=frozenset(), pdx_poa=("Y", "Y"), pdx="J18.9"):
    ak = IPAnswerKey(pdx_code=pdx, pdx_poa=pdx_poa[0], sdx=sdx_key, poa_exempt=exempt)
    sub = IPSubmission(pdx_code=pdx, pdx_poa=pdx_poa[1], sdx=sdx_sub)
    return ak, sub


def test_poa_on_an_exempt_secondary_is_never_a_coder_error():
    ak, sub = _ip([{"code": "Z87.891", "poa": "Y"}], [{"code": "Z87.891", "poa": "E"}],
                  exempt=frozenset({"Z87891"}))
    res = grade_ip(ak, sub)
    assert not any(f.issue_type == "Wrong_POA" for f in res.feedback)


def test_the_same_mismatch_on_a_reportable_code_is_still_an_error():
    ak, sub = _ip([{"code": "I10", "poa": "Y"}], [{"code": "I10", "poa": "N"}],
                  exempt=frozenset({"Z87891"}))
    assert any(f.issue_type == "Wrong_POA" for f in grade_ip(ak, sub).feedback)


def test_an_exempt_principal_is_not_graded_on_poa():
    ak, sub = _ip([], [], exempt=frozenset({"Z3800"}), pdx="Z38.00", pdx_poa=("", "E"))
    assert grade_ip(ak, sub).pdx_score > 0


def test_without_the_list_everything_is_graded_as_before():
    ak, sub = _ip([{"code": "Z87.891", "poa": "Y"}], [{"code": "Z87.891", "poa": "E"}])
    assert any(f.issue_type == "Wrong_POA" for f in grade_ip(ak, sub).feedback)


def test_an_exempt_code_is_no_poa_opportunity():
    ak, sub = _ip([{"code": "Z87.891", "poa": "Y"}, {"code": "I10", "poa": "Y"}],
                  [{"code": "Z87.891", "poa": "N"}, {"code": "I10", "poa": "Y"}],
                  exempt=frozenset({"Z87891"}))
    dpo = compute_dpo_ip(ak, sub, True)
    # PDx + I10 only; Z87.891 is neither a chance nor a defect.
    assert (dpo.poa.opportunities, dpo.poa.defects) == (2, 0)


# ── keys ─────────────────────────────────────────────────────────────────────

def test_an_exempt_code_in_an_inpatient_key_becomes_e(db):
    _load(db)
    poa, sdx, n = normalise_key_poa(db, Specialty.IP_DRG, "J18.9", "Y",
                                    [{"code": "Z87.891", "poa": "Y"}, {"code": "I10", "poa": "N"}])
    assert (poa, [r["poa"] for r in sdx], n) == ("Y", ["E", "N"], 1)


def test_outpatient_keys_are_left_alone(db):
    _load(db)
    _, sdx, n = normalise_key_poa(db, Specialty.SDS, "J18.9", "", [{"code": "Z87.891", "poa": ""}])
    assert n == 0 and sdx[0]["poa"] == ""


def test_nothing_is_rewritten_when_the_list_is_not_loaded(db):
    _load(db, loaded=False)
    _, sdx, n = normalise_key_poa(db, Specialty.IP_DRG, "J18.9", "Y", [{"code": "Z87.891", "poa": "Y"}])
    assert n == 0 and sdx[0]["poa"] == "Y"


def test_saving_a_key_in_the_editor_sets_e_on_exempt_codes(client, db):
    _load(db)
    chart = make_chart(db, specialty="IP-DRG", chart_number="POA-ED-1")
    db.commit()
    res = client.put(f"/practicelab/answer-key/{chart.id}", json={
        "pdx_code": "Z38.00", "pdx_poa": "Y", "entered_by": "T", "passphrase": MASTER_PASSPHRASE,
        "sdx": [{"code": "Y92.9", "poa": "N"}, {"code": "I10", "poa": "Y"}]})
    assert res.status_code == 200, res.text
    db.expire_all()
    ak = db.query(AnswerKey).filter(AnswerKey.chart_id == chart.id).first()
    assert ak.pdx_poa == "E"
    assert [r["poa"] for r in ak.sdx] == ["E", "Y"]


def test_existing_keys_are_corrected_once_the_list_is_loaded(db):
    _load(db)
    chart = make_chart(db, specialty="IP-DRG", chart_number="POA-OLD-1")
    db.add(AnswerKey(chart_id=chart.id, specialty=Specialty.IP_DRG, pdx_code="J18.9", pdx_poa="Y",
                     sdx=[{"code": "Z87.891", "poa": "Y"}, {"code": "Y92.9", "poa": ""}], entered_by="t"))
    db.commit()
    assert correct_existing_keys(db) == {"keys": 1, "lines": 2}
    db.expire_all()
    ak = db.query(AnswerKey).filter(AnswerKey.chart_id == chart.id).first()
    assert [r["poa"] for r in ak.sdx] == ["E", "E"] and ak.pdx_poa == "Y"


# ── the auditor's error generator ────────────────────────────────────────────

def _key(sdx):
    return AnswerKey(pdx_code="J18.9", pdx_poa="Y", sdx=sdx, pcs=[], cpt=[], entered_by="t")


ONLY_POA = MutationConfig(**{f: (100 if f == "mix_poa" else 0)
                             for f in MutationConfig.__dataclass_fields__ if f.startswith("mix_")})


def test_a_poa_error_is_never_planted_on_an_exempt_code():
    """Measured over many seeds, not one: the planting is random."""
    key = _key([{"code": "Z87.891", "poa": "E"}, {"code": "Y92.9", "poa": "E"},
                {"code": "I10", "poa": "Y"}, {"code": "E11.9", "poa": "Y"}])
    corpus = Corpus(poa_exempt=frozenset({"Z87891", "Y929"}))
    planted = []
    for seed in range(200):
        _, truth = generate(key, Specialty.IP_DRG, seed=seed, cfg=ONLY_POA, corpus=corpus, budget=1)
        planted += [t for t in truth if t.get("field") == "poa"]
    assert planted, "expected POA errors on the reportable lines"
    assert not any(str(t.get("code") or "").replace(".", "") in {"Z87891", "Y929"} for t in planted)


def test_a_chart_whose_only_poa_lines_are_exempt_gets_no_poa_error():
    key = AnswerKey(pdx_code="Z38.00", pdx_poa="E", sdx=[{"code": "Z87.891", "poa": "E"}],
                    pcs=[], cpt=[], entered_by="t")
    corpus = Corpus(poa_exempt=frozenset({"Z3800", "Z87891"}))
    for seed in range(50):
        _, truth = generate(key, Specialty.IP_DRG, seed=seed, cfg=ONLY_POA, corpus=corpus, budget=1)
        assert not [t for t in truth if t.get("field") == "poa"]


# ── the API screens read ─────────────────────────────────────────────────────

def test_describe_says_which_codes_are_exempt(client, db):
    _load(db)
    d = client.get("/codes/describe", params={"codes": "Z87.891,I10", "section": "SDx"}).json()["descriptions"]
    assert d["Z87891"]["poa_exempt"] is True and d["I10"]["poa_exempt"] is False


def test_status_reports_whether_the_list_is_loaded(client, db):
    assert client.get("/codes/status").json()["poa_exempt_loaded"] is False
    _load(db)
    st = client.get("/codes/status").json()
    assert st["poa_exempt_loaded"] is True and st["poa_exempt_codes"] == 3


def test_exempt_among_is_one_bare_set(db):
    _load(db)
    assert exempt_among(db, ["Z87.891", "I10", "y92.9", ""]) == frozenset({"Z87891", "Y929"})


# ── the Excel template upload ────────────────────────────────────────────────

def test_a_template_upload_stores_e_on_exempt_codes(client, db):
    """Through the real template and upload route: Y and blank on exempt codes become E."""
    from test_answer_key_upload_phase1 import _fill, _template, _upload_standard
    _load(db)
    make_chart(db, specialty="IP-DRG", chart_number="POA-UP-1")
    db.commit()
    data = _fill(_template(Specialty.IP_DRG), {
        "Chart_Number": "POA-UP-1", "PDx_Code": "Z38.00", "PDx_POA": "Y",
        "SDx_1": "Z87.891", "SDx_1_POA": "N",
        "SDx_2": "Y92.9",
        "SDx_3": "I10", "SDx_3_POA": "Y",
    })
    res = _upload_standard(client, Specialty.IP_DRG, data)
    assert res.status_code == 200, res.text
    db.expire_all()
    ak = db.query(AnswerKey).join(AnswerKey.chart).filter_by(chart_number="POA-UP-1").first() \
        if hasattr(AnswerKey, "chart") else None
    if ak is None:
        from models import Chart
        cid = db.query(Chart.id).filter(Chart.chart_number == "POA-UP-1").scalar()
        ak = db.query(AnswerKey).filter(AnswerKey.chart_id == cid).first()
    assert ak.pdx_poa == "E"
    assert [r.get("poa") for r in ak.sdx] == ["E", "E", "Y"]
