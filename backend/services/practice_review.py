"""
The post-submit review of one practice chart: what was right as well as wrong.

Grading writes `feedback`, which lists what LOST points. A reviewer reading only
that cannot see what the coder got right, so cannot tell a careful coder who
slipped once from one who guessed — and the E/M reasoning score (6.7 of 10)
reads as arithmetic nobody can reproduce, because the elements behind it are
not shown at all.

This module builds the full side-by-side once, section by section, and both the
review screens and the Excel export render it. One builder, so the screen and
the spreadsheet cannot disagree.

It DESCRIBES the grading; it never re-scores. Points come from what grading
stored. Comparisons here mirror the grader's own rules (codes compared without
dots or case; E/M diagnoses as a set, not a sequence) so a row never says
"wrong" where the score said right.

Shape, per chart:

    {"sections": [ {"key", "title", "group", "points", "max_points", "note",
                    "rows": [{"item", "key", "coded", "status", "note"}]} ],
     "summary": {"correct": n, "missed": n, "extra": n, "different": n}}

status is one of: correct · missed (in the key, not coded) · extra (coded, not
in the key) · different (both present, a detail differs) · order (right code,
different position — not scored) · info (context, not judged).
"""
import io
import json
import re
from typing import Dict, List, Optional

from services.grading_engine import norm_units

# em_grading lives in routers/ and that package imports this module's callers,
# so it is imported inside the functions that need it — the convention
# audit_mutation and excel_service already follow.


# ── Element labels — the wording on the coder's E/M form ─────────────────────
#
# A test asserts every field in the grader's three lists has a label here, so a
# new element cannot be scored and then silently left out of the review.
ELEMENT_LABELS: Dict[str, str] = {
    # COPA
    "copa_self_limited": "Self-limited / minor (Minimal)",
    "copa_stable_chronic": "Stable, chronic illness (Low)",
    "copa_stable_acute": "Stable, acute illness (Low)",
    "copa_acute_uncomplicated": "Acute, uncomplicated illness/injury (Low)",
    "copa_chronic_exacerbation": "Chronic illness with exacerbation (Moderate)",
    "copa_undiagnosed_new": "Undiagnosed new problem (Moderate)",
    "copa_acute_systemic": "Acute illness with systemic symptoms (Moderate)",
    "copa_acute_complicated_injury": "Acute, complicated injury (Moderate)",
    "copa_chronic_severe": "Chronic illness, severe exacerbation (High)",
    "copa_threat_to_life": "Threat to life or bodily function (High)",
    # Data Review — the first three are COUNTS, the rest yes/no
    "dr_order_tests": "Tests ordered (count)",
    "dr_review_test_results": "Test results reviewed (count)",
    "dr_prior_external_notes": "Prior external notes reviewed (count)",
    "dr_independent_historian": "Independent historian",
    "dr_independent_interpretation": "Category 2 — Independent interpretation of test results",
    "dr_external_discussion": "Category 3 — Discussion with treating/consulting provider",
    # Risk
    "risk_low": "Minor/OTC medications; lab tests; X-rays; limited ultrasound (Low)",
    "risk_prescription_drug_mgmt": "Prescription drug management (Moderate)",
    "risk_minor_surgery_with_factors": "Minor surgery with identified risk factors (Moderate)",
    "risk_elective_major_no_factors": "Elective major surgery without identified risk factors (Moderate)",
    "risk_hospitalization": "Decision regarding hospitalization (Moderate)",
    "risk_sdoh": "Social determinants of health (Moderate)",
    "risk_drug_intensive_monitoring": "Drug therapy requiring intensive monitoring for toxicity (High)",
    "risk_elective_major_with_factors": "Elective major surgery with identified risk factors (High)",
    "risk_emergency_major_surgery": "Emergency major surgery (High)",
    "risk_hospitalization_escalation": "Hospitalization or escalation of care (High)",
    "risk_dnr_deescalate": "Decision not to resuscitate or de-escalate care (High)",
    "risk_parenteral_controlled": "Parenteral controlled substances (High)",
}
COUNT_FIELDS = {"dr_order_tests", "dr_review_test_results", "dr_prior_external_notes"}

