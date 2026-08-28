"""
A batch summary must not report more coders passed than there are coders.

The insights panel headlines the number of coders, then showed "Passed 3 /
Failed 1" underneath. Those were CHARTS — three of four charts passed — but
sitting beside "Coders 2" they read as three coders out of two.

Both bases are legitimate and both are here. The rate stays chart-based and
says so in its label; the raw counts are the coders', because that is the
outcome that belongs beside a coder count. What is not acceptable is a figure
whose basis has to be guessed.
"""
from models import (Batch, BatchStatus, Chart, ChartStatus, Difficulty,
                    GradingResult, PassFail, Specialty)
from routers.practicelab_pkg.grading import coder_verdict


def _batch(db, rows):
    """rows = [(coder, score, pass_fail)]"""
    b = Batch(name="Basis", specialty=Specialty.IP_DRG, status=BatchStatus.OPEN,
              created_by="t", charts_per_coder=2, is_direct_assignment=False,
              use_weighted=True, use_dpo=False, force_closed=False)
    db.add(b); db.commit()
    for i, (coder, score, pf) in enumerate(rows):
        c = Chart(chart_number="IPB%03d" % i, specialty=Specialty.IP_DRG, category="C",
                  difficulty=Difficulty.INTERMEDIATE, status=ChartStatus.ACTIVE, uploaded_by="t")
        db.add(c); db.flush()
        db.add(GradingResult(batch_id=b.id, coder_name=coder, chart_id=c.id,
                             specialty=Specialty.IP_DRG, pdx_score=20, sdx_score=20,
                             pcs_score=20, total_score=score, pass_fail=pf))
    db.commit()
    return b.id


class TestTheVerdictRule:
    """Written once because two screens report it."""

    def test_a_majority_of_charts_passes_the_coder(self):
        assert coder_verdict(2, 3) == "PASS"
        assert coder_verdict(3, 4) == "PASS"

    def test_exactly_half_does_not(self):
        assert coder_verdict(1, 2) == "FAIL"
        assert coder_verdict(2, 4) == "FAIL"

    def test_nothing_scored_is_pending_not_failed(self):
        """A coder who has not sat the work has not failed it."""
        assert coder_verdict(0, 0) == "PENDING"


class TestTheInsightsPanel:

    def test_coders_passed_never_exceeds_the_coder_count(self, client, db):
        """The reported fault, as an invariant."""
        bid = _batch(db, [("Asha", 90, PassFail.PASS), ("Asha", 90, PassFail.PASS),
                          ("Ben", 90, PassFail.PASS), ("Ben", 40, PassFail.FAIL)])
        bs = client.get("/practicelab/batches/%d/insights" % bid).json()["batch_summary"]
        assert bs["n_coders"] == 2
        assert bs["coders_passed"] <= bs["n_coders"]
        assert bs["coders_passed"] + bs["coders_failed"] == bs["n_coders"]

    def test_the_chart_basis_is_still_reported(self, client, db):
        """
        Both bases are wanted. Losing the chart figures to fix the labels would
        have thrown away the more sensitive quality signal.
        """
        bid = _batch(db, [("Asha", 90, PassFail.PASS), ("Asha", 40, PassFail.FAIL),
                          ("Ben", 90, PassFail.PASS), ("Ben", 90, PassFail.PASS)])
        bs = client.get("/practicelab/batches/%d/insights" % bid).json()["batch_summary"]
        assert bs["passed"] == 3 and bs["failed"] == 1      # charts
        assert bs["pass_rate_basis"] == "chart"
        # And one coder on a coder basis: Asha passed exactly half her charts,
        # which does not carry her. Three charts and one coder from the same
        # four results is precisely why the label has to say which it is.
        assert bs["coders_passed"] == 1 and bs["coders_failed"] == 1

    def test_the_two_batch_screens_agree_on_who_passed(self, client, db):
        """
        The insights panel and the results tab compute this separately. They
        must not be able to disagree about the same coders.
        """
        bid = _batch(db, [("Asha", 90, PassFail.PASS), ("Asha", 40, PassFail.FAIL),
                          ("Ben", 90, PassFail.PASS), ("Ben", 90, PassFail.PASS)])
        ins = client.get("/practicelab/batches/%d/insights" % bid).json()["batch_summary"]
        res = client.get("/practicelab/batches/%d/results" % bid).json()["batch_summary"]
        assert ins["coders_passed"] == res["passed"], (
            "insights says %s coders passed, results says %s"
            % (ins["coders_passed"], res["passed"]))
