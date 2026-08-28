"""
Grading engine — Python port of GradingTool_Macros.bas (IP) and
OP_GradingTool_Macros.bas (OP).

Weights and thresholds are passed in via ScoringCfg dataclass so the
admin can change them without touching code. Defaults match the original
VBA constants exactly.
"""
import re
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
    # Which DRG auto-flag triggers are active.
    #
    # Only PDx, CC/MCC and PCS errors can move the DRG, so only those warrant a
    # trainer decision. "spurious_sdx" is deliberately NOT a default: it fired
    # whenever the key had no secondary diagnoses and the coder added any, but a
    # secondary that is not a CC or MCC does not change the DRG. It also could
    # never have been accurate — coder submissions carry no CC/MCC flag, so a
    # code the coder invents cannot be classified without a CC/MCC reference
    # table the app does not have.
    drg_triggers: list[str] = field(default_factory=lambda: [
        "pdx_mismatch", "ccmcc_missing", "pcs_undercoded",
        "pcs_overcoded", "spurious_pcs",
    ])


@dataclass
class OPScoringCfg:
    pdx_weight: int = 25
    sdx_weight: int = 25
    cpt_weight: int = 50
    pass_threshold: int = 90
    overcoding_penalty: bool = True


@dataclass
class EDSinglePathCfg:
    """
    ED Single Path — facility and professional levels coded from one chart.

    Both levels carry real weight because getting one right and the other wrong
    is the characteristic single-path error, and the whole point of training it.
    """
    pdx_weight: int = 20
    sdx_weight: int = 20
    facility_level_weight: int = 20
    profee_level_weight: int = 20
    cpt_weight: int = 20
    pass_threshold: int = 90
    overcoding_penalty: bool = True


DEFAULT_IP_CFG = IPScoringCfg()
DEFAULT_OP_CFG = OPScoringCfg()
DEFAULT_EDSP_CFG = EDSinglePathCfg()


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
class EDSinglePathAnswerKey:
    pdx_code: str = ""
    sdx: list[dict] = field(default_factory=list)     # [{code}]
    cpt: list[dict] = field(default_factory=list)     # [{code, modifier, pointers}]
    facility_level: str = ""
    profee_level: str = ""


@dataclass
class EDSinglePathSubmission:
    pdx_code: str = ""
    sdx: list[dict] = field(default_factory=list)
    cpt: list[dict] = field(default_factory=list)
    facility_level: str = ""
    profee_level: str = ""


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

def _clean(code) -> str:
    """Convert any value to string, treating None/'None'/'' as empty."""
    if code is None:
        return ""
    s = str(code).strip()
    return "" if s.lower() == "none" else s


def norm_dx(code) -> str:
    return _clean(code).replace(".", "").replace(" ", "").upper()


def norm_poa(poa) -> str:
    """
    One POA value, however it was recorded.

    CMS writes the exempt indicator as "1"; every answer key here uses "E", and
    the coder dropdown offered "1" — so an exempt diagnosis could never match
    its own key, and the coder was marked wrong for entering the only value the
    form let them pick. The dropdowns now say E, and this keeps the submissions
    already stored under "1" grading correctly on a re-grade.
    """
    v = _clean(poa).upper().strip()
    return "E" if v == "1" else v


def norm_pcs(code) -> str:
    c = _clean(code).replace(" ", "").upper()
    return c.replace("O", "0").replace("I", "1")


def norm_cpt(code) -> str:
    return _clean(code).replace(" ", "").upper()


_MOD_SPLIT_RE = re.compile(r"[,;/\s]+")


def norm_mod(mod) -> str:
    """Normalize a modifier field. Supports multiple modifiers in one cell
    (e.g. '25,59', '59, 25', '25;59') by splitting on common separators,
    cleaning each token, and sorting — so the comparison is independent of
    entry order or which separator was used."""
    s = _clean(mod).upper()
    if not s:
        return ""
    tokens = [t.replace("-", "").strip() for t in _MOD_SPLIT_RE.split(s) if t.strip()]
    return ",".join(sorted(tokens))


_CPT_EMBEDDED_MOD_RE = re.compile(r"^([A-Z0-9]{5})-?([A-Z0-9]{2})$")


