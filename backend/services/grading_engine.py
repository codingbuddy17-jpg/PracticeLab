"""
Grading engine — exact Python port of GradingTool_Macros.bas (IP) and
OP_GradingTool_Macros.bas (OP). Scoring weights, normalization, overcoding
penalty, DRG auto-flag triggers, and feedback generation are all preserved.
"""
from dataclasses import dataclass, field
from typing import Optional


# ── Scoring weights ───────────────────────────────────────────────────────────

IP_WT_PDX = 20
IP_WT_SDX = 20
IP_WT_PCS = 20
IP_WT_DRG = 40
IP_PASS_THRESHOLD = 80

OP_WT_PDX = 25
OP_WT_SDX = 25
OP_WT_CPT = 50
OP_PASS_THRESHOLD = 90


# ── Input data structures ─────────────────────────────────────────────────────

@dataclass
class IPAnswerKey:
    pdx_code: str = ""
    pdx_poa: str = ""
    sdx: list[dict] = field(default_factory=list)   # [{code, poa, ccmcc}]
    pcs: list[dict] = field(default_factory=list)   # [{code}]


@dataclass
class OPAnswerKey:
    pdx_code: str = ""
    sdx: list[dict] = field(default_factory=list)   # [{code}]
    cpt: list[dict] = field(default_factory=list)   # [{code, modifier}]


@dataclass
class IPSubmission:
    pdx_code: str = ""
    pdx_poa: str = ""
    sdx: list[dict] = field(default_factory=list)   # [{code, poa}]
    pcs: list[dict] = field(default_factory=list)   # [{code}]


@dataclass
class OPSubmission:
    pdx_code: str = ""
    sdx: list[dict] = field(default_factory=list)   # [{code}]
    cpt: list[dict] = field(default_factory=list)   # [{code, modifier}]


@dataclass
class FeedbackRow:
    section: str      # PDx | SDx | PCS | CPT
    issue_type: str   # Missed | Wrong_Code | Wrong_POA | Wrong_Modifier | Over_coded
    ak_code: str = ""
    coder_code: str = ""
    detail: str = ""


@dataclass
class IPGradingResult:
    pdx_score: int = 0
    sdx_score: int = 0
    pcs_score: int = 0
    drg_flag: bool = False
    # drg_score set after trainer DRG review
    feedback: list[FeedbackRow] = field(default_factory=list)


@dataclass
class OPGradingResult:
    pdx_score: int = 0
    sdx_score: int = 0
    cpt_score: int = 0
    total_score: int = 0
    pass_fail: str = ""
    feedback: list[FeedbackRow] = field(default_factory=list)


# ── Normalization (matches VBA NormDx / NormPCS / NormCPT / NormMod) ─────────

def norm_dx(code: str) -> str:
    """Strip dots and spaces, uppercase. E11.9 → E119"""
    return code.replace(".", "").replace(" ", "").upper().strip()


def norm_pcs(code: str) -> str:
    """Strip spaces, O→0, I→1, uppercase. Handles common typos."""
    code = code.replace(" ", "").upper().strip()
    code = code.replace("O", "0").replace("I", "1")
    return code


def norm_cpt(code: str) -> str:
    return code.replace(" ", "").upper().strip()


def norm_mod(mod: str) -> str:
    """Strip dashes and spaces, uppercase. -59 → 59"""
    return mod.replace("-", "").replace(" ", "").upper().strip()


# ── Order-independent matching with overcoding penalty ────────────────────────

