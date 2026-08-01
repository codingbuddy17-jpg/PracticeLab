"""E/M MDM scoring module — answer key management, grading engine, scoring config."""
from __future__ import annotations

import json
from typing import Optional
from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, Form
from pydantic import BaseModel
from sqlalchemy.orm import Session
from sqlalchemy import text

from database import get_db
from models import Chart, Specialty
from services.excel_service import parse_em_answer_key_upload
from .shared import MASTER_PASSPHRASE

router = APIRouter()

# ── Specialties that use MDM-based E/M scoring ────────────────────────────────
EM_SPECIALTIES = {Specialty.EM, Specialty.ED_PROFEE}


def _is_em(specialty: Specialty) -> bool:
    return specialty in EM_SPECIALTIES


# ── COPA level derivation ─────────────────────────────────────────────────────

def derive_copa_level(d: dict) -> str:
    """Derive COPA level from element counts per 2023 AMA MDM table."""
    if d.get("copa_threat_to_life", 0) >= 1 or d.get("copa_chronic_severe", 0) >= 1:
        return "High"
    if (d.get("copa_chronic_exacerbation", 0) >= 1
            or d.get("copa_stable_chronic", 0) >= 2
            or d.get("copa_undiagnosed_new", 0) >= 1
            or d.get("copa_acute_systemic", 0) >= 1
            or d.get("copa_acute_complicated_injury", 0) >= 1):
        return "Moderate"
    if (d.get("copa_self_limited", 0) >= 2
            or d.get("copa_stable_chronic", 0) >= 1
            or d.get("copa_acute_uncomplicated", 0) >= 1
            or d.get("copa_stable_acute", 0) >= 1):
        return "Low"
    if d.get("copa_self_limited", 0) >= 1:
        return "Minimal"
    return "Minimal"


# ── Data Review level derivation ──────────────────────────────────────────────

def _cat1_count(d: dict) -> int:
    return (
        (1 if d.get("dr_prior_external_notes", 0) >= 1 else 0)
        + (1 if d.get("dr_review_test_results", 0) >= 1 else 0)
        + (1 if d.get("dr_order_tests", 0) >= 1 else 0)
        + (1 if d.get("dr_independent_historian") else 0)
    )


def derive_dr_level(d: dict) -> str:
    """Derive Data Review level from elements per 2023 AMA MDM table."""
    cat1 = _cat1_count(d)
    cat2 = bool(d.get("dr_independent_interpretation"))
    cat3 = bool(d.get("dr_external_discussion"))

    cat1_mod = cat1 >= 3
    cats_met = sum([cat1_mod, cat2, cat3])

    if cats_met >= 2:
        return "Extensive"
    if cats_met >= 1:
        return "Moderate"
    if cat1 >= 2 or cat2 or cat3:
        return "Limited"
    return "Minimal"


# ── Risk level derivation ─────────────────────────────────────────────────────

def derive_risk_level(d: dict) -> str:
    """Derive Risk level — highest single element present wins."""
    high_fields = [
        "risk_drug_intensive_monitoring", "risk_elective_major_with_factors",
        "risk_emergency_major_surgery", "risk_hospitalization_escalation",
        "risk_dnr_deescalate", "risk_parenteral_controlled",
    ]
    moderate_fields = [
        "risk_prescription_drug_mgmt", "risk_minor_surgery_with_factors",
        "risk_elective_major_no_factors", "risk_hospitalization", "risk_sdoh",
    ]
    if any(d.get(f) for f in high_fields):
        return "High"
    if any(d.get(f) for f in moderate_fields):
        return "Moderate"
    if d.get("risk_low"):
        return "Low"
    return "Minimal"


# ── Overall MDM level (2-of-3 rule) ──────────────────────────────────────────

_LEVEL_ORDER = {"Minimal": 0, "Low": 1, "Moderate": 2, "Extensive": 3, "High": 3}
_LEVEL_NAMES = ["Minimal", "Low", "Moderate", "High"]


def derive_mdm_level(copa: str, dr: str, risk: str) -> str:
    """2-of-3 rule: overall level = second-lowest of the three component levels."""
    scores = sorted([_LEVEL_ORDER.get(copa, 0), _LEVEL_ORDER.get(dr, 0), _LEVEL_ORDER.get(risk, 0)])
    return _LEVEL_NAMES[min(scores[1], 3)]


# ── EM code → MDM level mapping ───────────────────────────────────────────────

_EM_CODE_LEVEL = {
    "99202": "Straightforward", "99212": "Straightforward",
    "99203": "Low", "99213": "Low",
    "99204": "Moderate", "99214": "Moderate",
    "99205": "High", "99215": "High",
    "99281": "Minimal", "99282": "Straightforward",
    "99283": "Low", "99284": "Moderate", "99285": "High",
}


def em_code_to_level(code: str) -> Optional[str]:
    return _EM_CODE_LEVEL.get(code.strip())


# ── Scoring engine ────────────────────────────────────────────────────────────

def _j(v):
    if isinstance(v, str):
        try:
            return json.loads(v)
        except Exception:
            return []
    return v or []


def _clean_codes(lst: list) -> list:
    return [str(c).strip().upper() for c in lst if c and str(c).strip().lower() not in ("", "none")]


# ── Time-based levelling (2021+ office/outpatient E/M) ───────────────────────
#
# A visit may be levelled by total time on the date of encounter OR by MDM —
# the coder chooses. ED codes (99281-99285) have no time option and are always
# MDM, so the Time path is never offered for them.
#
# Total time on date of encounter, per AMA CPT.
EM_TIME_BANDS = {
    # New patient
    "99202": (15, 29), "99203": (30, 44), "99204": (45, 59), "99205": (60, 74),
    # Established patient
    "99212": (10, 19), "99213": (20, 29), "99214": (30, 39), "99215": (40, 54),
}


