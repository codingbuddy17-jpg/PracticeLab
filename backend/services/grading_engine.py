"""
Grading engine — Python port of GradingTool_Macros.bas (IP) and
OP_GradingTool_Macros.bas (OP).

Weights and thresholds are passed in via ScoringCfg dataclass so the
admin can change them without touching code. Defaults match the original
VBA constants exactly.
"""
from dataclasses import dataclass, field
from typing import Optional


# ── Config dataclasses (populated from DB at grading time) ───────────────────

@dataclass
class IPScoringCfg:
    pdx_weight: int = 20
    sdx_weight: int = 20
    pcs_weight: int = 20
    drg_weight: int = 40
    pass_threshold: int = 80
    overcoding_penalty: bool = True
    # Which DRG auto-flag triggers are active
    drg_triggers: list[str] = field(default_factory=lambda: [
        "pdx_mismatch", "ccmcc_missing", "pcs_undercoded",
        "pcs_overcoded", "spurious_sdx", "spurious_pcs",
    ])


@dataclass
class OPScoringCfg:
    pdx_weight: int = 25
    sdx_weight: int = 25
    cpt_weight: int = 50
    pass_threshold: int = 90
    overcoding_penalty: bool = True


DEFAULT_IP_CFG = IPScoringCfg()
DEFAULT_OP_CFG = OPScoringCfg()


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
    sdx: list[dict] = field(default_factory=list)
    pcs: list[dict] = field(default_factory=list)


@dataclass
class OPSubmission:
    pdx_code: str = ""
    sdx: list[dict] = field(default_factory=list)
    cpt: list[dict] = field(default_factory=list)


@dataclass
class FeedbackRow:
    section: str
    issue_type: str
    ak_code: str = ""
    coder_code: str = ""
    detail: str = ""


@dataclass
class IPGradingResult:
    pdx_score: int = 0
    sdx_score: int = 0
    pcs_score: int = 0
    drg_flag: bool = False
    feedback: list[FeedbackRow] = field(default_factory=list)


@dataclass
class OPGradingResult:
    pdx_score: int = 0
    sdx_score: int = 0
    cpt_score: int = 0
    total_score: int = 0
    pass_fail: str = ""
    feedback: list[FeedbackRow] = field(default_factory=list)


# ── Normalization ─────────────────────────────────────────────────────────────

def norm_dx(code: str) -> str:
    return code.replace(".", "").replace(" ", "").upper().strip()


def norm_pcs(code: str) -> str:
    code = code.replace(" ", "").upper().strip()
    return code.replace("O", "0").replace("I", "1")


def norm_cpt(code: str) -> str:
    return code.replace(" ", "").upper().strip()


def norm_mod(mod: str) -> str:
    return mod.replace("-", "").replace(" ", "").upper().strip()


# ── Order-independent matching ────────────────────────────────────────────────

def _match_sdx_ip(ak_sdx: list[dict], cdr_sdx: list[dict], penalty: bool):
    ak_used = [False] * len(ak_sdx)
    cdr_used = [False] * len(cdr_sdx)
    matched = 0
    feedback = []

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
                feedback.append(FeedbackRow("SDx", "Wrong_POA",
                    ak.get("code", ""), cs.get("code", ""),
                    f"POA: {ak.get('poa','')} vs {cs.get('poa','')}"))
                break

    for ai, ak in enumerate(ak_sdx):
        if not ak_used[ai]:
            feedback.append(FeedbackRow("SDx", "Missed", ak.get("code", ""), ""))

    ak_cnt = len([a for a in ak_sdx if norm_dx(a.get("code", ""))])
    cdr_cnt = len([c for c in cdr_sdx if norm_dx(c.get("code", ""))])
    extra = max(0, cdr_cnt - ak_cnt) if penalty else 0
    if extra > 0:
        feedback.append(FeedbackRow("SDx", "Over_coded", detail=f"{extra} extra code(s) submitted"))

    return matched, extra, feedback


def _match_pcs(ak_pcs: list[dict], cdr_pcs: list[dict], penalty: bool):
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
            feedback.append(FeedbackRow("PCS", "Missed", ak.get("code", ""), ""))

    ak_cnt = len([a for a in ak_pcs if norm_pcs(a.get("code", ""))])
    cdr_cnt = len([c for c in cdr_pcs if norm_pcs(c.get("code", ""))])
    extra = max(0, cdr_cnt - ak_cnt) if penalty else 0
    if extra > 0:
        feedback.append(FeedbackRow("PCS", "Over_coded", detail=f"{extra} extra code(s) submitted"))

    return matched, extra, feedback