def resolve_cpt_modifier(code, modifier) -> tuple[str, str]:
    """Normalize a CPT code/modifier pair, recovering a modifier that was
    typed directly into the code cell (e.g. '99213-25' with modifier left
    blank) instead of its own column — otherwise the combined string never
    matches the answer key's code and gets misclassified as Missed."""
    code_s = norm_cpt(code)
    mod_s = norm_mod(modifier)
    if mod_s or not code_s:
        return code_s, mod_s
    m = _CPT_EMBEDDED_MOD_RE.match(code_s)
    if m:
        return m.group(1), m.group(2)
    return code_s, mod_s


def norm_units(raw) -> int:
    """
    Units on a CPT line, defaulting to 1.

    A blank cell means one unit — that is what a coder writing a single
    procedure leaves behind, and treating it as zero would fail every line
    nobody thought to annotate. Anything unreadable also falls back to 1 rather
    than raising: a stray character in a spreadsheet should not stop a chart
    being graded.
    """
    if raw is None or (isinstance(raw, str) and not raw.strip()):
        return 1
    try:
        n = int(float(str(raw).strip()))
    except (TypeError, ValueError):
        return 1
    return n if n >= 1 else 1


# ── Order-independent matching ────────────────────────────────────────────────

def _match_sdx_ip(ak_sdx: list[dict], cdr_sdx: list[dict], penalty: bool):
    ak_used = [False] * len(ak_sdx)
    cdr_used = [False] * len(cdr_sdx)
    matched = 0
    feedback = []

    for ci, cs in enumerate(cdr_sdx):
        c_code = norm_dx(cs.get("code", ""))
        c_poa = norm_poa(cs.get("poa", ""))
        if not c_code:
            continue
        for ai, ak in enumerate(ak_sdx):
            if ak_used[ai]:
                continue
            if norm_dx(ak.get("code", "")) == c_code and norm_poa(ak.get("poa", "")) == c_poa:
                matched += 1
                ak_used[ai] = True
                cdr_used[ci] = True
                break

    # Second pass: the code is right and the POA is not. Both sides must be
    # marked used. They were not, so every wrong-POA code was ALSO reported as
    # Missed by the loop below — a coder who got five codes right with the
    # wrong POA saw ten findings for five mistakes, five of them claiming a
    # code they had plainly submitted was absent. The score never used these
    # rows, so it was right all along; the feedback was telling a different
    # story from the mark.
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
                ak_used[ai] = True
                cdr_used[ci] = True
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


def claim_dx_list(pdx_code: str, sdx: list[dict]) -> list[str]:
    """
    The ordered diagnosis list a pointer letter indexes into.

    On a CMS-1500, Box 21 holds up to 12 diagnoses labelled A-L; Box 24E points
    at them by letter. Position 1 (A) is the principal diagnosis, then the
    secondaries in order.
    """
    out = [pdx_code or ""]
    out.extend((s or {}).get("code", "") for s in (sdx or []))
    return out[:12]


def pointer_index(token) -> Optional[int]:
    """
    A diagnosis pointer as a 0-based position, accepting either spelling.

    Coders here refer to diagnoses by NUMBER — Dx 1, Dx 2 — matching the order
    they are listed in, and that is what the app now shows and asks for. The
    CMS-1500 (02/12) prints letters A-L in Box 21, and earlier keys were
    entered that way, so letters are still read.

    Both are the same thing: a position in the diagnosis list. Storing the
    position rather than the spelling is what lets one key be entered as "1,2"
    and another as "A,B" without either being wrong.
    """
    t = str(token or "").strip().upper()
    if not t:
        return None
    if t.isdigit():
        n = int(t)
        return n - 1 if n >= 1 else None          # 1-based on the page
    if "A" <= t[0] <= "Z":
        return ord(t[0]) - ord("A")               # legacy letter form
    return None


def pointer_label(idx: int) -> str:
    """How a pointer position is written back out. Numeric, per the above."""
    return str(idx + 1)


# CMS-1500 Box 24E holds at most four diagnosis pointers per service line. A
# claim may carry twelve diagnoses (Box 21); the coder must choose the four
# that support medical necessity for THAT procedure. The first is primary.
MAX_POINTERS_PER_LINE = 4

# Box 21 holds twelve diagnoses, so no pointer can reference beyond that.
MAX_DIAGNOSES = 12