def _match_sdx_ip(ak_sdx: list[dict], cdr_sdx: list[dict]):
    """
    Returns (matched, extra, feedback_rows).
    Exact match = code AND poa both match.
    Wrong_POA = code matches, poa differs.
    """
    ak_used = [False] * len(ak_sdx)
    cdr_used = [False] * len(cdr_sdx)
    matched = 0
    feedback = []

    # Pass 1: exact matches (code + poa)
    for ci, cs in enumerate(cdr_sdx):
        c_code = norm_dx(cs.get("code", ""))
        c_poa = cs.get("poa", "").upper().strip()
        if not c_code:
            continue
        for ai, ak in enumerate(ak_sdx):
            if ak_used[ai]:
                continue
            if norm_dx(ak.get("code", "")) == c_code and ak.get("poa", "").upper().strip() == c_poa:
                matched += 1
                ak_used[ai] = True
                cdr_used[ci] = True
                break

    # Pass 2: wrong POA (code matches, poa differs) — feedback only
    for ci, cs in enumerate(cdr_sdx):
        if cdr_used[ci]:
            continue
        c_code = norm_dx(cs.get("code", ""))
        if not c_code:
            continue
        for ai, ak in enumerate(ak_sdx):
            if ak_used[ai]:
                continue
            if norm_dx(ak.get("code", "")) == c_code:
                feedback.append(FeedbackRow(
                    section="SDx", issue_type="Wrong_POA",
                    ak_code=ak.get("code", ""), coder_code=cs.get("code", ""),
                    detail=f"POA: {ak.get('poa','')} vs {cs.get('poa','')}",
                ))
                break

    # Pass 3: missed AK codes
    for ai, ak in enumerate(ak_sdx):
        if not ak_used[ai]:
            feedback.append(FeedbackRow(
                section="SDx", issue_type="Missed",
                ak_code=ak.get("code", ""), coder_code="",
            ))

    # Pass 4: overcoding
    ak_cnt = len([a for a in ak_sdx if norm_dx(a.get("code", ""))])
    cdr_cnt = len([c for c in cdr_sdx if norm_dx(c.get("code", ""))])
    extra = max(0, cdr_cnt - ak_cnt)
    if extra > 0:
        feedback.append(FeedbackRow(
            section="SDx", issue_type="Over_coded",
            detail=f"{extra} extra code(s) submitted",
        ))

    return matched, extra, feedback


def _match_pcs(ak_pcs: list[dict], cdr_pcs: list[dict]):
    """Order-independent PCS matching."""
    ak_used = [False] * len(ak_pcs)
    cdr_used = [False] * len(cdr_pcs)
    matched = 0
    feedback = []

    for ci, cs in enumerate(cdr_pcs):
        c_code = norm_pcs(cs.get("code", ""))
        if not c_code:
            continue
        for ai, ak in enumerate(ak_pcs):
            if ak_used[ai]:
                continue
            if norm_pcs(ak.get("code", "")) == c_code:
                matched += 1
                ak_used[ai] = True
                cdr_used[ci] = True
                break

    for ai, ak in enumerate(ak_pcs):
        if not ak_used[ai]:
            feedback.append(FeedbackRow(
                section="PCS", issue_type="Missed",
                ak_code=ak.get("code", ""), coder_code="",
            ))

    ak_cnt = len([a for a in ak_pcs if norm_pcs(a.get("code", ""))])
    cdr_cnt = len([c for c in cdr_pcs if norm_pcs(c.get("code", ""))])
    extra = max(0, cdr_cnt - ak_cnt)
    if extra > 0:
        feedback.append(FeedbackRow(
            section="PCS", issue_type="Over_coded",
            detail=f"{extra} extra code(s) submitted",
        ))

    return matched, extra, feedback


def _match_sdx_op(ak_sdx: list[dict], cdr_sdx: list[dict]):
    """OP SDx — code only, no POA."""
    ak_used = [False] * len(ak_sdx)
    matched = 0
    feedback = []

    for cs in cdr_sdx:
        c_code = norm_dx(cs.get("code", ""))
        if not c_code:
            continue
        for ai, ak in enumerate(ak_sdx):
            if ak_used[ai]:
                continue
            if norm_dx(ak.get("code", "")) == c_code:
                matched += 1
                ak_used[ai] = True
                break

    for ai, ak in enumerate(ak_sdx):
        if not ak_used[ai]:
            feedback.append(FeedbackRow(
                section="SDx", issue_type="Missed",
                ak_code=ak.get("code", ""), coder_code="",
            ))

    ak_cnt = len([a for a in ak_sdx if norm_dx(a.get("code", ""))])
    cdr_cnt = len([c for c in cdr_sdx if norm_dx(c.get("code", ""))])
    extra = max(0, cdr_cnt - ak_cnt)
    if extra > 0:
        feedback.append(FeedbackRow(
            section="SDx", issue_type="Over_coded",
            detail=f"{extra} extra code(s) submitted",
        ))

    return matched, extra, feedback