STATUS_LABELS = {
    "correct": "Correct", "missed": "Missed", "extra": "Extra (not in key)",
    "different": "Differs", "order": "Order only", "info": "",
}


def is_em_specialty(specialty) -> bool:
    """E/M and ED Profee are graded on the E/M path (em_answer_keys)."""
    s = str(specialty or "").upper()
    return "E/M" in s or "PROFEE" in s.replace(" ", "").replace("_", "")


def is_ed_rubric_specialty(specialty) -> bool:
    """Edits and Denials — free-text responses, scored by a trainer rubric."""
    s = str(specialty or "").upper()
    return "EDIT" in s or "DENIAL" in s


# ── small helpers ─────────────────────────────────────────────────────────────

def _norm(code) -> str:
    return str(code or "").strip().upper().replace(".", "")


def _code_of(item) -> str:
    if isinstance(item, dict):
        return str(item.get("code") or "").strip()
    return str(item or "").strip()


def _codes(lst) -> List[str]:
    if isinstance(lst, str):
        try:
            lst = json.loads(lst)
        except ValueError:
            lst = []
    return [c for c in (_code_of(x) for x in (lst or [])) if c]


def _row(item, key, coded, status, note="") -> dict:
    return {"item": item, "key": key or "", "coded": coded or "",
            "status": status, "note": note}


def _set_rows(item_label: str, key_items: list, coded_items: list,
              detail=None) -> List[dict]:
    """
    Compare two code lists as multisets: each key code pairs with the first
    unused coded code that matches. `detail(k, c)` may return a note when a
    paired line differs in something other than the code (POA, modifier...).
    """
    rows = []
    used = [False] * len(coded_items)
    for k in key_items:
        kc = _norm(_code_of(k))
        hit = None
        for i, c in enumerate(coded_items):
            if not used[i] and _norm(_code_of(c)) == kc:
                hit = i
                break
        if hit is None:
            rows.append(_row(item_label, _display(k), "", "missed"))
            continue
        used[hit] = True
        c = coded_items[hit]
        note = detail(k, c) if detail else ""
        rows.append(_row(item_label, _display(k), _display(c),
                         "different" if note else "correct", note))
    for i, c in enumerate(coded_items):
        if not used[i] and _code_of(c):
            rows.append(_row(item_label, "", _display(c), "extra"))
    return rows


def _display(item) -> str:
    """A code line as a person reads it: code, then modifier/units/POA."""
    if not isinstance(item, dict):
        return _code_of(item)
    bits = [_code_of(item)]
    if item.get("poa"):
        bits.append("POA " + str(item["poa"]))
    if item.get("modifier"):
        bits.append("mod " + str(item["modifier"]))
    units = item.get("units")
    if units not in (None, "", 1, "1"):
        bits.append("x" + str(units))
    ptrs = item.get("pointers")
    if ptrs:
        bits.append("ptr " + ",".join(str(p) for p in ptrs))
    return "  ".join(b for b in bits if b)


def _poa_note(k, c) -> str:
    kp = str((k or {}).get("poa") or "").strip().upper() if isinstance(k, dict) else ""
    cp = str((c or {}).get("poa") or "").strip().upper() if isinstance(c, dict) else ""
    if kp and kp != cp:
        return "POA: key %s, coded %s" % (kp, cp or "(none)")
    return ""


def _cpt_note(k, c) -> str:
    if not (isinstance(k, dict) and isinstance(c, dict)):
        return ""
    notes = []
    km = str(k.get("modifier") or "").strip().upper()
    cm = str(c.get("modifier") or "").strip().upper()
    if km != cm:
        notes.append("Modifier: key %s, coded %s" % (km or "(none)", cm or "(none)"))
    # Units are judged only where the key states them — the grader's rule.
    if k.get("units") not in (None, ""):
        if norm_units(k.get("units")) != norm_units(c.get("units")):
            notes.append("Units: key %s, coded %s" % (
                norm_units(k.get("units")), norm_units(c.get("units"))))
    return "; ".join(notes)