def canonical_pointers(raw) -> list:
    """
    The one place a pointer list is cleaned: canonical numeric strings, in
    order, capped at four.

    The cap lived in four separate slices — two UI parsers, the Excel reader
    and the E/M normaliser — which is three chances for a route to skip it. A
    key carrying five pointers is not merely untidy: it is a claim that could
    not be submitted, and grading a coder against it marks a correct four-
    pointer answer as incomplete.
    """
    out = []
    for p in (raw or []):
        idx = pointer_index(p)
        if idx is None or not (0 <= idx < MAX_DIAGNOSES):
            continue
        label = pointer_label(idx)
        if label not in out:                       # a repeat points nowhere new
            out.append(label)
    return out[:MAX_POINTERS_PER_LINE]


def pointer_display(pointers, dx_list: list) -> str:
    """Readable pointer list for trainer feedback — keeps the dotted code form."""
    out = []
    for p in (pointers or []):
        idx = pointer_index(p)
        if idx is not None and 0 <= idx < len(dx_list) and dx_list[idx]:
            out.append(f"{pointer_label(idx)}={dx_list[idx]}")
    return ", ".join(out) or "(none)"


def resolve_pointers(pointers, dx_list: list) -> set:
    """
    Turn pointers into the diagnosis codes they actually reference.

    Pointers are POSITIONAL, so the same pointer means different diagnoses if the
    coder ordered their Dx list differently from the answer key. Comparing
    pointers would mark correct work wrong — always compare resolved codes.
    """
    resolved = set()
    for p in (pointers or []):
        idx = pointer_index(p)
        if idx is not None and 0 <= idx < len(dx_list):
            code = norm_dx(dx_list[idx])
            if code:
                resolved.add(code)
    return resolved


def _match_cpt(ak_cpt: list[dict], cdr_cpt: list[dict], penalty: bool,
               ak_dx: Optional[list] = None, cdr_dx: Optional[list] = None,
               check_pointers: bool = False):
    ak_norm = [resolve_cpt_modifier(a.get("code", ""), a.get("modifier", "")) for a in ak_cpt]
    cdr_norm = [resolve_cpt_modifier(c.get("code", ""), c.get("modifier", "")) for c in cdr_cpt]

    ak_used = [False] * len(ak_cpt)
    cdr_used = [False] * len(cdr_cpt)
    matched = 0
    feedback = []

    for ci, (c_code, c_mod) in enumerate(cdr_norm):
        if not c_code:
            continue
        for ai, (a_code, a_mod) in enumerate(ak_norm):
            if ak_used[ai]:
                continue
            if a_code == c_code and a_mod == c_mod:
                # Code + modifier correct. Two things can still be wrong on the
                # line, and both are lesser mistakes than picking the wrong
                # procedure — the coder found it and then described it wrongly —
                # so each costs half the line rather than all of it.
                #
                # They do not stack: a line with the wrong pointers AND the
                # wrong units is still one line, and zeroing it would price a
                # described-badly line the same as a missed one.
                credit = 1.0
                if check_pointers:
                    ak_ptr = resolve_pointers(ak_cpt[ai].get("pointers"), ak_dx or [])
                    cdr_ptr = resolve_pointers(cdr_cpt[ci].get("pointers"), cdr_dx or [])
                    if ak_ptr and ak_ptr != cdr_ptr:
                        credit = 0.5
                        feedback.append(FeedbackRow(
                            "CPT", "Wrong_Pointer",
                            ak_cpt[ai].get("code", ""), cdr_cpt[ci].get("code", ""),
                            f"Dx pointers — key: {pointer_display(ak_cpt[ai].get('pointers'), ak_dx or [])}"
                            f"  |  coded: {pointer_display(cdr_cpt[ci].get('pointers'), cdr_dx or [])}"))

                # Units are graded only where the key states them, so keys
                # written before units existed grade exactly as they did.
                if "units" in ak_cpt[ai]:
                    ak_u = norm_units(ak_cpt[ai].get("units"))
                    cdr_u = norm_units(cdr_cpt[ci].get("units"))
                    if ak_u != cdr_u:
                        credit = min(credit, 0.5)
                        feedback.append(FeedbackRow(
                            "CPT", "Wrong_Units",
                            ak_cpt[ai].get("code", ""), cdr_cpt[ci].get("code", ""),
                            f"Units — key: {ak_u}  |  coded: {cdr_u}"))
                matched += credit
                ak_used[ai] = True
                cdr_used[ci] = True
                break

    for ci, (c_code, c_mod) in enumerate(cdr_norm):
        if cdr_used[ci] or not c_code:
            continue
        for ai, (a_code, a_mod) in enumerate(ak_norm):
            if ak_used[ai]:
                continue
            if a_code == c_code:
                feedback.append(FeedbackRow("CPT", "Wrong_Modifier",
                    ak_cpt[ai].get("code", ""), cdr_cpt[ci].get("code", ""),
                    f"Modifier: {a_mod or '(none)'} vs {c_mod or '(none)'}"))
                ak_used[ai] = True
                cdr_used[ci] = True
                break

    for ai, (a_code, _a_mod) in enumerate(ak_norm):
        if not ak_used[ai] and a_code:
            feedback.append(FeedbackRow("CPT", "Missed", ak_cpt[ai].get("code", ""), ""))

    ak_cnt = len([c for c, _ in ak_norm if c])
    cdr_cnt = len([c for c, _ in cdr_norm if c])
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

    # NOTE: no spurious-SDx trigger. Adding a secondary diagnosis that is not a
    # CC or MCC cannot change the DRG, so it needs no trainer decision — and a
    # coder-invented code carries no CC/MCC flag to test against anyway. Left
    # honourable only if an org explicitly re-enables it in scoring config.
    if "spurious_sdx" in triggers:
        ak_sdx_cnt = len([s for s in ak.sdx if norm_dx(s.get("code", ""))])
        cdr_sdx_cnt = len([s for s in sub.sdx if norm_dx(s.get("code", ""))])
        if ak_sdx_cnt == 0 and cdr_sdx_cnt > 0:
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
               norm_poa(sub.pdx_poa) == norm_poa(ak.pdx_poa))
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
             cfg: OPScoringCfg = DEFAULT_OP_CFG,
             check_pointers: bool = False) -> OPGradingResult:
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
        cpt_matched, cpt_extra, cpt_fb = _match_cpt(
            ak.cpt, sub.cpt, penalty,
            ak_dx=claim_dx_list(ak.pdx_code, ak.sdx),
            cdr_dx=claim_dx_list(sub.pdx_code, sub.sdx),
            check_pointers=check_pointers,
        )
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


