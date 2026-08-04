"""
The figures on the trainer landing page.

A landing page has no filters, so it must not silently inherit one — and every
number on it is read as "the whole system" because there is nothing on screen
suggesting otherwise.
"""
import pytest

from models import Chart, Batch, Specialty, AnswerKey, GradingResult, PassFail
from models.charts import ChartStatus, Difficulty
from models.practicelab import BatchStatus


def _chart(db, n, sp=Specialty.IP_DRG, key=False):
    c = Chart(chart_number=n, specialty=sp, category="Sepsis", difficulty=Difficulty.BEGINNER,
              status=ChartStatus.ACTIVE, uploaded_by="t", view_count=0)
    db.add(c); db.commit()
    if key:
        db.add(AnswerKey(chart_id=c.id, specialty=sp, pdx_code="J18.9",
                         sdx=[], pcs=[], cpt=[], entered_by="t"))
        db.commit()
    return c


def _batch(db, name, direct=False):
    b = Batch(name=name, specialty=Specialty.IP_DRG, status=BatchStatus.OPEN, created_by="t",
              charts_per_coder=1, is_direct_assignment=direct,
              use_weighted=True, use_dpo=False, force_closed=False)
    db.add(b); db.commit()
    return b


class TestBatchCount:
    def test_direct_assignments_are_counted_on_the_landing_page(self, client, db):
        """
        The page showed three batches while ten existed — seven direct
        assignments excluded by a default the page never chose.
        """
        for i in range(3):
            _batch(db, f"Formal {i}")
        for i in range(7):
            _batch(db, f"Direct {i}", direct=True)
        body = client.get("/practicelab/analytics/overview", params={"scope": "all"}).json()
        assert body["total_batches"] == 10

    def test_the_default_scope_still_excludes_them(self, client, db):
        """The default is not wrong — it is wrong for a page with no filter."""
        _batch(db, "Formal")
        _batch(db, "Direct", direct=True)
        assert client.get("/practicelab/analytics/overview").json()["total_batches"] == 1


class TestChartStats:
    def test_specialties_are_named_not_just_counted(self, client, db):
        """
        The page listed them from a hardcoded string that had gone stale — it
        named ICD-10, which is a code set rather than a specialty, and predated
        Surgery and ED Single Path.
        """
        _chart(db, "IP1")
        _chart(db, "SD1", Specialty.SDS)
        _chart(db, "SU1", Specialty.SURGERY)
        body = client.get("/charts/stats").json()
        assert body["total_specialties"] == 3
        assert {s["specialty"] for s in body["specialties"]} == {"IP-DRG", "SDS", "Surgery"}

    def test_specialties_are_ordered_by_volume(self, client, db):
        for i in range(3):
            _chart(db, f"IP{i}")
        _chart(db, "SD1", Specialty.SDS)
        body = client.get("/charts/stats").json()
        assert body["specialties"][0]["specialty"] == "IP-DRG"
        assert body["specialties"][0]["charts"] == 3

    def test_charts_without_keys_are_reported(self, client, db):
        """Inventory that looks like capacity until a batch is built from it."""
        _chart(db, "K1", key=True)
        _chart(db, "K2", key=True)
        _chart(db, "N1", key=False)
        body = client.get("/charts/stats").json()
        assert body["charts_with_keys"] == 2
        assert body["charts_without_keys"] == 1

    def test_retired_charts_count_nowhere(self, client, db):
        c = _chart(db, "R1")
        c.status = ChartStatus.RETIRED
        db.commit()
        body = client.get("/charts/stats").json()
        assert body["total_charts"] == 0
        assert body["specialties"] == []


class TestAssessmentClearance:
    def test_the_overview_carries_a_clearance_rate(self, client):
        """The third assessment tile was a static "Generate" button — a button
        dressed as a statistic, in the one slot that could carry an outcome."""
        body = client.get("/assessment/analytics/overview").json()
        for k in ("overall_pass_rate", "total_sessions", "total_submitted"):
            assert k in body