def time_supports_code(total_time, em_code: str) -> bool:
    """Does the documented time fall in the band supporting this code?

    Graded on band rather than exact digits: coders read 'approximately 40
    minutes' off a chart, and failing them on transcription would test the
    wrong skill.
    """
    band = EM_TIME_BANDS.get((em_code or "").strip())
    if not band or total_time in (None, ""):
        return False
    try:
        mins = int(float(total_time))
    except (TypeError, ValueError):
        return False
    return band[0] <= mins <= band[1]


def code_supports_time(em_code: str) -> bool:
    """True when the code can be levelled by time at all (office/outpatient)."""
    return (em_code or "").strip() in EM_TIME_BANDS


def grade_em_chart(ak: dict, sub: dict, cfg: dict, overcoding_penalty: bool = True) -> dict:
    """
    Grade one E/M chart submission against its answer key.

    ak  — answer key dict (from em_answer_keys row)
    sub — coder submission dict
    cfg — em_scoring_configs row as dict
    Returns scoring breakdown dict.
    """
    l1w = cfg["line1_weight"]
    l2w = cfg["line2_weight"]
    em_w = cfg["em_level_weight"]
    cpt_w = cfg["cpt_weight"]
    dx_w = cfg["dx_weight"]
    copa_w = cfg["copa_weight"]
    dr_w = cfg["dr_weight"]
    risk_w = cfg["risk_weight"]

    # ── Derive submitted levels ───────────────────────────────────────────────
    derived_copa = derive_copa_level({k.replace("sub_", ""): v for k, v in sub.items() if k.startswith("sub_copa")})
    derived_dr = derive_dr_level({k.replace("sub_", ""): v for k, v in sub.items() if k.startswith("sub_dr")})
    derived_risk = derive_risk_level({k.replace("sub_", ""): v for k, v in sub.items() if k.startswith("sub_risk")})

    ak_copa = ak.get("copa_level", "")
    ak_dr = ak.get("dr_level", "")
    ak_risk = ak.get("risk_level", "")

    # ── Adjust weights when no procedure CPTs in answer key ──────────────────
    ak_cpts = _clean_codes(_j(ak.get("procedure_cpts", "[]")))
    if not ak_cpts:
        half = cpt_w / 2
        em_w_adj = em_w + half
        dx_w_adj = dx_w + half
        cpt_w_adj = 0.0
    else:
        em_w_adj = em_w
        dx_w_adj = dx_w
        cpt_w_adj = cpt_w

    # ── Coding Accuracy ───────────────────────────────────────────────────────
    # E/M Level — complexity AND patient type must both match (when AK patient_type != NA)
    sub_em_level = em_code_to_level(sub.get("sub_em_code") or "")
    ak_em_level = em_code_to_level(ak.get("em_code") or "")
    ak_patient_type = (ak.get("patient_type") or "NA").upper().strip()
    sub_patient_type = (sub.get("sub_patient_type") or "NA").upper().strip()
    patient_type_ok = (ak_patient_type == "NA") or (sub_patient_type == ak_patient_type)
    em_level_score = em_w_adj if (sub_em_level and sub_em_level == ak_em_level and patient_type_ok) else 0.0
    patient_type_mismatch = (ak_patient_type != "NA") and (not patient_type_ok)

    # ── Levelling method: MDM or Time ────────────────────────────────────────
    # Coding Accuracy is scored on the final code regardless of method — either
    # route can legitimately reach the right answer. The method mistake costs
    # Reasoning Accuracy instead, which is what "justify it correctly" means.
    ak_method = (ak.get("level_method") or "MDM").upper().strip()
    sub_method = (sub.get("sub_level_method") or "MDM").upper().strip()
    method_ok = (ak_method == sub_method)
    ak_is_time = (ak_method == "TIME")
    time_ok = False
    if ak_is_time and method_ok:
        time_ok = time_supports_code(sub.get("sub_total_time"), ak.get("em_code") or "")
    method_mismatch = not method_ok

    # CPT (proportional, equal weight per CPT, overcoding penalty)
    cpt_score = 0.0
    if ak_cpts and cpt_w_adj > 0:
        sub_cpts = _clean_codes(_j(sub.get("sub_procedure_cpts", "[]")))
        per_cpt = cpt_w_adj / len(ak_cpts)
        matched = sum(1 for c in ak_cpts if c in sub_cpts)
        cpt_score = matched * per_cpt
        if overcoding_penalty:
            over = max(0, len(sub_cpts) - len(ak_cpts))
            penalty = over * per_cpt
            cpt_score = max(0.0, cpt_score - penalty)

    # Dx (proportional, overcoding penalty)
    ak_dx = _clean_codes(_j(ak.get("dx_codes", "[]")))
    sub_dx = _clean_codes(_j(sub.get("sub_dx_codes", "[]")))
    dx_score = 0.0
    if ak_dx:
        per_dx = dx_w_adj / len(ak_dx)
        matched_dx = sum(1 for c in ak_dx if c in sub_dx)
        dx_score = matched_dx * per_dx
        if overcoding_penalty:
            over_dx = max(0, len(sub_dx) - len(ak_dx))
            dx_score = max(0.0, dx_score - over_dx * per_dx)
    # No AK dx → full dx score (chart has no expected dx)
    elif dx_w_adj > 0:
        dx_score = dx_w_adj

    coding_accuracy_total = em_level_score + cpt_score + dx_score

    # ── Reasoning Accuracy (element proportion) ───────────────────────────────
    copa_fields = [
        "copa_self_limited", "copa_stable_acute", "copa_stable_chronic",
        "copa_acute_uncomplicated", "copa_chronic_exacerbation",
        "copa_undiagnosed_new", "copa_acute_systemic",
        "copa_acute_complicated_injury", "copa_chronic_severe", "copa_threat_to_life",
    ]
    dr_fields = [
        "dr_prior_external_notes", "dr_review_test_results", "dr_order_tests",
        "dr_independent_historian", "dr_independent_interpretation", "dr_external_discussion",
    ]
    risk_fields = [
        "risk_low", "risk_prescription_drug_mgmt", "risk_minor_surgery_with_factors",
        "risk_elective_major_no_factors", "risk_hospitalization", "risk_sdoh",
        "risk_drug_intensive_monitoring", "risk_elective_major_with_factors",
        "risk_emergency_major_surgery", "risk_hospitalization_escalation",
        "risk_dnr_deescalate", "risk_parenteral_controlled",
    ]

    def _element_score(fields: list, ak_row: dict, sub_row: dict, weight: float) -> float:
        ak_vals = [int(ak_row.get(f, 0) or 0) for f in fields]
        sub_vals = [int(sub_row.get(f"sub_{f}", 0) or 0) for f in fields]
        total_ak = sum(min(v, 1) for v in ak_vals)  # count non-zero AK elements
        if total_ak == 0:
            return weight  # no elements expected → full score
        # Count only the elements the key actually expects. The previous version
        # counted every field where AK and submission agreed — including the many
        # both-zero fields — so `correct` ran far above `total_ak` and the score
        # blew past its weight (COPA alone returned 100 against a weight of 10).
        correct = sum(1 for a, s in zip(ak_vals, sub_vals) if a > 0 and a == s)
        return round((correct / total_ak) * weight, 2)

    if ak_is_time:
        # Time-levelled chart: MDM elements are not the operative criteria, so
        # they are not scored. Reasoning credit turns on picking the Time route
        # and reading the time correctly.
        reasoning_w = copa_w + dr_w + risk_w
        if not method_ok:
            reasoning_earned = 0.0          # levelled by MDM when time was the basis
        elif time_ok:
            reasoning_earned = reasoning_w  # right route, time in band
        else:
            reasoning_earned = reasoning_w / 2   # right route, wrong time
        copa_element_score = dr_element_score = risk_element_score = 0.0
        reasoning_accuracy_total = round(reasoning_earned, 2)
    elif not method_ok:
        # MDM-levelled chart but the coder levelled by time — the MDM elements
        # they skipped are exactly what Reasoning Accuracy measures.
        copa_element_score = dr_element_score = risk_element_score = 0.0
        reasoning_accuracy_total = 0.0
    else:
        copa_element_score = _element_score(copa_fields, ak, sub, copa_w)
        dr_element_score = _element_score(dr_fields, ak, sub, dr_w)
        risk_element_score = _element_score(risk_fields, ak, sub, risk_w)
        reasoning_accuracy_total = copa_element_score + dr_element_score + risk_element_score

    total_score = round(coding_accuracy_total + reasoning_accuracy_total, 1)
    pass_threshold = cfg.get("pass_threshold", 80.0)
    pass_fail = "PASS" if total_score >= pass_threshold else "FAIL"

    return {
        "derived_copa_level": derived_copa,
        "derived_dr_level": derived_dr,
        "derived_risk_level": derived_risk,
        "ak_level_method": ak_method,
        "sub_level_method": sub_method,
        "method_mismatch": method_mismatch,
        "time_ok": time_ok,
        "em_level_score": round(em_level_score, 2),
        "cpt_score": round(cpt_score, 2),
        "dx_score": round(dx_score, 2),
        "coding_accuracy_total": round(coding_accuracy_total, 2),
        "copa_element_score": copa_element_score,
        "dr_element_score": dr_element_score,
        "risk_element_score": risk_element_score,
        "reasoning_accuracy_total": round(reasoning_accuracy_total, 2),
        "total_score": total_score,
        "pass_fail": pass_fail,
        "patient_type_mismatch": patient_type_mismatch,
        "ak_patient_type": ak_patient_type,
        "sub_patient_type": sub_patient_type,
    }