# ── DPO accuracy layer ────────────────────────────────────────────────────────

@dataclass
class DPOSection:
    label: str
    opportunities: int
    defects: int

    @property
    def accuracy(self) -> Optional[float]:
        """Returns accuracy 0–100, or None when no opportunities exist (N/A)."""
        if self.opportunities == 0:
            return None
        return round(max(0.0, (1 - self.defects / self.opportunities)) * 100, 1)


@dataclass
class DPOResult:
    dx: DPOSection     # Diagnostic code accuracy (PDx + SDx codes)
    poa: DPOSection    # POA indicator accuracy (IP only; opportunities=0 for OP)
    proc: DPOSection   # PCS (IP) or CPT+Mod (OP)
    overall_accuracy: float


def compute_dpo_ip(ak: IPAnswerKey, sub: IPSubmission, overcoding_penalty: bool) -> DPOResult:
    """DPO supplementary scoring for IP charts. All accuracies expressed 0–100%."""
    # ── DX section: PDx code + SDx codes (POA excluded here) ─────────────────
    ak_sdx = [s for s in ak.sdx if norm_dx(s.get("code", ""))]
    cdr_sdx = [s for s in sub.sdx if norm_dx(s.get("code", ""))]

    dx_opp = 1 + len(ak_sdx)
    dx_defects = 0

    pdx_code_ok = norm_dx(sub.pdx_code) == norm_dx(ak.pdx_code)
    if not pdx_code_ok:
        dx_defects += 1

    # SDx code matching (order-independent, ignoring POA for this section)
    ak_sdx_used = [False] * len(ak_sdx)
    sdx_code_matched_idx: list[tuple[int, int]] = []  # (ak_idx, cdr_idx)
    for ci, cs in enumerate(cdr_sdx):
        c = norm_dx(cs.get("code", ""))
        for ai, a in enumerate(ak_sdx):
            if not ak_sdx_used[ai] and norm_dx(a.get("code", "")) == c:
                ak_sdx_used[ai] = True
                sdx_code_matched_idx.append((ai, ci))
                break

    sdx_missed = len(ak_sdx) - len(sdx_code_matched_idx)
    dx_defects += sdx_missed

    sdx_extra = max(0, len(cdr_sdx) - len(ak_sdx)) if overcoding_penalty else 0
    dx_defects += sdx_extra
    if overcoding_penalty and sdx_extra > 0:
        dx_opp += sdx_extra  # extra submissions create additional opportunities

    # ── POA section: PDx POA + POA on code-matched SDx ───────────────────────
    poa_opp = 0
    poa_defects = 0

    if pdx_code_ok:
        poa_opp += 1
        if norm_poa(sub.pdx_poa) != norm_poa(ak.pdx_poa):
            poa_defects += 1

    cdr_sdx_used_set = {ci for _, ci in sdx_code_matched_idx}
    for ai, ci in sdx_code_matched_idx:
        poa_opp += 1
        if norm_poa(cdr_sdx[ci].get("poa", "")) != norm_poa(ak_sdx[ai].get("poa", "")):
            poa_defects += 1

    # ── PCS section ───────────────────────────────────────────────────────────
    ak_pcs = [p for p in ak.pcs if norm_pcs(p.get("code", ""))]
    cdr_pcs = [p for p in sub.pcs if norm_pcs(p.get("code", ""))]

    if len(ak_pcs) == 0 and len(cdr_pcs) == 0:
        proc = DPOSection("PCS Accuracy", 0, 0)
    else:
        ak_pcs_used = [False] * len(ak_pcs)
        pcs_matched = 0
        for cp in cdr_pcs:
            c = norm_pcs(cp.get("code", ""))
            for ai, ap in enumerate(ak_pcs):
                if not ak_pcs_used[ai] and norm_pcs(ap.get("code", "")) == c:
                    pcs_matched += 1
                    ak_pcs_used[ai] = True
                    break
        pcs_missed = len(ak_pcs) - pcs_matched
        pcs_extra = max(0, len(cdr_pcs) - len(ak_pcs)) if overcoding_penalty else 0
        pcs_opp = len(ak_pcs) + (pcs_extra if overcoding_penalty else 0)
        proc = DPOSection("PCS Accuracy", pcs_opp, pcs_missed + pcs_extra)

    # ── Overall ───────────────────────────────────────────────────────────────
    total_opp = dx_opp + poa_opp + proc.opportunities
    total_def = dx_defects + poa_defects + proc.defects
    overall = round(max(0.0, (1 - total_def / total_opp)) * 100, 1) if total_opp > 0 else 100.0

    return DPOResult(
        dx=DPOSection("Dx Accuracy", dx_opp, dx_defects),
        poa=DPOSection("POA Accuracy", poa_opp, poa_defects),
        proc=proc,
        overall_accuracy=overall,
    )