def _section(key, title, group, rows, points=None, max_points=None, note=None):
    return {"key": key, "title": title, "group": group, "rows": rows,
            "points": points, "max_points": max_points, "note": note}


_PTS = re.compile(r"(-?[\d.]+)\s*(?:/\s*([\d.]+))?\s*pts")


def _fb_points(feedback: list, prefix: str):
    """(earned, out_of) from a stored E/M feedback line such as 'Dx: 11.7/23.3 pts'."""
    for f in feedback or []:
        issue = str(f.get("issue") or "")
        if issue.strip().upper().startswith(prefix.upper()):
            m = _PTS.search(issue)
            if m:
                return float(m.group(1)), (float(m.group(2)) if m.group(2) else None)
    return None, None


def _fb_row(feedback: list, prefix: str) -> Optional[dict]:
    for f in feedback or []:
        if str(f.get("issue") or "").strip().upper().startswith(prefix.upper()):
            return f
    return None


def _summarise(sections: List[dict]) -> dict:
    out = {"correct": 0, "missed": 0, "extra": 0, "different": 0}
    for sec in sections:
        for r in sec["rows"]:
            st = r["status"]
            if st in out:
                out[st] += 1
    return out


# ── IP / OP / Surgery / ED Facility ───────────────────────────────────────────

def _code_sections(r: dict) -> List[dict]:
    sections = []
    pdx_k, pdx_c = (r.get("pdx_answer_key") or ""), (r.get("pdx_submitted") or "")
    if pdx_k or pdx_c:
        if pdx_k and pdx_c:
            st = "correct" if _norm(pdx_k) == _norm(pdx_c) else "different"
        else:
            st = "missed" if pdx_k else "extra"
        sections.append(_section("pdx", "Principal Diagnosis", "Coding",
                                 [_row("PDx", pdx_k, pdx_c, st)]))

    sdx_k, sdx_c = r.get("sdx_answer_key") or [], r.get("sdx_submitted") or []
    if _codes(sdx_k) or _codes(sdx_c):
        sections.append(_section("sdx", "Secondary Diagnoses", "Coding",
                                 _set_rows("SDx", sdx_k, sdx_c, _poa_note)))

    pcs_k, pcs_c = r.get("pcs_answer_key") or [], r.get("pcs_submitted") or []
    if _codes(pcs_k) or _codes(pcs_c):
        sections.append(_section("pcs", "Procedures (ICD-10-PCS)", "Coding",
                                 _set_rows("PCS", pcs_k, pcs_c)))

    cpt_k, cpt_c = r.get("cpt_answer_key") or [], r.get("cpt_submitted") or []
    if _codes(cpt_k) or _codes(cpt_c):
        sections.append(_section("cpt", "CPT / HCPCS", "Coding",
                                 _set_rows("CPT", cpt_k, cpt_c, _cpt_note)))
    return sections


def _ed_rubric_sections(r: dict) -> List[dict]:
    scored = bool(r.get("ed_scored"))
    items = [
        ("Review", r.get("ed_review"), r.get("ed_review_pass")),
        ("Research", r.get("ed_research"),
         None if not scored else all(bool(r.get(k)) for k in (
             "ed_research_coding_pass", "ed_research_payer_pass", "ed_research_nuances_pass"))),
        ("Resolution", r.get("ed_resolution"), r.get("ed_resolution_pass")),
        ("Final Rationale", r.get("ed_rationale"), None),
    ]
    rows = []
    for label, text, passed in items:
        if not scored or passed is None:
            st = "info"
        else:
            st = "correct" if passed else "missed"
        rows.append(_row(label, "", text or "(not answered)", st))
    note = None if scored else "Awaiting trainer rubric scoring."
    if scored and r.get("ed_rationale_tier"):
        note = "Rationale rated: %s" % str(r["ed_rationale_tier"]).replace("_", " ")
    return [_section("ed", "Responses", "Coding", rows, note=note)]