def _match_sdx_op(ak_sdx: list[dict], cdr_sdx: list[dict], penalty: bool):
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
            feedback.append(FeedbackRow("SDx", "Missed", ak.get("code", ""), ""))

    ak_cnt = len([a for a in ak_sdx if norm_dx(a.get("code", ""))])
    cdr_cnt = len([c for c in cdr_sdx if norm_dx(c.get("code", ""))])
    extra = max(0, cdr_cnt - ak_cnt) if penalty else 0
    if extra > 0:
        feedback.append(FeedbackRow("SDx", "Over_coded", detail=f"{extra} extra code(s) submitted"))

    return matched, extra, feedback


def _match_cpt(ak_cpt: list[dict], cdr_cpt: list[dict], penalty: bool):
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
                feedback.append(FeedbackRow("CPT", "Wrong_Modifier",
                    ak.get("code", ""), cs.get("code", ""),
                    f"Modifier: {ak.get('modifier','')} vs {cs.get('modifier','')}"))
                break

    for ai, ak in enumerate(ak_cpt):
        if not ak_used[ai]:
            feedback.append(FeedbackRow("CPT", "Missed", ak.get("code", ""), ""))

    ak_cnt = len([a for a in ak_cpt if norm_cpt(a.get("code", ""))])
    cdr_cnt = len([c for c in cdr_cpt if norm_cpt(c.get("code", ""))])
    extra = max(0, cdr_cnt - ak_cnt) if penalty else 0
    if extra > 0:
        feedback.append(FeedbackRow("CPT", "Over_coded", detail=f"{extra} extra code(s) submitted"))

    return matched, extra, feedback


# ── DRG auto-flag ─────────────────────────────────────────────────────────────

def _drg_flag(ak: IPAnswerKey, sub: IPSubmission, pdx_ok: bool,
              pcs_matched: int, pcs_extra: int, triggers: list[str]) -> bool:
    if "pdx_mismatch" in triggers and not pdx_ok:
        return True

    if "ccmcc_missing" in triggers:
        ak_ccmcc = {norm_dx(s["code"]) for s in ak.sdx
                    if s.get("ccmcc", "").upper() in ("CC", "MCC") and norm_dx(s.get("code", ""))}
        cdr_codes = {norm_dx(s.get("code", "")) for s in sub.sdx if norm_dx(s.get("code", ""))}
        if ak_ccmcc and not ak_ccmcc.issubset(cdr_codes):
            return True

    ak_pcs_cnt = len([p for p in ak.pcs if norm_pcs(p.get("code", ""))])
    cdr_pcs_cnt = len([p for p in sub.pcs if norm_pcs(p.get("code", ""))])

    if "pcs_undercoded" in triggers and pcs_matched < ak_pcs_cnt:
        return True
    if "pcs_overcoded" in triggers and pcs_extra > 0:
        return True

    ak_sdx_cnt = len([s for s in ak.sdx if norm_dx(s.get("code", ""))])
    cdr_sdx_cnt = len([s for s in sub.sdx if norm_dx(s.get("code", ""))])
    if "spurious_sdx" in triggers and ak_sdx_cnt == 0 and cdr_sdx_cnt > 0:
        return True
    if "spurious_pcs" in triggers and ak_pcs_cnt == 0 and cdr_pcs_cnt > 0:
        return True

    return False


# ── Main grading functions ────────────────────────────────────────────────────

def grade_ip(ak: IPAnswerKey, sub: IPSubmission,
             cfg: IPScoringCfg = DEFAULT_IP_CFG) -> IPGradingResult:
    result = IPGradingResult()
    feedback = []
    penalty = cfg.overcoding_penalty

    # PDx
    pdx_ok = (norm_dx(sub.pdx_code) == norm_dx(ak.pdx_code) and
               sub.pdx_poa.upper().strip() == ak.pdx_poa.upper().strip())
    result.pdx_score = cfg.pdx_weight if pdx_ok else 0
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
        sdx_matched, sdx_extra, sdx_fb = _match_sdx_ip(ak.sdx, sub.sdx, penalty)
        sdx_per = cfg.sdx_weight / ak_sdx_cnt
        result.sdx_score = max(0, round((sdx_matched - sdx_extra) * sdx_per))
        feedback.extend(sdx_fb)
    elif cdr_sdx_cnt == 0:
        result.sdx_score = cfg.sdx_weight
        sdx_matched = sdx_extra = 0
    else:
        result.sdx_score = 0
        sdx_matched = sdx_extra = 0
        feedback.append(FeedbackRow("SDx", "Over_coded", detail="AK has no SDx but codes were submitted"))

    # PCS
    ak_pcs_cnt = len([p for p in ak.pcs if norm_pcs(p.get("code", ""))])
    cdr_pcs_cnt = len([p for p in sub.pcs if norm_pcs(p.get("code", ""))])
    if ak_pcs_cnt > 0:
        pcs_matched, pcs_extra, pcs_fb = _match_pcs(ak.pcs, sub.pcs, penalty)
        pcs_per = cfg.pcs_weight / ak_pcs_cnt
        result.pcs_score = max(0, round((pcs_matched - pcs_extra) * pcs_per))
        feedback.extend(pcs_fb)
    elif cdr_pcs_cnt == 0:
        result.pcs_score = cfg.pcs_weight
        pcs_matched = pcs_extra = 0
    else:
        result.pcs_score = 0
        pcs_matched = pcs_extra = 0
        feedback.append(FeedbackRow("PCS", "Over_coded", detail="AK has no PCS but codes were submitted"))

    result.drg_flag = _drg_flag(ak, sub, pdx_ok, pcs_matched, pcs_extra, cfg.drg_triggers)
    result.feedback = feedback
    return result