def compute_dpo_op(ak: OPAnswerKey, sub: OPSubmission, overcoding_penalty: bool) -> DPOResult:
    """DPO supplementary scoring for OP charts."""
    # ── DX section ────────────────────────────────────────────────────────────
    ak_sdx = [s for s in ak.sdx if norm_dx(s.get("code", ""))]
    cdr_sdx = [s for s in sub.sdx if norm_dx(s.get("code", ""))]

    dx_opp = 1 + len(ak_sdx)
    dx_defects = 0

    if norm_dx(sub.pdx_code) != norm_dx(ak.pdx_code):
        dx_defects += 1

    ak_sdx_used = [False] * len(ak_sdx)
    sdx_matched = 0
    for cs in cdr_sdx:
        c = norm_dx(cs.get("code", ""))
        for ai, a in enumerate(ak_sdx):
            if not ak_sdx_used[ai] and norm_dx(a.get("code", "")) == c:
                ak_sdx_used[ai] = True
                sdx_matched += 1
                break

    dx_defects += (len(ak_sdx) - sdx_matched)
    sdx_extra = max(0, len(cdr_sdx) - len(ak_sdx)) if overcoding_penalty else 0
    dx_defects += sdx_extra
    if overcoding_penalty and sdx_extra > 0:
        dx_opp += sdx_extra

    # ── CPT+Modifier section ──────────────────────────────────────────────────
    ak_cpt = [resolve_cpt_modifier(c.get("code", ""), c.get("modifier", "")) for c in ak.cpt]
    ak_cpt = [c for c in ak_cpt if c[0]]
    cdr_cpt = [resolve_cpt_modifier(c.get("code", ""), c.get("modifier", "")) for c in sub.cpt]
    cdr_cpt = [c for c in cdr_cpt if c[0]]

    if len(ak_cpt) == 0 and len(cdr_cpt) == 0:
        proc = DPOSection("CPT Accuracy", 0, 0)
    else:
        ak_cpt_used = [False] * len(ak_cpt)
        cpt_matched = 0
        for c, m in cdr_cpt:
            for ai, (a_c, a_m) in enumerate(ak_cpt):
                if not ak_cpt_used[ai] and a_c == c and a_m == m:
                    cpt_matched += 1
                    ak_cpt_used[ai] = True
                    break
        cpt_missed = len(ak_cpt) - cpt_matched
        cpt_extra = max(0, len(cdr_cpt) - len(ak_cpt)) if overcoding_penalty else 0
        cpt_opp = len(ak_cpt) + (cpt_extra if overcoding_penalty else 0)
        proc = DPOSection("CPT Accuracy", cpt_opp, cpt_missed + cpt_extra)

    total_opp = dx_opp + proc.opportunities
    total_def = dx_defects + proc.defects
    overall = round(max(0.0, (1 - total_def / total_opp)) * 100, 1) if total_opp > 0 else 100.0

    return DPOResult(
        dx=DPOSection("Dx Accuracy", dx_opp, dx_defects),
        poa=DPOSection("POA Accuracy", 0, 0),   # N/A for OP
        proc=proc,
        overall_accuracy=overall,
    )