# ── Pydantic models ───────────────────────────────────────────────────────────

class EMAnswerKeyPayload(BaseModel):
    chart_id: int
    copa_self_limited: int = 0
    copa_stable_acute: int = 0
    copa_stable_chronic: int = 0
    copa_acute_uncomplicated: int = 0
    copa_chronic_exacerbation: int = 0
    copa_undiagnosed_new: int = 0
    copa_acute_systemic: int = 0
    copa_acute_complicated_injury: int = 0
    copa_chronic_severe: int = 0
    copa_threat_to_life: int = 0
    copa_level_overridden: bool = False
    copa_level_override: Optional[str] = None
    dr_prior_external_notes: int = 0
    dr_review_test_results: int = 0
    dr_order_tests: int = 0
    dr_independent_historian: bool = False
    dr_independent_interpretation: bool = False
    dr_external_discussion: bool = False
    dr_level_overridden: bool = False
    dr_level_override: Optional[str] = None
    risk_low: bool = False
    risk_prescription_drug_mgmt: bool = False
    risk_minor_surgery_with_factors: bool = False
    risk_elective_major_no_factors: bool = False
    risk_hospitalization: bool = False
    risk_sdoh: bool = False
    risk_drug_intensive_monitoring: bool = False
    risk_elective_major_with_factors: bool = False
    risk_emergency_major_surgery: bool = False
    risk_hospitalization_escalation: bool = False
    risk_dnr_deescalate: bool = False
    risk_parenteral_controlled: bool = False
    risk_level_overridden: bool = False
    risk_level_override: Optional[str] = None
    em_code: str
    em_modifier: Optional[str] = None
    patient_type: Optional[str] = "NA"  # New / Established / NA
    level_method: Optional[str] = "MDM"  # MDM | TIME (office/outpatient only)
    total_time: Optional[int] = None     # total minutes on date of encounter
    dx_codes: list = []
    procedure_cpts: list = []
    entered_by: str