def _match_cpt(ak_cpt: list[dict], cdr_cpt: list[dict]):
    """CPT: code + modifier pair must match."""
    ak_used = [False] * len(ak_cpt)
    cdr_used = [False] * len(cdr_cpt)
    matched = 0
    feedback = []

    for ci, cs in enumerate(cdr_cpt):
        c_code = norm_cpt(cs.get("code", ""))
        c_mod = norm_mod(cs.get("modifier", ""))
        if not c_code:
            continue
        for ai, ak in enumerate(ak_cpt):
            if ak_used[ai]:
                continue
            if norm_cpt(ak.get("code", "")) == c_code and norm_mod(ak.get("modifier", "")) == c_mod:
                matched += 1
                ak_used[ai] = True
                cdr_used[ci] = True
                break

    # Wrong modifier feedback
    for ci, cs in enumerate(cdr_cpt):
        if cdr_used[ci]:
            continue
        c_code = norm_cpt(cs.get("code", ""))
        if not c_code:
            continue
        for ai, ak in enumerate(ak_cpt):
            if ak_used[ai]:
                continue
            if norm_cpt(ak.get("code", "")) == c_code:
                feedback.append(FeedbackRow(
                    section="CPT", issue_type="Wrong_Modifier",
                    ak_code=ak.get("code", ""), coder_code=cs.get("code", ""),
                    detail=f"Modifier: {ak.get('modifier','')} vs {cs.get('modifier','')}",
                ))
                break

    for ai, ak in enumerate(ak_cpt):
        if not ak_used[ai]:
            feedback.append(FeedbackRow(
                section="CPT", issue_type="Missed",
                ak_code=ak.get("code", ""), coder_code="",
            ))

    ak_cnt = len([a for a in ak_cpt if norm_cpt(a.get("code", ""))])
    cdr_cnt = len([c for c in cdr_cpt if norm_cpt(c.get("code", ""))])
    extra = max(0, cdr_cnt - ak_cnt)
    if extra > 0:
        feedback.append(FeedbackRow(
            section="CPT", issue_type="Over_coded",
            detail=f"{extra} extra code(s) submitted",
        ))

    return matched, extra, feedback


# ── DRG auto-flag (6 triggers — any one flags the row) ───────────────────────

def _drg_flag(ak: IPAnswerKey, sub: IPSubmission, pdx_ok: bool,
              pcs_matched: int, pcs_extra: int, sdx_matched: int) -> bool:
    # Trigger 1: PDx mismatch
    if not pdx_ok:
        return True

    # Trigger 2: any CC/MCC SDx from AK missing from coder
    ak_ccmcc = {norm_dx(s["code"]) for s in ak.sdx
                if s.get("ccmcc", "").upper() in ("CC", "MCC") and norm_dx(s.get("code", ""))}
    cdr_codes = {norm_dx(s.get("code", "")) for s in sub.sdx if norm_dx(s.get("code", ""))}
    if ak_ccmcc and not ak_ccmcc.issubset(cdr_codes):
        return True

    # Trigger 3: PCS under-coded
    ak_pcs_cnt = len([p for p in ak.pcs if norm_pcs(p.get("code", ""))])
    if pcs_matched < ak_pcs_cnt:
        return True

    # Trigger 4: PCS over-coded
    if pcs_extra > 0:
        return True

    # Trigger 5: spurious SDx (AK has none, coder added)
    ak_sdx_cnt = len([s for s in ak.sdx if norm_dx(s.get("code", ""))])
    cdr_sdx_cnt = len([s for s in sub.sdx if norm_dx(s.get("code", ""))])
    if ak_sdx_cnt == 0 and cdr_sdx_cnt > 0:
        return True

    # Trigger 6: spurious PCS (AK has none, coder added)
    cdr_pcs_cnt = len([p for p in sub.pcs if norm_pcs(p.get("code", ""))])
    if ak_pcs_cnt == 0 and cdr_pcs_cnt > 0:
        return True

    return False


# ── Main grading functions ────────────────────────────────────────────────────