def compute_dpo_ed_single_path(
    ak: EDSinglePathAnswerKey,
    sub: EDSinglePathSubmission,
    overcoding_penalty: bool,
) -> DPOResult:
    """DPO supplementary scoring for ED Single Path. Dx pointers are not used."""
    base = compute_dpo_op(
        OPAnswerKey(pdx_code=ak.pdx_code, sdx=ak.sdx, cpt=ak.cpt),
        OPSubmission(pdx_code=sub.pdx_code, sdx=sub.sdx, cpt=sub.cpt),
        overcoding_penalty=overcoding_penalty,
    )

    level_opp = 0
    level_defects = 0
    if _clean(ak.facility_level):
        level_opp += 1
        if norm_cpt(sub.facility_level) != norm_cpt(ak.facility_level):
            level_defects += 1
    if _clean(ak.profee_level):
        level_opp += 1
        if norm_cpt(sub.profee_level) != norm_cpt(ak.profee_level):
            level_defects += 1

    proc = DPOSection(
        "Level/CPT Accuracy",
        base.proc.opportunities + level_opp,
        base.proc.defects + level_defects,
    )
    total_opp = base.dx.opportunities + proc.opportunities
    total_def = base.dx.defects + proc.defects
    overall = round(max(0.0, (1 - total_def / total_opp)) * 100, 1) if total_opp > 0 else 100.0

    return DPOResult(dx=base.dx, poa=base.poa, proc=proc, overall_accuracy=overall)


def cfg_from_db(db_row) -> "IPScoringCfg | OPScoringCfg | EDSinglePathCfg":
    """Convert a ScoringConfig DB row to the appropriate config dataclass."""
    def _value(name: str, default):
        v = getattr(db_row, name, None)
        return default if v is None else v

    if db_row.specialty_type == "IP":
        return IPScoringCfg(
            pdx_weight=db_row.pdx_weight,
            sdx_weight=db_row.sdx_weight,
            pcs_weight=_value("pcs_weight", 20),
            drg_weight=_value("drg_weight", 40),
            pass_threshold=db_row.pass_threshold,
            overcoding_penalty=db_row.overcoding_penalty,
            drg_triggers=db_row.drg_triggers or [],
        )
    if db_row.specialty_type == "EDSP":
        return EDSinglePathCfg(
            pdx_weight=db_row.pdx_weight,
            sdx_weight=db_row.sdx_weight,
            facility_level_weight=_value("facility_level_weight", 20),
            profee_level_weight=_value("profee_level_weight", 20),
            cpt_weight=_value("cpt_weight", 20),
            pass_threshold=db_row.pass_threshold,
            overcoding_penalty=db_row.overcoding_penalty,
        )
    return OPScoringCfg(
        pdx_weight=db_row.pdx_weight,
        sdx_weight=db_row.sdx_weight,
        cpt_weight=_value("cpt_weight", 50),
        pass_threshold=db_row.pass_threshold,
        overcoding_penalty=db_row.overcoding_penalty,
    )


