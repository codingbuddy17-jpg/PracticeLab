"""
The batch report PDF, generated over the shapes a real batch actually takes.

Every test here opens the bytes that come back. A report that 500s or renders
a box with text hanging out of it is not visible from reading the generator —
only from running it against awkward data.
"""
import pytest

from models import (Chart, Batch, Specialty, GradingResult, GradingFeedback,
                    PassFail)
from models.charts import ChartStatus, Difficulty
from models.practicelab import BatchStatus


def _chart(db, n, sp=Specialty.IP_DRG, cat="Sepsis"):
    c = Chart(chart_number=n, specialty=sp, category=cat, difficulty=Difficulty.BEGINNER,
              status=ChartStatus.ACTIVE, uploaded_by="t", view_count=0)
    db.add(c); db.commit()
    return c


def _batch(db, name, sp=Specialty.IP_DRG):
    b = Batch(name=name, specialty=sp, status=BatchStatus.OPEN, created_by="t",
              charts_per_coder=1, is_direct_assignment=False, use_weighted=True,
              use_dpo=False, force_closed=False)
    db.add(b); db.commit()
    return b


def _result(db, b, c, coder, score, emp="E1"):
    r = GradingResult(batch_id=b.id, coder_name=coder, emp_id=emp, chart_id=c.id,
                      specialty=c.specialty, total_score=score,
                      pass_fail=PassFail.PASS if score >= 80 else PassFail.FAIL)
    db.add(r); db.commit()
    return r


def _pdf(client, batch_id):
    r = client.get(f"/practicelab/batches/{batch_id}/insights/report.pdf")
    assert r.status_code == 200, f"{r.status_code}: {r.text[:300]}"
    assert r.content[:4] == b"%PDF", "not a PDF"
    return r.content


class TestItRendersAtAll:
    def test_one_coder_one_chart(self, client, db):
        b = _batch(db, "Solo")
        _result(db, b, _chart(db, "IP1"), "A", 90)
        assert len(_pdf(client, b.id)) > 1000

    def test_rubric_specialty(self, client, db):
        """Edits/Denials produce no codes and no DPO — every code section is empty."""
        b = _batch(db, "Edits", Specialty.EDITS)
        _result(db, b, _chart(db, "ED1", Specialty.EDITS, "Claim Edits"), "A", 70)
        _pdf(client, b.id)

    def test_em_specialty(self, client, db):
        b = _batch(db, "EM", Specialty.EM)
        _result(db, b, _chart(db, "EM1", Specialty.EM, "Office Visit"), "A", 85)
        _pdf(client, b.id)

    def test_every_score_identical(self, client, db):
        """Zero variance — distribution buckets and min/max collapse onto one value."""
        b = _batch(db, "Flat")
        for i in range(3):
            _result(db, b, _chart(db, f"IPF{i}"), f"C{i}", 100, emp=f"F{i}")
        _pdf(client, b.id)

    def test_every_score_zero(self, client, db):
        b = _batch(db, "Zeroes")
        for i in range(3):
            _result(db, b, _chart(db, f"IPZ{i}"), f"C{i}", 0, emp=f"Z{i}")
        _pdf(client, b.id)

    def test_a_batch_with_no_results_404s_rather_than_500s(self, client, db):
        b = _batch(db, "Empty")
        r = client.get(f"/practicelab/batches/{b.id}/insights/report.pdf")
        assert r.status_code == 404, r.text

    def test_a_missing_batch_404s(self, client):
        assert client.get("/practicelab/batches/999999/insights/report.pdf").status_code == 404


class TestAwkwardContent:
    """The overflow cases: long strings in cells sized for short ones."""

    def test_very_long_batch_chart_and_coder_names(self, client, db):
        b = _batch(db, "Quarterly Inpatient DRG Validation Wave 3 — Northeast Region Coding Team 2026")
        c = _chart(db, "IP-VERYLONGCHARTNUMBER-000002",
                   cat="Sepsis with Acute Organ Dysfunction and Septic Shock Complications")
        _result(db, b, c, "Bartholomew Fitzgerald-Winchester III", 55)
        _pdf(client, b.id)

    def test_many_coders_and_categories(self, client, db):
        b = _batch(db, "Big One")
        for i in range(25):
            _result(db, b, _chart(db, f"IPB{i}", cat=f"Category Number {i} With A Rather Long Name"),
                    f"Coder Number {i}", 40 + i * 2, emp=f"E{i}")
        _pdf(client, b.id)

    def test_long_feedback_detail(self, client, db):
        b = _batch(db, "Feedback Heavy")
        r = _result(db, b, _chart(db, "IPFB1"), "A", 60)
        for i in range(8):
            db.add(GradingFeedback(result_id=r.id, section="SDx", issue_type="Missed",
                                   ak_code=f"J{i}18.9", coder_code=None,
                                   detail="Coder omitted the secondary diagnosis "
                                          "despite clear documentation in the record. " * 3))
        db.commit()
        _pdf(client, b.id)

    def test_a_coder_name_with_no_spaces_to_wrap_on(self, client, db):
        """A single long token cannot wrap, so it overflows rather than breaking."""
        b = _batch(db, "Unwrappable")
        _result(db, b, _chart(db, "IPU1"), "AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA", 70)
        _pdf(client, b.id)


