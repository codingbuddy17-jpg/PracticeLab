"""
A wrong POA is one finding, and the exempt indicator is E.

Two faults reported from a real IP-DRG submission.

The feedback said a code was both Wrong_POA and Missed. The second pass matches
on code alone to report a POA error, and never marked the key entry used — so
the pass after it reported the same entry absent. A coder who got five codes
right with the wrong POA saw twelve findings for seven mistakes, five of them
claiming a code they had plainly submitted was not there. The score never used
these rows, so the mark was right while the explanation was wrong, which is the
worse way round: the coder cannot tell which to believe.

And the coder's POA dropdown offered "1" for exempt while every answer key uses
"E", so an exempt diagnosis could never match — the form offered only a value
that was always wrong.
"""
from services.grading_engine import _match_sdx_ip, norm_poa


def _key(*pairs):
    return [{"code": c, "poa": p} for c, p in pairs]


class TestWrongPoaIsNotAlsoMissed:

    def test_a_wrong_poa_is_reported_once(self):
        ak = _key(("Z93.1", "Y"), ("Z79.4", "Y"))
        sub = _key(("Z93.1", "N"), ("Z79.4", "N"))
        _matched, _extra, fb = _match_sdx_ip(ak, sub, penalty=True)
        kinds = sorted(r.issue_type for r in fb)
        assert kinds == ["Wrong_POA", "Wrong_POA"], kinds
        assert not [r for r in fb if r.issue_type == "Missed"], (
            "a code submitted with the wrong POA was also reported missing")

    def test_genuinely_missed_codes_are_still_reported(self):
        """The control. Silencing Missed altogether would also pass the test above."""
        ak = _key(("Z93.1", "Y"), ("Q93.9", "Y"), ("Z79.899", "Y"))
        sub = _key(("Z93.1", "N"))
        _m, _e, fb = _match_sdx_ip(ak, sub, penalty=True)
        assert sorted(r.ak_code for r in fb if r.issue_type == "Missed") == ["Q93.9", "Z79.899"]
        assert [r.ak_code for r in fb if r.issue_type == "Wrong_POA"] == ["Z93.1"]

    def test_the_finding_carries_both_poa_values(self):
        """Comparing the codes says nothing — they are the same code."""
        ak = _key(("Z93.1", "Y"))
        sub = _key(("Z93.1", "N"))
        _m, _e, fb = _match_sdx_ip(ak, sub, penalty=True)
        row = fb[0]
        assert row.ak_code == row.coder_code == "Z93.1"
        assert "Y" in row.detail and "N" in row.detail, row.detail

    def test_a_correct_submission_produces_no_findings(self):
        ak = _key(("Z93.1", "Y"), ("Q93.9", "N"))
        _m, _e, fb = _match_sdx_ip(ak, list(ak), penalty=True)
        assert fb == []

    def test_the_reported_case(self):
        """Five right codes with wrong POA, two never submitted: seven, not twelve."""
        ak = _key(*[(c, "Y") for c in
                    ("Z93.1", "Z79.4", "Z91.018", "Z88.8", "Q04.0", "Q93.9", "Z79.899")])
        sub = _key(*[(c, "N") for c in ("Z93.1", "Z79.4", "Z91018", "Z88.8", "Q04.0")])
        _m, _e, fb = _match_sdx_ip(ak, sub, penalty=True)
        assert len(fb) == 7, [(r.issue_type, r.ak_code) for r in fb]


class TestExemptIsE:

    def test_one_and_E_are_the_same_value(self):
        """
        Submissions already stored under "1" must still grade correctly, since
        that is the only value the form used to offer.
        """
        assert norm_poa("1") == "E"
        assert norm_poa("e") == "E"
        assert norm_poa(" E ") == "E"

    def test_a_key_of_E_matches_a_submission_of_1(self):
        ak = _key(("Z93.1", "E"))
        sub = _key(("Z93.1", "1"))
        matched, _e, fb = _match_sdx_ip(ak, sub, penalty=True)
        assert matched == 1, "an exempt diagnosis could not match its own key"
        assert fb == []

    def test_other_values_are_untouched(self):
        for v in ("Y", "N", "U", "W"):
            assert norm_poa(v) == v
        # Not a blanket alias — only the exempt indicator.
        ak, sub = _key(("Z93.1", "Y")), _key(("Z93.1", "N"))
        matched, _e, _fb = _match_sdx_ip(ak, sub, penalty=True)
        assert matched == 0