# ── E/M and ED Profee ─────────────────────────────────────────────────────────

def _flag(v) -> int:
    try:
        return int(v or 0)
    except (TypeError, ValueError):
        return 1 if v else 0


def _mdm_section(key: str, title: str, fields: List[str], ak: dict, em: dict,
                 fb_prefix: str, level_key: str, feedback: list,
                 max_points: Optional[float]) -> dict:
    """
    One MDM table, element by element — the rows that explain the points.

    The grader awards (key elements matched ÷ key elements) × weight, counting
    only elements the key ticked; an element the coder adds that the key lacks
    costs nothing. The note says exactly that, with the numbers.
    """
    rows = []
    expected = matched = 0
    for f in fields:
        kv, cv = _flag(ak.get(f)), _flag(em.get(f))
        if not kv and not cv:
            continue
        label = ELEMENT_LABELS.get(f, f)
        shown = (lambda v: str(v) if v else "") if f in COUNT_FIELDS else (lambda v: "Yes" if v else "")
        if kv:
            expected += 1
            if cv == kv:
                matched += 1
                st, note = "correct", ""
            elif cv:
                st, note = "different", "Count must match the key exactly"
            else:
                st, note = "missed", ""
        else:
            st, note = "extra", "Not penalised"
        rows.append(_row(label, shown(kv), shown(cv), st, note))

    fb = _fb_row(feedback, fb_prefix)
    ak_level = (fb or {}).get("ak_code") or ak.get(level_key) or ""
    coded_level = (fb or {}).get("coder_code") or ""
    if ak_level or coded_level:
        lvl_st = "correct" if ak_level and _norm(ak_level) == _norm(coded_level) else "different"
        rows.insert(0, _row("Level", ak_level, coded_level, lvl_st,
                            "Derived from the elements below"))

    earned, _ = _fb_points(feedback, fb_prefix)
    if expected:
        note = ("Matched %d of %d element%s the key expects. Points = %d/%d x %s"
                % (matched, expected, "" if expected == 1 else "s", matched, expected,
                   ("%g" % max_points) if max_points is not None else "weight"))
    else:
        note = "The key expects no elements here, so this table earns full credit."
    return _section(key, title, "Reasoning", rows, earned, max_points, note)


