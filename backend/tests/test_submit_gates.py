"""
An irreversible submission asks first.

The coder's practice session let a wholly empty session go in one click: the
review screen said "0 charts coded · 2 not started" in grey, the button was
enabled, and the screen itself warns that submissions cannot be edited. The
auditor blocks the same moment properly, which is what showed this was a choice
rather than a constraint.

The rule that came out of it: nothing coded at all is an accident and is
blocked; some charts left is a legitimate decision and is confirmed, not
blocked. Static assertions, because the frontend has no test runner.
"""
import pathlib
import re

SRC = pathlib.Path(__file__).resolve().parents[2] / "frontend" / "src" / "pages"


class TestThePracticeSubmitGate:
    def test_a_wholly_empty_session_cannot_be_submitted(self):
        src = (SRC / "PracticeSession.tsx").read_text()
        assert "nothingCoded" in src, "no guard against submitting nothing"
        m = re.search(r"disabled=\{submitting[^}]*\}", src)
        assert m and "nothingCoded" in m.group(0), (
            "the submit button does not disable when nothing has been coded")

    def test_leaving_some_charts_asks_rather_than_blocks(self):
        """
        A coder may legitimately submit having been told to do two of three.
        That must be a question, not a wall.
        """
        src = (SRC / "PracticeSession.tsx").read_text()
        assert "confirmingSubmit" in src
        assert "Yes, submit with" in src

    def test_the_auditor_still_blocks_its_own_gate(self):
        """The stricter module must not drift to match the looser one."""
        src = (SRC / "AuditSession.tsx").read_text()
        assert "disabled" in src and "needs a verdict" in src


class TestTheAssessmentSubmitGate:
    def test_final_submit_confirms_before_an_irreversible_send(self):
        src = (SRC / "TakeAssessmentSession.tsx").read_text()
        assert "confirmingFinal" in src, (
            "Final Submit sends immediately with no confirmation step")