def test_the_frontend_offers_E_not_1():
    """Every screen where a POA is chosen. The keys all use E."""
    from pathlib import Path
    root = Path(__file__).resolve().parents[2] / "frontend" / "src"
    for rel in ("pages/PracticeSession.tsx",
                "pages/practicelab/AnswerKeyEditor.tsx",
                "pages/AuditSession.tsx"):
        src = (root / rel).read_text()
        # The DEFINITION, not the first use of it — AuditSession refers to
        # POA_VALUES hundreds of lines above where it declares them.
        i = src.find("const POA_")
        assert i != -1, "%s declares no POA list" % rel
        block = src[i:src.find("\n\n", i)] if "\n\n" in src[i:] else src[i:i + 400]
        assert "'E'" in block or '"E"' in block, "%s does not offer E: %s" % (rel, block[:200])
        assert "'1'" not in block, "%s still offers 1 for exempt" % rel


class TestOverCodingNamesTheCodes:
    """
    "1 extra code(s) submitted" says a coder over-coded and leaves them to find
    where. On a chart with a dozen procedures that is the review over again,
    and it was the first thing asked about the redesigned screen.

    The count and the named codes are not the same quantity. `extra` is
    submitted minus expected, so it can differ from the number that failed to
    match — the count is what is scored, the names are what a coder can act on.
    """

    def test_procedures_name_the_surplus(self):
        from services.grading_engine import _match_pcs
        _m, extra, fb = _match_pcs(
            [{"code": "0DTJ0ZZ"}],
            [{"code": "0DTJ0ZZ"}, {"code": "0DTJ4ZZ"}, {"code": "0FB03ZX"}], True)
        row = [r for r in fb if r.issue_type == "Over_coded"][0]
        assert extra == 2
        assert "0DTJ4ZZ" in row.detail and "0FB03ZX" in row.detail
        assert "0DTJ0ZZ" not in row.detail, "the matched procedure was called surplus"
        # The row is already labelled Over coded; the detail is the codes.
        assert not row.detail.lower().startswith(("not in", "extra")), row.detail

    def test_diagnoses_name_the_surplus(self):
        ak = [{"code": "Z23", "poa": "Y"}]
        sub = [{"code": "Z23", "poa": "Y"}, {"code": "E11.9", "poa": "N"}]
        _m, _e, fb = _match_sdx_ip(ak, sub, True)
        row = [r for r in fb if r.issue_type == "Over_coded"][0]
        assert "E11.9" in row.detail

    def test_a_wrong_poa_code_is_not_called_surplus(self):
        """
        It matched on code, so it is not an extra — it is the same code with
        the wrong POA, and reporting it twice is the fault this file exists for.
        """
        ak = [{"code": "Z23", "poa": "Y"}, {"code": "Q53.9", "poa": "Y"}]
        sub = [{"code": "Z23", "poa": "N"}, {"code": "Q53.9", "poa": "N"},
               {"code": "E11.9", "poa": "N"}]
        _m, _e, fb = _match_sdx_ip(ak, sub, True)
        over = [r for r in fb if r.issue_type == "Over_coded"]
        assert over, "an extra code was submitted and not reported"
        assert "Z23" not in over[0].detail and "Q53.9" not in over[0].detail
        assert "E11.9" in over[0].detail

    def test_it_falls_back_to_the_count_when_nothing_can_be_named(self):
        """Never worse than it was — the count still appears on its own."""
        from services.grading_engine import _surplus_detail
        assert _surplus_detail(3, []) == "3 extra code(s) submitted"

    def test_a_long_list_is_capped(self):
        from services.grading_engine import _surplus_detail
        d = _surplus_detail(9, ["A%d" % i for i in range(9)])
        assert "…" in d and d.count(",") <= 6

    def test_the_codes_lead_and_the_penalty_follows(self):
        """
        The count and the names are different quantities and diverge whenever a
        coder both misses codes and adds them. Four right, two missed, three
        invented scores as ONE extra beside THREE named codes — putting the
        count first made that read as a contradiction.
        """
        ak = [{"code": c, "poa": "Y"} for c in ("A", "B", "C", "D", "E", "F")]
        sub = [{"code": c, "poa": "Y"} for c in ("A", "B", "C", "D", "X", "Y", "Z")]
        _m, extra, fb = _match_sdx_ip(ak, sub, True)
        row = [r for r in fb if r.issue_type == "Over_coded"][0]
        assert extra == 1
        assert row.detail.startswith("X, Y, Z"), row.detail
        # Three codes named, one scored: the sentence has to say why those are
        # different numbers, or it reads as an arithmetic error.
        assert "did not match" in row.detail
        assert "1 more code(s) submitted than the key holds" in row.detail