def _em_sections(r: dict, ak: Optional[dict], em: Optional[dict], cfg: Optional[dict]) -> List[dict]:
    from routers.practicelab_pkg.em_grading import (
        COPA_FIELDS, DR_FIELDS, RISK_FIELDS,
        applicable_weights, normalise_cpts, resolve_category, score_em_dx,
    )
    ak, em, feedback = ak or {}, em or {}, r.get("feedback") or []
    sections = []

    # E/M level
    rows = []
    k_code, c_code = ak.get("em_code") or "", em.get("em_code") or ""
    if k_code or c_code:
        rows.append(_row("E/M code", k_code, c_code,
                         "correct" if k_code and _norm(k_code) == _norm(c_code) else "different"))
    k_mod = str(ak.get("em_modifier") or "").strip().upper()
    c_mod = str(em.get("em_modifier") or "").strip().upper()
    if k_mod or c_mod:
        rows.append(_row("Modifier", k_mod, c_mod, "correct" if k_mod == c_mod else "different"))
    k_pt = str(ak.get("patient_type") or "").upper()
    c_pt = str(em.get("patient_type") or "").upper()
    if (k_pt and k_pt != "NA") or (c_pt and c_pt != "NA"):
        rows.append(_row("Patient type", k_pt, c_pt, "correct" if k_pt == c_pt else "different"))
    k_m = str(ak.get("level_method") or "MDM").upper()
    c_m = str(em.get("level_method") or "MDM").upper()
    rows.append(_row("Levelled by", k_m, c_m, "correct" if k_m == c_m else "different",
                     "" if k_m == c_m else "Reasoning points are not earned on the wrong route"))
    k_cc, c_cc = ak.get("critical_care_minutes"), em.get("critical_care_minutes")
    if k_cc not in (None, "") or c_cc not in (None, ""):
        rows.append(_row("Critical care minutes", str(k_cc or ""), str(c_cc or ""),
                         "correct" if str(k_cc or "").strip() == str(c_cc or "").strip() else "different"))
    pts, out = _fb_points(feedback, "E/M Level")
    sections.append(_section("em_level", "E/M Level", "Coding", rows, pts, out))

    # Diagnoses: one section carrying the one Dx score, broken into its two
    # parts — the primary (half, all or nothing, must be listed first) and the
    # secondaries (the other half, wherever listed). Built from score_em_dx,
    # the grader's own function, so the explanation is the rule that scored it.
    # Compared as the grader compares (no dots, upper case), displayed as typed.
    shown_k, shown_c = _codes(r.get("sdx_answer_key")), _codes(r.get("sdx_submitted"))
    dx_k, dx_c = [_norm(c) for c in shown_k], [_norm(c) for c in shown_c]
    dx_pts, dx_out = _fb_points(feedback, "Dx:")
    weight = dx_out if dx_out is not None else 0.0
    sc = score_em_dx(dx_k, dx_c, weight, bool((cfg or {}).get("overcoding_penalty", True)))
    dx_rows = []
    consumed = None
    if dx_k or dx_c:
        k1, c1 = (dx_k[0] if dx_k else ""), (dx_c[0] if dx_c else "")
        sk1, sc1 = (shown_k[0] if shown_k else ""), (shown_c[0] if shown_c else "")
        if k1 and c1 == k1:
            consumed = 0
            dx_rows.append(_row("Primary Dx", sk1, sc1, "correct"))
        elif k1:
            where = dx_c.index(k1) if k1 in dx_c else None
            if where is not None:
                consumed = where
                note = ("Coded at position %d, not first: no primary credit. "
                        "The primary must be listed first" % (where + 1))
            else:
                note = "Not coded"
            dx_rows.append(_row("Primary Dx", sk1, sc1, "different" if c1 else "missed", note))
    c_rest = [c for i, c in enumerate(shown_c) if i != consumed]
    dx_rows += _set_rows("Secondary Dx", shown_k[1:], c_rest)
    if dx_k:
        parts = ["Primary %.1f of %.1f pts (must be listed first)" % (sc["primary_pts"], sc["primary_max"])]
        if sc["sec_total"]:
            parts.append("Secondary %d of %d coded, %.1f of %.1f pts"
                         % (sc["sec_matched"], sc["sec_total"], sc["sec_pts"], sc["sec_max"]))
        if sc["over"]:
            parts.append("%d over-coded, -%.1f pts" % (sc["over"], sc["penalty"]))
        dx_note = " · ".join(parts)
        if dx_pts is not None and round(dx_pts, 1) != round(sc["score"], 1):
            # Graded before the primary rule existed; stored scores were left
            # as they were. Say so rather than show parts that do not add up.
            dx_note = ("Scored under the earlier rule, where diagnosis order did not count "
                       "(%.1f pts). Re-grade the session to apply the current rule: %s"
                       % (dx_pts, dx_note))
    else:
        dx_note = "The key lists no diagnoses, so this component earns full credit."
    sections.append(_section("dx", "Diagnoses", "Coding", dx_rows, dx_pts, dx_out, dx_note))

    # CPT / procedures
    cpt_k = normalise_cpts(r.get("cpt_answer_key") or [])
    cpt_c = normalise_cpts(r.get("cpt_submitted") or [])
    if cpt_k or cpt_c:
        pts, out = _fb_points(feedback, "CPT:")
        notes = [f["issue"] for f in feedback
                 if str(f.get("issue") or "").startswith("Dx pointers on CPT")]
        sections.append(_section("cpt", "CPT / Procedures", "Coding",
                                 _set_rows("CPT", cpt_k, cpt_c, _cpt_note), pts, out,
                                 "; ".join(notes) or None))

    # Reasoning
    category = resolve_category(ak.get("em_category"), ak.get("em_code"))
    weights = {}
    if cfg:
        weights = applicable_weights(cfg, category, bool(cpt_k), ak.get("level_method"))
    if k_m == "TIME":
        pts, _ = _fb_points(feedback, "Time supports")
        rows = [_row("Total time (minutes)", str(ak.get("total_time") or ""),
                     str(em.get("total_time") or ""), "info")]
        sections.append(_section("time", "Time", "Reasoning", rows, pts,
                                 weights.get("time"),
                                 "Levelled by time: full credit for the time route with time in band, "
                                 "half for the right route with time out of band."))
    elif "copa" in weights or (not cfg and _fb_row(feedback, "COPA")):
        if k_m != c_m:
            note = "Levelled by %s instead of %s — reasoning points not earned." % (c_m, k_m)
        else:
            note = None
        for key, title, fields, prefix, lvl in (
            ("copa", "Problems Addressed (COPA)", COPA_FIELDS, "COPA", "copa_level"),
            ("dr", "Data Reviewed and Analysed", DR_FIELDS, "Data Review", "dr_level"),
            ("risk", "Risk of Patient Management", RISK_FIELDS, "Risk", "risk_level"),
        ):
            sec = _mdm_section(key, title, fields, ak, em, prefix, lvl, feedback, weights.get(key))
            if note:
                sec["note"] = note
            sections.append(sec)
    else:
        sections.append(_section("mdm", "Medical Decision Making", "Reasoning", [], None, None,
                                 "Not assessed on MDM for this kind of visit; its weight "
                                 "is folded into the coding score."))
    return sections