# ── ED Single Path grading ────────────────────────────────────────────────────

@dataclass
class EDSinglePathResult:
    pdx_score: int = 0
    sdx_score: int = 0
    facility_level_score: int = 0
    profee_level_score: int = 0
    cpt_score: int = 0
    total_score: int = 0
    pass_fail: str = ""
    facility_level_ok: bool = False
    profee_level_ok: bool = False
    feedback: list = field(default_factory=list)


def grade_ed_single_path(ak, sub, cfg: EDSinglePathCfg = DEFAULT_EDSP_CFG) -> EDSinglePathResult:
    """
    Grade one ED Single Path chart.

    Diagnoses are shared between the two claims and scored once. The facility
    and professional levels are scored separately so the report can distinguish
    "levelled facility correctly but not profee" from a general miss — that
    split is the reason single-path is trained at all.

    Diagnosis pointers are intentionally not enforced here. In single-path
    practice, the facility/profee split is already the learning target and
    pointer segregation is too ambiguous for reliable automated scoring.
    """
    result = EDSinglePathResult()
    feedback = []
    penalty = cfg.overcoding_penalty

    # ── Shared diagnoses ──
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

    # ── The two levels, scored independently ──
    fac_ak, fac_sub = norm_cpt(ak.facility_level), norm_cpt(sub.facility_level)
    result.facility_level_ok = bool(fac_ak) and fac_ak == fac_sub
    result.facility_level_score = cfg.facility_level_weight if result.facility_level_ok else 0
    if fac_ak and not result.facility_level_ok:
        feedback.append(FeedbackRow("CPT", "Wrong_Code", ak.facility_level or "",
                                    sub.facility_level or "", "Facility ED level"))

    pro_ak, pro_sub = norm_cpt(ak.profee_level), norm_cpt(sub.profee_level)
    result.profee_level_ok = bool(pro_ak) and pro_ak == pro_sub
    result.profee_level_score = cfg.profee_level_weight if result.profee_level_ok else 0
    if pro_ak and not result.profee_level_ok:
        feedback.append(FeedbackRow("CPT", "Wrong_Code", ak.profee_level or "",
                                    sub.profee_level or "", "Professional ED level"))

    # ── Additional CPTs (professional side -> pointer-checked) ──
    ak_cpt_cnt = len([c for c in ak.cpt if norm_cpt(c.get("code", ""))])
    cdr_cpt_cnt = len([c for c in sub.cpt if norm_cpt(c.get("code", ""))])
    if ak_cpt_cnt > 0:
        cpt_matched, cpt_extra, cpt_fb = _match_cpt(
            ak.cpt, sub.cpt, penalty,
            ak_dx=claim_dx_list(ak.pdx_code, ak.sdx),
            cdr_dx=claim_dx_list(sub.pdx_code, sub.sdx),
            check_pointers=False,
        )
        cpt_per = cfg.cpt_weight / ak_cpt_cnt
        result.cpt_score = max(0, round((cpt_matched - cpt_extra) * cpt_per))
        feedback.extend(cpt_fb)
    elif cdr_cpt_cnt == 0:
        result.cpt_score = cfg.cpt_weight
    else:
        result.cpt_score = 0
        feedback.append(FeedbackRow("CPT", "Over_coded", detail="AK has no additional CPTs but codes were submitted"))

    result.total_score = (result.pdx_score + result.sdx_score +
                          result.facility_level_score + result.profee_level_score +
                          result.cpt_score)
    result.pass_fail = "PASS" if result.total_score >= cfg.pass_threshold else "FAIL"
    result.feedback = feedback
    return result