class TestWhenTheKeyExpectsNothing:
    """
    A separate branch from the surplus one, and it had the same fault.

    Where the key holds no codes for a section at all and the coder entered
    some, the finding read "AK has no PCS but codes were submitted" — a rule,
    not a fact about their chart. It left them to work out which of their
    procedures it meant, and it said "AK", which is trainer vocabulary that a
    coder has no reason to know.
    """

    def _graded(self, ak, sub):
        from services.grading_engine import (DEFAULT_IP_CFG, IPAnswerKey,
                                             IPSubmission, grade_ip)
        return grade_ip(IPAnswerKey(**ak), IPSubmission(**sub), DEFAULT_IP_CFG).feedback

    def test_procedures_are_named_when_none_were_expected(self):
        fb = self._graded(
            dict(pdx_code="K56.41", pdx_poa="Y", sdx=[{"code": "Z93.1", "poa": "Y"}], pcs=[]),
            dict(pdx_code="K56.41", pdx_poa="Y", sdx=[{"code": "Z93.1", "poa": "Y"}],
                 pcs=[{"code": "0DTJ0ZZ"}, {"code": "0DTJ4ZZ"}]))
        row = [r for r in fb if r.section == "PCS" and r.issue_type == "Over_coded"][0]
        assert "0DTJ0ZZ" in row.detail and "0DTJ4ZZ" in row.detail
        assert "AK" not in row.detail, "trainer vocabulary on a coder's screen"

    def test_diagnoses_are_named_when_none_were_expected(self):
        fb = self._graded(
            dict(pdx_code="K56.41", pdx_poa="Y", sdx=[], pcs=[{"code": "0DTJ0ZZ"}]),
            dict(pdx_code="K56.41", pdx_poa="Y",
                 sdx=[{"code": "E11.9", "poa": "N"}, {"code": "I10", "poa": "N"}],
                 pcs=[{"code": "0DTJ0ZZ"}]))
        row = [r for r in fb if r.section == "SDx" and r.issue_type == "Over_coded"][0]
        assert "E11.9" in row.detail and "I10" in row.detail

    def test_no_finding_at_all_when_the_coder_also_entered_nothing(self):
        """The control — the branch only fires on codes that were entered."""
        fb = self._graded(
            dict(pdx_code="K56.41", pdx_poa="Y", sdx=[{"code": "Z93.1", "poa": "Y"}], pcs=[]),
            dict(pdx_code="K56.41", pdx_poa="Y", sdx=[{"code": "Z93.1", "poa": "Y"}], pcs=[]))
        assert not [r for r in fb if r.section == "PCS"]

    def test_no_wording_anywhere_still_says_AK(self):
        """
        Six call sites carried it and all six are a coder's to read. A grep,
        because the next one added would otherwise reintroduce the phrase.
        """
        from pathlib import Path
        src = (Path(__file__).resolve().parents[1] / "services" / "grading_engine.py").read_text()
        offenders = [l.strip() for l in src.split("\n")
                     if "detail=" in l and "AK has no" in l]
        assert not offenders, offenders