# ── entry point ───────────────────────────────────────────────────────────────

def build_review(r: dict, ak: Optional[dict] = None, em_data: Optional[dict] = None,
                 cfg: Optional[dict] = None) -> dict:
    """Sections for one result row from _build_coder_results."""
    if is_em_specialty(r.get("specialty")):
        sections = _em_sections(r, ak, em_data, cfg)
    elif is_ed_rubric_specialty(r.get("specialty")):
        sections = _ed_rubric_sections(r)
    else:
        sections = _code_sections(r)
    return {"sections": sections, "summary": _summarise(sections)}


# ── Descriptions ──────────────────────────────────────────────────────────────

# Which code system each review section's codes belong to, in the spelling
# services/code_enrichment keys on. E/M level codes and CPT are AMA's and are
# never described; MDM, time and text sections carry no codes.
_DESCRIBE_SECTION = {"pdx": "PDx", "sdx": "SDx", "dx": "SDx", "pcs": "PCS", "cpt": "CPT"}


def _first_code(display: str) -> str:
    """The code at the front of a display string such as 'I10  POA Y'."""
    return (display or "").split("  ")[0].strip()


def describe_review(db, charts: List[dict]) -> None:
    """
    Add key_desc / coded_desc to every code row of every chart's review, in
    place: what each code MEANS beside what was expected. One lookup per code
    system for the whole session, not per row.

    Silent where nothing is known — CPT, an unloaded code set, a code not in
    the edition — so the row shows the code alone, as everywhere else.
    """
    from services.code_enrichment import enrich_codes, lookup

    targets = []
    for c in charts:
        for sec in ((c.get("review") or {}).get("sections") or []):
            section = _DESCRIBE_SECTION.get(sec.get("key"))
            if not section:
                continue
            for row in sec.get("rows") or []:
                targets.append((section, row))
    if not targets:
        return
    pairs = set()
    for section, row in targets:
        for code in (_first_code(row.get("key")), _first_code(row.get("coded"))):
            if code:
                pairs.add((section, code))
    try:
        enriched = enrich_codes(db, pairs)
    except Exception:  # noqa: BLE001 — descriptions are an aid, never a failure
        enriched = {}
    for section, row in targets:
        for field, col in (("key", "key_desc"), ("coded", "coded_desc")):
            info = lookup(enriched, section, _first_code(row.get(field))) if row.get(field) else None
            row[col] = (info or {}).get("description") or ""