class EMScoringConfigPayload(BaseModel):
    line1_weight: float = 70.0
    line2_weight: float = 30.0
    em_level_weight: float = 23.33
    cpt_weight: float = 23.33
    dx_weight: float = 23.34
    copa_weight: float = 10.0
    dr_weight: float = 10.0
    risk_weight: float = 10.0
    pass_threshold: float = 80.0
    overcoding_penalty: bool = True
    passphrase: str
    updated_by: str


# ── Answer key endpoints ──────────────────────────────────────────────────────

@router.get("/em/answer-key/list")
def list_em_answer_keys(db: Session = Depends(get_db)):
    rows = db.execute(text("""
        SELECT eak.chart_id, c.chart_number, c.category, c.specialty,
               eak.em_code, eak.copa_level, eak.dr_level, eak.risk_level,
               eak.entered_by, eak.entered_at,
               eak.copa_level_overridden, eak.dr_level_overridden, eak.risk_level_overridden
        FROM em_answer_keys eak
        JOIN charts c ON c.id = eak.chart_id
        ORDER BY c.chart_number
    """)).mappings().fetchall()
    return [dict(r) for r in rows]


@router.get("/em/answer-key/{chart_id}")
def get_em_answer_key(chart_id: int, db: Session = Depends(get_db)):
    row = db.execute(
        text("SELECT * FROM em_answer_keys WHERE chart_id = :c"), {"c": chart_id}
    ).mappings().first()
    if not row:
        raise HTTPException(status_code=404, detail="No E/M answer key for this chart")
    return dict(row)