class TestFilenameHeaders:
    """
    The 500 was never in the PDF — it was the Content-Disposition header.

    HTTP headers are latin-1. A batch named "Wave 3 — Northeast" raised
    UnicodeEncodeError while Starlette encoded the response, AFTER the handler
    had returned a perfectly good PDF. So the report failed every time for that
    batch and worked for every other one, and the traceback pointed at the web
    server rather than at the name.
    """

    @pytest.mark.parametrize("name", [
        "Wave 3 — Northeast",          # em dash: the one that was reported
        "Q1 “Pilot” Batch",            # curly quotes
        "Révision Février",            # accents
        "住院编码批次",                  # non-Latin script
        "Batch / with \\ slashes",     # path separators
        "…leading ellipsis",
    ])
    def test_awkward_batch_names_still_download(self, client, db, name):
        b = _batch(db, name)
        _result(db, b, _chart(db, f"IPN{abs(hash(name)) % 10000}"), "A", 90)
        r = client.get(f"/practicelab/batches/{b.id}/insights/report.pdf")
        assert r.status_code == 200, f"{r.status_code}: {r.text[:200]}"
        assert r.content[:4] == b"%PDF"
        # The header must be latin-1 encodable, which is what blew up before.
        r.headers["content-disposition"].encode("latin-1")

    def test_the_real_name_survives_for_clients_that_can_read_it(self, client, db):
        """ASCII filename for everyone, RFC 6266 filename* for the real thing."""
        b = _batch(db, "Wave 3 — Northeast")
        _result(db, b, _chart(db, "IPRFC1"), "A", 90)
        cd = client.get(f"/practicelab/batches/{b.id}/insights/report.pdf").headers["content-disposition"]
        assert "filename=" in cd and "filename*=UTF-8''" in cd

    def test_batch_results_excel_too(self, client, db):
        """Same header, same crash — the Excel export shares the fault."""
        b = _batch(db, "Wave 3 — Northeast")
        _result(db, b, _chart(db, "IPX1"), "A", 90)
        r = client.get(f"/practicelab/batches/{b.id}/results/export")
        assert r.status_code == 200, r.text
        r.headers["content-disposition"].encode("latin-1")


class TestSanitiser:
    def test_keeps_something_readable(self):
        from services.download_headers import safe_filename
        assert safe_filename("Wave 3 — Northeast_Report.pdf") == "Wave_3_-_Northeast_Report.pdf"

    def test_falls_back_when_nothing_survives(self):
        """A name of only non-Latin characters must not become an empty filename."""
        from services.download_headers import safe_filename
        assert safe_filename("住院编码", "download") == "download"

    def test_caps_the_length(self):
        from services.download_headers import safe_filename
        assert len(safe_filename("A" * 300)) <= 80


class TestStatCardLayout:
    """
    Six stat cards on one row made each ~1.1 inch wide. The label did not
    overflow — KeepInFrame shrank it — but shrink is per-card, so adjacent
    boxes rendered at different font sizes and the row looked ragged.
    """

    def test_a_long_row_wraps_instead_of_shrinking(self):
        from services.pdf_report_service import _stat_row, MAX_STATS_PER_ROW
        from reportlab.platypus import KeepTogether
        six = [(str(i), f"Label Number {i}") for i in range(6)]
        assert isinstance(_stat_row(six), KeepTogether), "should wrap onto more than one row"
        assert MAX_STATS_PER_ROW == 4

    def test_rows_are_balanced_so_cards_stay_one_width(self):
        """6 becomes 3+3, not 4+2 — a row of 4 beside a row of 2 looks broken."""
        from services.pdf_report_service import _stat_row
        from reportlab.platypus import Table
        six = [(str(i), f"L{i}") for i in range(6)]
        rows = [f for f in _stat_row(six)._content if isinstance(f, Table)]
        assert len(rows) == 2
        # 3 cards + 2 gap columns
        assert all(len(r._argW) == 5 for r in rows), [len(r._argW) for r in rows]

    def test_a_short_row_is_left_alone(self):
        from services.pdf_report_service import _stat_row
        from reportlab.platypus import Table
        assert isinstance(_stat_row([("1", "A"), ("2", "B")]), Table)

    def test_the_batch_report_actually_uses_six_stats(self, client, db):
        """Guards the premise: if the report stops passing six, this test is
        no longer covering anything and should be revisited."""
        b = _batch(db, "Six Stats")
        _result(db, b, _chart(db, "IPS1"), "A", 90)
        import services.pdf_report_service as svc
        seen = []
        original = svc._stat_row
        svc._stat_row = lambda stats, *a, **k: (seen.append(len(stats)), original(stats, *a, **k))[1]
        try:
            _pdf(client, b.id)
        finally:
            svc._stat_row = original
        assert seen and seen[0] > MAX_PER_ROW_GUARD, "batch report should still be wrapping"