def grade_op(ak: OPAnswerKey, sub: OPSubmission,
             cfg: OPScoringCfg = DEFAULT_OP_CFG) -> OPGradingResult:
    result = OPGradingResult()
    feedback = []
    penalty = cfg.overcoding_penalty

    pdx_ok = norm_dx(sub.pdx_code) == norm_dx(ak.pdx_code)
    result.pdx_score = cfg.pdx_weight if pdx_ok else 0
    if not pdx_ok:
        feedback.append(FeedbackRow("PDx", "Wrong_Code", ak.pdx_code, sub.pdx_code))

    ak_sdx_cnt = len([s for s in ak.sdx if norm_dx(s.get("code", ""))])
    cdr_sdx_cnt = len([s for s in sub.sdx if norm_dx(s.get("code", ""))])
    if ak_sdx_cnt > 0:
        sdx_matched, sdx_extra, sdx_fb = _match_sdx_op(ak.sdx, sub.sdx, penalty)
        sdx_per = cfg.sdx_weight / ak_sdx_cnt
        result.sdx_score = max(0, round((sdx_matched - sdx_extra) * sdx_per))
        feedback.extend(sdx_fb)
    elif cdr_sdx_cnt == 0:
        result.sdx_score = cfg.sdx_weight
    else:
        result.sdx_score = 0
        feedback.append(FeedbackRow("SDx", "Over_coded", detail="AK has no SDx but codes were submitted"))

    ak_cpt_cnt = len([c for c in ak.cpt if norm_cpt(c.get("code", ""))])
    cdr_cpt_cnt = len([c for c in sub.cpt if norm_cpt(c.get("code", ""))])
    if ak_cpt_cnt > 0:
        cpt_matched, cpt_extra, cpt_fb = _match_cpt(ak.cpt, sub.cpt, penalty)
        cpt_per = cfg.cpt_weight / ak_cpt_cnt
        result.cpt_score = max(0, round((cpt_matched - cpt_extra) * cpt_per))
        feedback.extend(cpt_fb)
    elif cdr_cpt_cnt == 0:
        result.cpt_score = cfg.cpt_weight
    else:
        result.cpt_score = 0
        feedback.append(FeedbackRow("CPT", "Over_coded", detail="AK has no CPT but codes were submitted"))

    result.total_score = result.pdx_score + result.sdx_score + result.cpt_score
    result.pass_fail = "PASS" if result.total_score >= cfg.pass_threshold else "FAIL"
    result.feedback = feedback
    return result


def finalize_ip_score(pdx_score: int, sdx_score: int, pcs_score: int,
                       drg_error: bool, drg_weight: int = 40,
                       pass_threshold: int = 80) -> tuple[int, str, int]:
    drg_score = 0 if drg_error else drg_weight
    total = pdx_score + sdx_score + pcs_score + drg_score
    pass_fail = "PASS" if total >= pass_threshold else "FAIL"
    return total, pass_fail, drg_score


def cfg_from_db(db_row) -> "IPScoringCfg | OPScoringCfg":
    """Convert a ScoringConfig DB row to the appropriate config dataclass."""
    if db_row.specialty_type == "IP":
        return IPScoringCfg(
            pdx_weight=db_row.pdx_weight,
            sdx_weight=db_row.sdx_weight,
            pcs_weight=db_row.pcs_weight or 20,
            drg_weight=db_row.drg_weight or 40,
            pass_threshold=db_row.pass_threshold,
            overcoding_penalty=db_row.overcoding_penalty,
            drg_triggers=db_row.drg_triggers or [],
        )
    return OPScoringCfg(
        pdx_weight=db_row.pdx_weight,
        sdx_weight=db_row.sdx_weight,
        cpt_weight=db_row.cpt_weight or 50,
        pass_threshold=db_row.pass_threshold,
        overcoding_penalty=db_row.overcoding_penalty,
    )