@router.post("/em/answer-key")
def upsert_em_answer_key(payload: EMAnswerKeyPayload, db: Session = Depends(get_db)):
    d = payload.dict()
    chart_id = d.pop("chart_id")
    entered_by = d.pop("entered_by")

    # Derive levels (or use override)
    copa_level = d.pop("copa_level_override") or derive_copa_level(d)
    dr_level = d.pop("dr_level_override") or derive_dr_level(d)
    risk_level = d.pop("risk_level_override") or derive_risk_level(d)

    copa_overridden = d.pop("copa_level_overridden")
    dr_overridden = d.pop("dr_level_overridden")
    risk_overridden = d.pop("risk_level_overridden")

    dx_codes = json.dumps(d.pop("dx_codes"))
    procedure_cpts = json.dumps(d.pop("procedure_cpts"))

    existing = db.execute(
        text("SELECT id FROM em_answer_keys WHERE chart_id = :c"), {"c": chart_id}
    ).first()

    if existing:
        db.execute(text("""
            UPDATE em_answer_keys SET
                copa_self_limited=:copa_self_limited,
                copa_stable_acute=:copa_stable_acute,
                copa_stable_chronic=:copa_stable_chronic,
                copa_acute_uncomplicated=:copa_acute_uncomplicated,
                copa_chronic_exacerbation=:copa_chronic_exacerbation,
                copa_undiagnosed_new=:copa_undiagnosed_new,
                copa_acute_systemic=:copa_acute_systemic,
                copa_acute_complicated_injury=:copa_acute_complicated_injury,
                copa_chronic_severe=:copa_chronic_severe,
                copa_threat_to_life=:copa_threat_to_life,
                copa_level=:copa_level, copa_level_overridden=:copa_overridden,
                dr_prior_external_notes=:dr_prior_external_notes,
                dr_review_test_results=:dr_review_test_results,
                dr_order_tests=:dr_order_tests,
                dr_independent_historian=:dr_independent_historian,
                dr_independent_interpretation=:dr_independent_interpretation,
                dr_external_discussion=:dr_external_discussion,
                dr_level=:dr_level, dr_level_overridden=:dr_overridden,
                risk_low=:risk_low,
                risk_prescription_drug_mgmt=:risk_prescription_drug_mgmt,
                risk_minor_surgery_with_factors=:risk_minor_surgery_with_factors,
                risk_elective_major_no_factors=:risk_elective_major_no_factors,
                risk_hospitalization=:risk_hospitalization,
                risk_sdoh=:risk_sdoh,
                risk_drug_intensive_monitoring=:risk_drug_intensive_monitoring,
                risk_elective_major_with_factors=:risk_elective_major_with_factors,
                risk_emergency_major_surgery=:risk_emergency_major_surgery,
                risk_hospitalization_escalation=:risk_hospitalization_escalation,
                risk_dnr_deescalate=:risk_dnr_deescalate,
                risk_parenteral_controlled=:risk_parenteral_controlled,
                risk_level=:risk_level, risk_level_overridden=:risk_overridden,
                em_code=:em_code, em_modifier=:em_modifier, patient_type=:patient_type,
                level_method=:level_method, total_time=:total_time,
                dx_codes=:dx_codes, procedure_cpts=:procedure_cpts,
                entered_by=:entered_by, entered_at=CURRENT_TIMESTAMP
            WHERE chart_id=:chart_id
        """), {**d, "chart_id": chart_id, "entered_by": entered_by,
               "copa_level": copa_level, "copa_overridden": copa_overridden,
               "dr_level": dr_level, "dr_overridden": dr_overridden,
               "risk_level": risk_level, "risk_overridden": risk_overridden,
               "patient_type": (payload.patient_type or "NA").upper(),
               "level_method": (payload.level_method or "MDM").upper(),
               "total_time": payload.total_time,
               "dx_codes": dx_codes, "procedure_cpts": procedure_cpts})
    else:
        db.execute(text("""
            INSERT INTO em_answer_keys (
                chart_id,
                copa_self_limited, copa_stable_acute, copa_stable_chronic,
                copa_acute_uncomplicated, copa_chronic_exacerbation, copa_undiagnosed_new,
                copa_acute_systemic, copa_acute_complicated_injury,
                copa_chronic_severe, copa_threat_to_life,
                copa_level, copa_level_overridden,
                dr_prior_external_notes, dr_review_test_results, dr_order_tests,
                dr_independent_historian, dr_independent_interpretation, dr_external_discussion,
                dr_level, dr_level_overridden,
                risk_low, risk_prescription_drug_mgmt, risk_minor_surgery_with_factors,
                risk_elective_major_no_factors, risk_hospitalization, risk_sdoh,
                risk_drug_intensive_monitoring, risk_elective_major_with_factors,
                risk_emergency_major_surgery, risk_hospitalization_escalation,
                risk_dnr_deescalate, risk_parenteral_controlled,
                risk_level, risk_level_overridden,
                em_code, em_modifier, patient_type, level_method, total_time, dx_codes, procedure_cpts,
                entered_by
            ) VALUES (
                :chart_id,
                :copa_self_limited, :copa_stable_acute, :copa_stable_chronic,
                :copa_acute_uncomplicated, :copa_chronic_exacerbation, :copa_undiagnosed_new,
                :copa_acute_systemic, :copa_acute_complicated_injury,
                :copa_chronic_severe, :copa_threat_to_life,
                :copa_level, :copa_overridden,
                :dr_prior_external_notes, :dr_review_test_results, :dr_order_tests,
                :dr_independent_historian, :dr_independent_interpretation, :dr_external_discussion,
                :dr_level, :dr_overridden,
                :risk_low, :risk_prescription_drug_mgmt, :risk_minor_surgery_with_factors,
                :risk_elective_major_no_factors, :risk_hospitalization, :risk_sdoh,
                :risk_drug_intensive_monitoring, :risk_elective_major_with_factors,
                :risk_emergency_major_surgery, :risk_hospitalization_escalation,
                :risk_dnr_deescalate, :risk_parenteral_controlled,
                :risk_level, :risk_overridden,
                :em_code, :em_modifier, :patient_type, :level_method, :total_time, :dx_codes, :procedure_cpts,
                :entered_by
            )
        """), {**d, "chart_id": chart_id, "entered_by": entered_by,
               "copa_level": copa_level, "copa_overridden": copa_overridden,
               "dr_level": dr_level, "dr_overridden": dr_overridden,
               "risk_level": risk_level, "risk_overridden": risk_overridden,
               "patient_type": (payload.patient_type or "NA").upper(),
               "level_method": (payload.level_method or "MDM").upper(),
               "total_time": payload.total_time,
               "dx_codes": dx_codes, "procedure_cpts": procedure_cpts})
    db.commit()
    return {"status": "ok", "copa_level": copa_level, "dr_level": dr_level, "risk_level": risk_level}


@router.delete("/em/answer-key/{chart_id}")
def delete_em_answer_key(chart_id: int, passphrase: str, db: Session = Depends(get_db)):
    if passphrase != MASTER_PASSPHRASE:
        raise HTTPException(status_code=403, detail="Invalid passphrase")
    db.execute(text("DELETE FROM em_answer_keys WHERE chart_id = :c"), {"c": chart_id})
    db.commit()
    return {"status": "deleted"}


# ── Scoring config endpoints ──────────────────────────────────────────────────

@router.get("/em/scoring-config")
def get_em_scoring_config(db: Session = Depends(get_db)):
    row = db.execute(text("SELECT * FROM em_scoring_configs WHERE id = 1")).mappings().first()
    if not row:
        return {
            "line1_weight": 70.0, "line2_weight": 30.0,
            "em_level_weight": 23.33, "cpt_weight": 23.33, "dx_weight": 23.34,
            "copa_weight": 10.0, "dr_weight": 10.0, "risk_weight": 10.0,
            "pass_threshold": 80.0, "overcoding_penalty": True,
        }
    return dict(row)