MAX_PER_ROW_GUARD = 4


class TestEveryListedBatchHasAWorkingReport:
    """
    Analytics -> By Batch enables a PDF button on every row, on the grounds
    that the endpoint only lists batches with graded results. That was true of
    the LISTING and false of the REPORT.

    There are two result stores: /practice writes practice_results, everything
    else writes grading_results, and practice work is mirrored into the latter.
    The insights endpoint read only practice_results for direct assignments,
    so a direct assignment graded through the normal path was listed by
    Analytics (which reads grading_results) and 404'd when its button was
    pressed.
    """

    def _direct(self, db, name="Direct One"):
        b = Batch(name=name, specialty=Specialty.IP_DRG, status=BatchStatus.OPEN,
                  created_by="t", charts_per_coder=1, is_direct_assignment=True,
                  use_weighted=True, use_dpo=False, force_closed=False)
        db.add(b); db.commit()
        return b

    def test_a_direct_assignment_with_only_grading_results(self, client, db):
        b = self._direct(db)
        _result(db, b, _chart(db, "IPD1"), "A", 90)
        listed = [r["batch_name"] for r in
                  client.get("/practicelab/analytics/by-batch", params={"scope": "direct"}).json()]
        assert listed == ["Direct One"]
        _pdf(client, b.id)

    def test_every_row_by_batch_lists_can_produce_a_report(self, client, db):
        """The invariant the enabled button depends on, stated directly."""
        formal = _batch(db, "Formal")
        _result(db, formal, _chart(db, "IPE1"), "A", 90)
        direct = self._direct(db, "Direct Two")
        _result(db, direct, _chart(db, "IPE2"), "B", 70, emp="E2")

        rows = client.get("/practicelab/analytics/by-batch", params={"scope": "all"}).json()
        assert len(rows) == 2
        for row in rows:
            r = client.get(f"/practicelab/batches/{row['batch_id']}/insights/report.pdf")
            assert r.status_code == 200, f"{row['batch_name']} is listed but its report {r.status_code}s"

    def test_a_batch_with_nothing_graded_is_neither_listed_nor_reportable(self, client, db):
        b = _batch(db, "Nothing Yet")
        assert client.get("/practicelab/analytics/by-batch").json() == []
        assert client.get(f"/practicelab/batches/{b.id}/insights/report.pdf").status_code == 404


class TestDirectAssignmentWithPracticeResults:
    """
    The remaining 500, and the one the earlier fix missed.

    Fixing the EMPTY practice_results case left the non-empty one untouched:
    a direct assignment that DID have practice_results built lightweight shim
    objects carrying only total_score, pass_fail, feedback and chart. The
    report then asked each row for coder_name and chart_id, neither of which
    existed, and the endpoint raised AttributeError.
    """

    def _direct_with_practice_results(self, db, name="Direct Practice"):
        from sqlalchemy import text
        b = Batch(name=name, specialty=Specialty.IP_DRG, status=BatchStatus.OPEN,
                  created_by="t", charts_per_coder=1, is_direct_assignment=True,
                  use_weighted=True, use_dpo=False, force_closed=False)
        db.add(b); db.commit()
        c = _chart(db, f"IPP{b.id}")
        db.execute(text(
            "INSERT INTO practice_sessions (batch_id, coder_name, specialty, token, "
            "chart_ids, status) VALUES (:b, 'Asha R', 'IP_DRG', :tok, '[]', 'submitted')"
        ), {"b": b.id, "tok": f"TOK{b.id}"})
        sid = db.execute(text("SELECT id FROM practice_sessions WHERE batch_id = :b"),
                         {"b": b.id}).scalar()
        db.execute(text(
            "INSERT INTO practice_results (session_id, chart_id, total_score, pass_fail, "
            "feedback) VALUES (:s, :c, 88, 'PASS', '[]')"
        ), {"s": sid, "c": c.id})
        db.commit()
        return b

    def test_the_report_renders(self, client, db):
        b = self._direct_with_practice_results(db)
        _pdf(client, b.id)

    def test_the_coder_breakdown_survives(self, client, db):
        """coder_name came from the session; without it the endpoint crashed."""
        b = self._direct_with_practice_results(db, "Named Coder")
        body = client.get(f"/practicelab/batches/{b.id}/insights").json()
        assert body["has_data"] is True
        assert any(c["coder_name"] == "Asha R" for c in body["coder_insights"])

    def test_grading_results_win_when_both_stores_have_rows(self, client, db):
        """
        Practice work is mirrored into grading_results, so both stores can hold
        the same batch. The ORM rows are complete; the shim is not. Preferring
        the shim was the whole cause, so the order is worth pinning.
        """
        b = self._direct_with_practice_results(db, "Both Stores")
        c = _chart(db, "IPBOTH")
        _result(db, b, c, "Asha R", 88)
        body = client.get(f"/practicelab/batches/{b.id}/insights").json()
        assert body["has_data"] is True
        _pdf(client, b.id)