def grade_ip(ak: IPAnswerKey, sub: IPSubmission) -> IPGradingResult:
    result = IPGradingResult()
    feedback = []

    # PDx
    pdx_ok = (norm_dx(sub.pdx_code) == norm_dx(ak.pdx_code) and
               sub.pdx_poa.upper().strip() == ak.pdx_poa.upper().strip())
    result.pdx_score = IP_WT_PDX if pdx_ok else 0
    if not pdx_ok:
        if norm_dx(sub.pdx_code) != norm_dx(ak.pdx_code):
            feedback.append(FeedbackRow("PDx", "Wrong_Code", ak.pdx_code, sub.pdx_code))
        else:
            feedback.append(FeedbackRow("PDx", "Wrong_POA", ak.pdx_code, sub.pdx_code,
                                        f"POA: {ak.pdx_poa} vs {sub.pdx_poa}"))

    # SDx
    ak_sdx_cnt = len([s for s in ak.sdx if norm_dx(s.get("code", ""))])
    cdr_sdx_cnt = len([s for s in sub.sdx if norm_dx(s.get("code", ""))])
    if ak_sdx_cnt > 0:
        sdx_matched, sdx_extra, sdx_fb = _match_sdx_ip(ak.sdx, sub.sdx)
        sdx_per = IP_WT_SDX / ak_sdx_cnt
        result.sdx_score = max(0, round((sdx_matched - sdx_extra) * sdx_per))
        feedback.extend(sdx_fb)
    elif cdr_sdx_cnt == 0:
        result.sdx_score = IP_WT_SDX  # both blank
        sdx_matched, sdx_extra = 0, 0
    else:
        result.sdx_score = 0  # spurious SDx
        sdx_matched, sdx_extra = 0, 0
        feedback.append(FeedbackRow("SDx", "Over_coded", detail="AK has no SDx but codes were submitted"))

    # PCS
    ak_pcs_cnt = len([p for p in ak.pcs if norm_pcs(p.get("code", ""))])
    cdr_pcs_cnt = len([p for p in sub.pcs if norm_pcs(p.get("code", ""))])
    if ak_pcs_cnt > 0:
        pcs_matched, pcs_extra, pcs_fb = _match_pcs(ak.pcs, sub.pcs)
        pcs_per = IP_WT_PCS / ak_pcs_cnt
        result.pcs_score = max(0, round((pcs_matched - pcs_extra) * pcs_per))
        feedback.extend(pcs_fb)
    elif cdr_pcs_cnt == 0:
        result.pcs_score = IP_WT_PCS  # both blank
        pcs_matched, pcs_extra = 0, 0
    else:
        result.pcs_score = 0  # spurious PCS
        pcs_matched, pcs_extra = 0, 0
        feedback.append(FeedbackRow("PCS", "Over_coded", detail="AK has no PCS but codes were submitted"))

    # DRG flag
    result.drg_flag = _drg_flag(ak, sub, pdx_ok, pcs_matched, pcs_extra,
                                 sdx_matched if ak_sdx_cnt > 0 else 0)
    result.feedback = feedback
    return result


def grade_op(ak: OPAnswerKey, sub: OPSubmission) -> OPGradingResult:
    result = OPGradingResult()
    feedback = []

    # PDx
    pdx_ok = norm_dx(sub.pdx_code) == norm_dx(ak.pdx_code)
    result.pdx_score = OP_WT_PDX if pdx_ok else 0
    if not pdx_ok:
        feedback.append(FeedbackRow("PDx", "Wrong_Code", ak.pdx_code, sub.pdx_code))

    # SDx
    ak_sdx_cnt = len([s for s in ak.sdx if norm_dx(s.get("code", ""))])
    cdr_sdx_cnt = len([s for s in sub.sdx if norm_dx(s.get("code", ""))])
    if ak_sdx_cnt > 0:
        sdx_matched, sdx_extra, sdx_fb = _match_sdx_op(ak.sdx, sub.sdx)
        sdx_per = OP_WT_SDX / ak_sdx_cnt
        result.sdx_score = max(0, round((sdx_matched - sdx_extra) * sdx_per))
        feedback.extend(sdx_fb)
    elif cdr_sdx_cnt == 0:
        result.sdx_score = OP_WT_SDX
    else:
        result.sdx_score = 0
        feedback.append(FeedbackRow("SDx", "Over_coded", detail="AK has no SDx but codes were submitted"))

    # CPT
    ak_cpt_cnt = len([c for c in ak.cpt if norm_cpt(c.get("code", ""))])
    cdr_cpt_cnt = len([c for c in sub.cpt if norm_cpt(c.get("code", ""))])
    if ak_cpt_cnt > 0:
        cpt_matched, cpt_extra, cpt_fb = _match_cpt(ak.cpt, sub.cpt)
        cpt_per = OP_WT_CPT / ak_cpt_cnt
        result.cpt_score = max(0, round((cpt_matched - cpt_extra) * cpt_per))
        feedback.extend(cpt_fb)
    elif cdr_cpt_cnt == 0:
        result.cpt_score = OP_WT_CPT
    else:
        result.cpt_score = 0
        feedback.append(FeedbackRow("CPT", "Over_coded", detail="AK has no CPT but codes were submitted"))

    result.total_score = result.pdx_score + result.sdx_score + result.cpt_score
    result.pass_fail = "PASS" if result.total_score >= OP_PASS_THRESHOLD else "FAIL"
    result.feedback = feedback
    return result


def finalize_ip_score(pdx_score: int, sdx_score: int, pcs_score: int,
                       drg_error: bool) -> tuple[int, str]:
    """Called after trainer DRG review. Returns (total, pass_fail)."""
    drg_score = 0 if drg_error else IP_WT_DRG
    total = pdx_score + sdx_score + pcs_score + drg_score
    pass_fail = "PASS" if total >= IP_PASS_THRESHOLD else "FAIL"
    return total, pass_fail, drg_score