@router.put("/em/scoring-config")
def update_em_scoring_config(payload: EMScoringConfigPayload, db: Session = Depends(get_db)):
    if payload.passphrase != MASTER_PASSPHRASE:
        raise HTTPException(status_code=403, detail="Invalid passphrase")
    d = payload.dict()
    d.pop("passphrase")
    d["updated_at"] = "CURRENT_TIMESTAMP"
    db.execute(text("""
        INSERT INTO em_scoring_configs
            (id, line1_weight, line2_weight, em_level_weight, cpt_weight, dx_weight,
             copa_weight, dr_weight, risk_weight, pass_threshold, overcoding_penalty,
             updated_by, updated_at)
        VALUES
            (1, :line1_weight, :line2_weight, :em_level_weight, :cpt_weight, :dx_weight,
             :copa_weight, :dr_weight, :risk_weight, :pass_threshold, :overcoding_penalty,
             :updated_by, CURRENT_TIMESTAMP)
        ON CONFLICT (id) DO UPDATE SET
            line1_weight=EXCLUDED.line1_weight,
            line2_weight=EXCLUDED.line2_weight,
            em_level_weight=EXCLUDED.em_level_weight,
            cpt_weight=EXCLUDED.cpt_weight,
            dx_weight=EXCLUDED.dx_weight,
            copa_weight=EXCLUDED.copa_weight,
            dr_weight=EXCLUDED.dr_weight,
            risk_weight=EXCLUDED.risk_weight,
            pass_threshold=EXCLUDED.pass_threshold,
            overcoding_penalty=EXCLUDED.overcoding_penalty,
            updated_by=EXCLUDED.updated_by,
            updated_at=EXCLUDED.updated_at
    """), {k: v for k, v in d.items() if k != "updated_at"})
    db.commit()
    return {"status": "saved"}


# ── Bulk Excel upload ─────────────────────────────────────────────────────────

