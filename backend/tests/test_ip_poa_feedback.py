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
