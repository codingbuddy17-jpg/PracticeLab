"""
The coder profile payload.

Its defining property is that it mixes formal batches with direct assignments,
which is right for a coder's record and wrong for a team aggregate. Everything
here follows from that: the history has to say which is which, and the report
header has to describe the work rather than assert it covers everything.
"""
from datetime import datetime

import pytest

from models import Chart, Batch, Specialty, GradingResult, PassFail
from models.charts import ChartStatus, Difficulty
from models.practicelab import BatchStatus

URL = "/practicelab/analytics/coder-summary"


def _chart(db, number, specialty=Specialty.IP_DRG, category="Sepsis"):
    c = Chart(chart_number=number, specialty=specialty, category=category,
              difficulty=Difficulty.BEGINNER, status=ChartStatus.ACTIVE,
              uploaded_by="t", view_count=0)
    db.add(c); db.commit()
    return c


def _batch(db, name, specialty=Specialty.IP_DRG, direct=False):
    b = Batch(name=name, specialty=specialty, status=BatchStatus.OPEN, created_by="t",
              charts_per_coder=1, is_direct_assignment=direct,
              use_weighted=True, use_dpo=False, force_closed=False)
    db.add(b); db.commit()
    return b


def _result(db, batch, chart, score, coder="Asha R", emp="E1"):
    r = GradingResult(batch_id=batch.id, coder_name=coder, emp_id=emp, chart_id=chart.id,
                      specialty=chart.specialty, total_score=score,
                      pass_fail=PassFail.PASS if score >= 80 else PassFail.FAIL)
    db.add(r); db.commit()
    return r


def _get(client, coder="Asha R", **params):
    return client.get(URL, params={"coder_name": coder, **params}).json()


class TestSpecialtyMix:
    def test_reports_what_the_coder_actually_works_on(self, client, db):
        """
        The PDF header said "All practice & batch work", which is true of every
        report it has ever produced and tells a reader nothing. The scores in a
        report are scores in SOME specialty; this is which.
        """
        b = _batch(db, "B1")
        _result(db, b, _chart(db, "IP950"), 90)
        _result(db, b, _chart(db, "IP951"), 70)
        _result(db, b, _chart(db, "SDS950", Specialty.SDS), 85)
        mix = {m["specialty"]: m["charts"] for m in _get(client)["specialty_mix"]}
        assert mix == {"IP-DRG": 2, "SDS": 1}

    def test_mix_is_ordered_by_volume(self, client, db):
        b = _batch(db, "B2")
        _result(db, b, _chart(db, "SDS960", Specialty.SDS), 90)
        _result(db, b, _chart(db, "SDS961", Specialty.SDS), 90)
        _result(db, b, _chart(db, "IP960"), 90)
        assert _get(client)["specialty_mix"][0]["specialty"] == "SDS"


class TestProcedureLabel:
    """PCS and CPT are different code sets; "Procedure accuracy" reads as
    whichever the trainer's own specialty uses, which is a guess."""

    def test_ip_only_says_pcs(self, client, db):
        b = _batch(db, "IP Only")
        _result(db, b, _chart(db, "IP970"), 90)
        assert _get(client)["proc_label"] == "PCS accuracy"

    def test_outpatient_only_says_cpt(self, client, db):
        b = _batch(db, "OP Only", Specialty.SDS)
        _result(db, b, _chart(db, "SDS970", Specialty.SDS), 90)
        assert _get(client)["proc_label"] == "CPT accuracy"

    def test_a_mix_says_both(self, client, db):
        b = _batch(db, "Mixed")
        _result(db, b, _chart(db, "IP971"), 90)
        _result(db, b, _chart(db, "SDS971", Specialty.SDS), 90)
        assert _get(client)["proc_label"] == "Procedure accuracy (PCS + CPT)"


class TestHistoryDistinguishesDirect:
    def test_each_row_declares_its_type(self, client, db):
        """
        A coder's history mixes both by design. Without the flag, a run of
        one-off charts is indistinguishable from batch work.
        """
        formal = _batch(db, "Formal")
        direct = _batch(db, "One Off", direct=True)
        _result(db, formal, _chart(db, "IP980"), 90)
        _result(db, direct, _chart(db, "IP981"), 40)
        rows = {b["batch_name"]: b["is_direct_assignment"] for b in _get(client)["batches"]}
        assert rows == {"Formal": False, "One Off": True}

    def test_direct_work_still_counts_toward_the_coder(self, client, db):
        """The flag labels the row; it must not quietly exclude it."""
        formal = _batch(db, "Formal")
        direct = _batch(db, "One Off", direct=True)
        _result(db, formal, _chart(db, "IP990"), 100)
        _result(db, direct, _chart(db, "IP991"), 0)
        body = _get(client)
        assert body["total_charts"] == 2
        assert body["weighted_accuracy"] == 50.0


class TestLastActivity:
    def test_reports_the_most_recent_grading(self, client, db):
        b = _batch(db, "Dated")
        _result(db, b, _chart(db, "IP995"), 90)
        _result(db, b, _chart(db, "IP996"), 80)
        rows = db.query(GradingResult).order_by(GradingResult.id).all()
        rows[0].graded_at = datetime(2026, 1, 2, 9, 0)
        rows[1].graded_at = datetime(2026, 5, 9, 9, 0)
        db.commit()
        assert _get(client)["last_activity"].startswith("2026-05-09")


class TestReportHeader:
    def test_pdf_names_the_specialties_rather_than_claiming_everything(self, client, db):
        """The report must open by describing the work it covers."""
        b = _batch(db, "For Report")
        _result(db, b, _chart(db, "IP997"), 90)
        r = client.get("/practicelab/analytics/coder-report.pdf", params={"coder_name": "Asha R"})
        assert r.status_code == 200
        assert r.content[:4] == b"%PDF"