@router.post("/em/answer-key/upload")
def upload_em_answer_keys(
    file: UploadFile = File(...),
    entered_by: str = Form(...),
    replace: bool = Form(False),
    passphrase: str = Form(""),
    db: Session = Depends(get_db),
):
    if replace and passphrase != MASTER_PASSPHRASE:
        raise HTTPException(status_code=403, detail="Invalid passphrase")

    try:
        rows = parse_em_answer_key_upload(file.file.read())
    except Exception as e:
        raise HTTPException(status_code=422, detail=f"Could not parse file: {e}")

    stored, replaced, skipped, not_found = [], [], [], []

    for row in rows:
        chart_num = row["chart_number"]
        chart = db.query(Chart).filter(Chart.chart_number == chart_num).first()
        if not chart:
            not_found.append(chart_num)
            continue

        if chart.specialty.value not in ("E/M", "ED Profee"):
            not_found.append(chart_num)
            continue

        em_code = row.get("em_code", "").strip()
        if not em_code:
            skipped.append(chart_num)
            continue

        entered_by_val = row.get("entered_by") or entered_by

        copa_override_raw = row.get("copa_level_override", "") or ""
        dr_override_raw = row.get("dr_level_override", "") or ""
        risk_override_raw = row.get("risk_level_override", "") or ""

        copa_level = copa_override_raw or derive_copa_level(row)
        dr_level = dr_override_raw or derive_dr_level(row)
        risk_level = risk_override_raw or derive_risk_level(row)

        dx_codes = json.dumps(row.get("dx_codes", []))
        procedure_cpts = json.dumps(row.get("procedure_cpts", []))

        existing = db.execute(
            text("SELECT id FROM em_answer_keys WHERE chart_id = :c"), {"c": chart.id}
        ).first()

        params = {
            "chart_id": chart.id,
            "copa_self_limited": row.get("copa_self_limited", 0),
            "copa_stable_acute": row.get("copa_stable_acute", 0),
            "copa_stable_chronic": row.get("copa_stable_chronic", 0),
            "copa_acute_uncomplicated": row.get("copa_acute_uncomplicated", 0),
            "copa_chronic_exacerbation": row.get("copa_chronic_exacerbation", 0),
            "copa_undiagnosed_new": row.get("copa_undiagnosed_new", 0),
            "copa_acute_systemic": row.get("copa_acute_systemic", 0),
            "copa_acute_complicated_injury": row.get("copa_acute_complicated_injury", 0),
            "copa_chronic_severe": row.get("copa_chronic_severe", 0),
            "copa_threat_to_life": row.get("copa_threat_to_life", 0),
            "copa_level": copa_level,
            "copa_level_overridden": bool(copa_override_raw),
            "dr_prior_external_notes": row.get("dr_prior_external_notes", 0),
            "dr_review_test_results": row.get("dr_review_test_results", 0),
            "dr_order_tests": row.get("dr_order_tests", 0),
            "dr_independent_historian": row.get("dr_independent_historian", False),
            "dr_independent_interpretation": row.get("dr_independent_interpretation", False),
            "dr_external_discussion": row.get("dr_external_discussion", False),
            "dr_level": dr_level,
            "dr_level_overridden": bool(dr_override_raw),
            "risk_low": row.get("risk_low", False),
            "risk_prescription_drug_mgmt": row.get("risk_prescription_drug_mgmt", False),
            "risk_minor_surgery_with_factors": row.get("risk_minor_surgery_with_factors", False),
            "risk_elective_major_no_factors": row.get("risk_elective_major_no_factors", False),
            "risk_hospitalization": row.get("risk_hospitalization", False),
            "risk_sdoh": row.get("risk_sdoh", False),
            "risk_drug_intensive_monitoring": row.get("risk_drug_intensive_monitoring", False),
            "risk_elective_major_with_factors": row.get("risk_elective_major_with_factors", False),
            "risk_emergency_major_surgery": row.get("risk_emergency_major_surgery", False),
            "risk_hospitalization_escalation": row.get("risk_hospitalization_escalation", False),
            "risk_dnr_deescalate": row.get("risk_dnr_deescalate", False),
            "risk_parenteral_controlled": row.get("risk_parenteral_controlled", False),
            "risk_level": risk_level,
            "risk_level_overridden": bool(risk_override_raw),
            "em_code": em_code,
            "em_modifier": row.get("em_modifier", "") or "",
            "patient_type": (row.get("patient_type") or "NA").upper().strip(),
            "level_method": (row.get("level_method") or "MDM").upper().strip(),
            "total_time": row.get("total_time"),
            "dx_codes": dx_codes,
            "procedure_cpts": procedure_cpts,
            "entered_by": entered_by_val,
        }

        if existing:
            if not replace:
                skipped.append(chart_num)
                continue
            db.execute(text("""
                UPDATE em_answer_keys SET
                    copa_self_limited=:copa_self_limited, copa_stable_acute=:copa_stable_acute,
                    copa_stable_chronic=:copa_stable_chronic, copa_acute_uncomplicated=:copa_acute_uncomplicated,
                    copa_chronic_exacerbation=:copa_chronic_exacerbation, copa_undiagnosed_new=:copa_undiagnosed_new,
                    copa_acute_systemic=:copa_acute_systemic, copa_acute_complicated_injury=:copa_acute_complicated_injury,
                    copa_chronic_severe=:copa_chronic_severe, copa_threat_to_life=:copa_threat_to_life,
                    copa_level=:copa_level, copa_level_overridden=:copa_level_overridden,
                    dr_prior_external_notes=:dr_prior_external_notes, dr_review_test_results=:dr_review_test_results,
                    dr_order_tests=:dr_order_tests, dr_independent_historian=:dr_independent_historian,
                    dr_independent_interpretation=:dr_independent_interpretation, dr_external_discussion=:dr_external_discussion,
                    dr_level=:dr_level, dr_level_overridden=:dr_level_overridden,
                    risk_low=:risk_low, risk_prescription_drug_mgmt=:risk_prescription_drug_mgmt,
                    risk_minor_surgery_with_factors=:risk_minor_surgery_with_factors,
                    risk_elective_major_no_factors=:risk_elective_major_no_factors,
                    risk_hospitalization=:risk_hospitalization, risk_sdoh=:risk_sdoh,
                    risk_drug_intensive_monitoring=:risk_drug_intensive_monitoring,
                    risk_elective_major_with_factors=:risk_elective_major_with_factors,
                    risk_emergency_major_surgery=:risk_emergency_major_surgery,
                    risk_hospitalization_escalation=:risk_hospitalization_escalation,
                    risk_dnr_deescalate=:risk_dnr_deescalate, risk_parenteral_controlled=:risk_parenteral_controlled,
                    risk_level=:risk_level, risk_level_overridden=:risk_level_overridden,
                    em_code=:em_code, em_modifier=:em_modifier, patient_type=:patient_type,
                level_method=:level_method, total_time=:total_time,
                    dx_codes=:dx_codes, procedure_cpts=:procedure_cpts,
                    entered_by=:entered_by, entered_at=CURRENT_TIMESTAMP
                WHERE chart_id=:chart_id
            """), params)
            replaced.append(chart_num)
        else:
            db.execute(text("""
                INSERT INTO em_answer_keys (
                    chart_id,
                    copa_self_limited, copa_stable_acute, copa_stable_chronic,
                    copa_acute_uncomplicated, copa_chronic_exacerbation, copa_undiagnosed_new,
                    copa_acute_systemic, copa_acute_complicated_injury, copa_chronic_severe, copa_threat_to_life,
                    copa_level, copa_level_overridden,
                    dr_prior_external_notes, dr_review_test_results, dr_order_tests,
                    dr_independent_historian, dr_independent_interpretation, dr_external_discussion,
                    dr_level, dr_level_overridden,
                    risk_low, risk_prescription_drug_mgmt, risk_minor_surgery_with_factors,
                    risk_elective_major_no_factors, risk_hospitalization, risk_sdoh,
                    risk_drug_intensive_monitoring, risk_elective_major_with_factors,
                    risk_emergency_major_surgery, risk_hospitalization_escalation,
                    risk_dnr_deescalate, risk_parenteral_controlled,
                    risk_level, risk_level_overridden,
                    em_code, em_modifier, patient_type, level_method, total_time, dx_codes, procedure_cpts, entered_by
                ) VALUES (
                    :chart_id,
                    :copa_self_limited, :copa_stable_acute, :copa_stable_chronic,
                    :copa_acute_uncomplicated, :copa_chronic_exacerbation, :copa_undiagnosed_new,
                    :copa_acute_systemic, :copa_acute_complicated_injury, :copa_chronic_severe, :copa_threat_to_life,
                    :copa_level, :copa_level_overridden,
                    :dr_prior_external_notes, :dr_review_test_results, :dr_order_tests,
                    :dr_independent_historian, :dr_independent_interpretation, :dr_external_discussion,
                    :dr_level, :dr_level_overridden,
                    :risk_low, :risk_prescription_drug_mgmt, :risk_minor_surgery_with_factors,
                    :risk_elective_major_no_factors, :risk_hospitalization, :risk_sdoh,
                    :risk_drug_intensive_monitoring, :risk_elective_major_with_factors,
                    :risk_emergency_major_surgery, :risk_hospitalization_escalation,
                    :risk_dnr_deescalate, :risk_parenteral_controlled,
                    :risk_level, :risk_level_overridden,
                    :em_code, :em_modifier, :patient_type, :level_method, :total_time, :dx_codes, :procedure_cpts, :entered_by
                )
            """), params)
            stored.append(chart_num)

    db.commit()
    return {
        "stored": stored,
        "replaced": replaced,
        "skipped_duplicates": skipped,
        "not_found": not_found,
    }


# ── Excel template download ───────────────────────────────────────────────────