# ── Excel ─────────────────────────────────────────────────────────────────────

def review_workbook(header: dict, charts: List[dict]) -> bytes:
    """
    Two sheets. Summary: one row per chart. Review: every compared line, one
    row each, filterable — so "show me everything this coder missed" is one
    click on the Result column rather than a read of the whole sheet.
    """
    from openpyxl import Workbook
    from openpyxl.styles import Alignment
    from services.excel_style import (CELL_BORDER, DIFFER_FILL, DIFFER_FONT,
                                      EXTRA_FILL, EXTRA_FONT, FAIL_FILL, FAIL_FONT,
                                      INFO_FILL, INFO_FONT, PASS_FILL, PASS_FONT,
                                      finish)

    status_style = {
        "correct": (PASS_FILL, PASS_FONT),
        "missed": (FAIL_FILL, FAIL_FONT),
        "extra": (EXTRA_FILL, EXTRA_FONT),
        "different": (DIFFER_FILL, DIFFER_FONT),
        "order": (INFO_FILL, INFO_FONT),
    }

    wb = Workbook()
    ws = wb.active
    ws.title = "Summary"
    ws.append(["Coder", "Specialty", "Submitted", "Chart", "Score %", "Result",
               "Correct", "Missed", "Extra", "Differs"])
    for c in charts:
        s = (c.get("review") or {}).get("summary") or {}
        ws.append([header.get("coder_name"), c.get("specialty") or header.get("specialty"),
                   header.get("submitted_at"), c.get("chart_number"), c.get("total_score"),
                   c.get("pass_fail"), s.get("correct", 0), s.get("missed", 0),
                   s.get("extra", 0), s.get("different", 0)])
        pf = ws.cell(row=ws.max_row, column=6)
        if pf.value in ("PASS", "FAIL"):
            pf.fill, pf.font = (PASS_FILL, PASS_FONT) if pf.value == "PASS" else (FAIL_FILL, FAIL_FONT)
    finish(ws)

    rv = wb.create_sheet("Review")
    rv.append(["Chart", "Score %", "Section", "Points", "Item", "Answer key",
               "Key description", "Coded", "Coded description", "Result", "Note"])
    for c in charts:
        for sec in (c.get("review") or {}).get("sections") or []:
            if sec.get("points") is None:
                pts = ""
            elif sec.get("max_points") is not None:
                pts = "%.1f / %.1f" % (sec["points"], sec["max_points"])
            else:
                pts = "%.1f" % sec["points"]
            rows = sec.get("rows") or []
            if not rows:
                rv.append([c.get("chart_number"), c.get("total_score"), sec["title"], pts,
                           "", "", "", "", "", "", sec.get("note") or ""])
                continue
            for i, row in enumerate(rows):
                note = row.get("note") or ""
                if i == 0 and sec.get("note"):
                    note = (sec["note"] + (" | " + note if note else ""))
                rv.append([c.get("chart_number"), c.get("total_score"), sec["title"],
                           pts if i == 0 else "", row["item"], row["key"],
                           row.get("key_desc") or "", row["coded"], row.get("coded_desc") or "",
                           STATUS_LABELS.get(row["status"], row["status"]), note])
                st = status_style.get(row["status"])
                if st:
                    cell = rv.cell(row=rv.max_row, column=10)
                    cell.fill, cell.font = st
    for row in rv.iter_rows(min_row=2):
        for cell in row:
            cell.border = CELL_BORDER
            cell.alignment = Alignment(vertical="top", wrap_text=cell.column in (7, 9, 11))
    finish(rv)
    for col in ("G", "I"):
        rv.column_dimensions[col].width = 40
    rv.column_dimensions["K"].width = 60

    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()