@router.get("/em/answer-key/template")
def download_em_template():
    """Return E/M answer key Excel template as base64."""
    import base64
    from io import BytesIO
    import openpyxl
    from openpyxl.styles import Font, PatternFill, Alignment

    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "E/M Answer Key"

    hdr_font = Font(bold=True, color="FFFFFF")
    hdr_fill = PatternFill("solid", fgColor="1e3a5f")
    section_fill = PatternFill("solid", fgColor="dbeafe")
    section_font = Font(bold=True, color="1e3a5f")

    def hdr(cell, val):
        ws[cell] = val
        ws[cell].font = hdr_font
        ws[cell].fill = hdr_fill
        ws[cell].alignment = Alignment(horizontal="center", wrap_text=True)

    def sec(cell, val):
        ws[cell] = val
        ws[cell].font = section_font
        ws[cell].fill = section_fill

    # Column headers
    hdr("A1", "Chart Number")
    hdr("B1", "COPA: Self-limited/Minor Problems (count)")
    hdr("C1", "COPA: Stable Acute Illness (count)")
    hdr("D1", "COPA: Stable Chronic Illness (count)")
    hdr("E1", "COPA: Acute Uncomplicated (count)")
    hdr("F1", "COPA: Chronic Exacerbation (count)")
    hdr("G1", "COPA: Undiagnosed New Problem (count)")
    hdr("H1", "COPA: Acute w/ Systemic Symptoms (count)")
    hdr("I1", "COPA: Acute Complicated Injury (count)")
    hdr("J1", "COPA: Chronic Severe Exacerbation (count)")
    hdr("K1", "COPA: Threat to Life/Function (0 or 1)")
    hdr("L1", "COPA Level Override (leave blank to auto-derive)")
    hdr("M1", "DR: Prior External Notes (count)")
    hdr("N1", "DR: Review Test Results (count)")
    hdr("O1", "DR: Order Tests (count)")
    hdr("P1", "DR: Independent Historian (Y/N)")
    hdr("Q1", "DR: Independent Interpretation (Y/N)")
    hdr("R1", "DR: External Discussion (Y/N)")
    hdr("S1", "DR Level Override (leave blank to auto-derive)")
    hdr("T1", "Risk: Low (Y/N)")
    hdr("U1", "Risk: Prescription Drug Mgmt (Y/N)")
    hdr("V1", "Risk: Minor Surgery w/ Risk Factors (Y/N)")
    hdr("W1", "Risk: Elective Major - No Risk Factors (Y/N)")
    hdr("X1", "Risk: Hospitalization (Y/N)")
    hdr("Y1", "Risk: SDOH Limitation (Y/N)")
    hdr("Z1", "Risk: Drug Intensive Toxicity Monitoring (Y/N)")
    hdr("AA1", "Risk: Elective Major w/ Risk Factors (Y/N)")
    hdr("AB1", "Risk: Emergency Major Surgery (Y/N)")
    hdr("AC1", "Risk: Hospitalization/Escalation (Y/N)")
    hdr("AD1", "Risk: DNR / De-escalate (Y/N)")
    hdr("AE1", "Risk: Parenteral Controlled Substance (Y/N)")
    hdr("AF1", "Risk Level Override (leave blank to auto-derive)")
    hdr("AG1", "E/M Code")
    hdr("AH1", "E/M Modifier (e.g. 25)")
    hdr("AI1", "Patient Type (New / Established / NA)")
    hdr("AJ1", "Primary Dx Code")
    hdr("AK1", "Additional Dx 2")
    hdr("AL1", "Additional Dx 3")
    hdr("AM1", "Additional Dx 4")
    hdr("AN1", "Additional Dx 5")
    hdr("AO1", "Additional Dx 6")
    hdr("AP1", "Additional Dx 7")
    hdr("AQ1", "Additional Dx 8")
    hdr("AR1", "Procedure CPT 1")
    hdr("AS1", "Procedure CPT 1 Modifier")
    hdr("AT1", "Procedure CPT 2")
    hdr("AU1", "Procedure CPT 2 Modifier")
    hdr("AV1", "Procedure CPT 3")
    hdr("AW1", "Procedure CPT 3 Modifier")
    hdr("AX1", "Procedure CPT 4")
    hdr("AY1", "Procedure CPT 4 Modifier")
    hdr("AZ1", "Entered By")
    # Appended at the END on purpose: inserting mid-table would shift every
    # downstream parser index again (that bug cost us once already).
    hdr("BA1", "Level By (MDM / Time)")
    hdr("BB1", "Total Time (minutes)")

    # Sample row
    ws["A2"] = "EM001"
    ws["B2"] = 0
    ws["D2"] = 2
    ws["L2"] = ""
    ws["N2"] = 1
    ws["O2"] = 1
    ws["Q2"] = "Y"
    ws["U2"] = "Y"
    ws["AG2"] = "99214"
    ws["AH2"] = ""
    ws["AG2"] = "99214"
    ws["AI2"] = "Established"
    ws["BA2"] = "MDM"
    ws["AJ2"] = "E11.9"
    ws["AK2"] = "I10"
    ws["AL2"] = "Z79.4"
    ws["AZ2"] = "Dr. Smith"

    ws.freeze_panes = "B2"  # freeze column A (chart number) and header row

    ws.row_dimensions[1].height = 60
    for col in ws.columns:
        ws.column_dimensions[col[0].column_letter].width = 18

    buf = BytesIO()
    wb.save(buf)
    buf.seek(0)
    encoded = base64.b64encode(buf.read()).decode()
    return {"filename": "em_answer_key_template.xlsx", "content": encoded}
