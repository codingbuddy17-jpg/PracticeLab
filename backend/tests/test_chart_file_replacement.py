"""
Replacing a chart's pages keeps everything attached to the chart.

add-files only ever appended, so a chart with a problem could be corrected only
by leaving the bad pages beside the good ones, or by retiring it and
re-uploading under a new number — which means re-entering the answer key and
cutting every grading result loose from the chart it was graded on.

The case this exists for is PHI that survived de-identification. That changes
what is VISIBLE, not the clinical facts the key was written against, so past
scores stay meaningful and are deliberately not blocked. What the endpoint owes
in return is a record: the reason is required, and the audit entry says how
many results already existed.
"""
import pytest

from models import (AnswerKey, AuditLog, Batch, BatchStatus, Chart, ChartFile,
                    ChartStatus, Difficulty, GradingResult, PassFail, Specialty)

PASSPHRASE = "test-passphrase"


@pytest.fixture()
def stub_ingest(monkeypatch):
    """
    Stand in for image conversion and object storage.

    What is under test is the swap — which rows go, which stay, how the pages
    are renumbered and what is written down. Turning a PDF into PNGs is not.
    """
    import routers.upload as up
    uploaded, deleted = [], []

    def fake_ingest(db, chart_id, filename, file_bytes, uploaded_by, page_order_start=0):
        for i in range(2):                       # two pages per file
            key = "charts/%d/%04d_%s.png" % (chart_id, page_order_start + i, filename)
            db.add(ChartFile(chart_id=chart_id, storage_key=key,
                             original_filename=filename, page_order=page_order_start + i,
                             total_pages=2, uploaded_by=uploaded_by))
            uploaded.append(key)
        db.flush()
        return 2

    monkeypatch.setattr(up, "ingest_file", fake_ingest)
    monkeypatch.setattr(up, "delete_object", lambda key: deleted.append(key))
    return uploaded, deleted


def _chart_with_history(db):
    c = Chart(chart_number="IP700", specialty=Specialty.IP_DRG, category="Cardio",
              difficulty=Difficulty.INTERMEDIATE, status=ChartStatus.ACTIVE,
              uploaded_by="Trainer")
    db.add(c); db.flush()
    db.add(AnswerKey(chart_id=c.id, specialty=Specialty.IP_DRG, pdx_code="J18.9",
                     pdx_poa="Y", sdx=[], pcs=[], cpt=[], entered_by="t"))
    for i in range(3):
        db.add(ChartFile(chart_id=c.id, storage_key="charts/%d/old_%d.png" % (c.id, i),
                         original_filename="old.pdf", page_order=i, total_pages=3,
                         uploaded_by="Trainer"))
    b = Batch(name="Wave", specialty=Specialty.IP_DRG, status=BatchStatus.OPEN,
              created_by="t", charts_per_coder=1, is_direct_assignment=False,
              use_weighted=True, use_dpo=False, force_closed=False)
    db.add(b); db.flush()
    db.add(GradingResult(batch_id=b.id, coder_name="Asha", chart_id=c.id,
                         specialty=Specialty.IP_DRG, pdx_score=20, sdx_score=20,
                         pcs_score=20, total_score=60, pass_fail=PassFail.FAIL))
    db.commit()
    return c


def _post(client, chart_id, **form):
    body = {"uploaded_by": "Trainer", "reason": "PHI on page 2"}
    body.update(form)
    return client.post("/upload/%d/replace-files" % chart_id,
                       files=[("files", ("fixed.pdf", b"x", "application/pdf"))],
                       data=body)


class TestReplaceChartFiles:

    def test_a_reason_is_required(self, client, db, stub_ingest):
        c = _chart_with_history(db)
        r = _post(client, c.id, reason="   ")
        assert r.status_code == 400
        assert "reason" in r.text.lower()

    def test_someone_else_needs_the_passphrase(self, client, db, stub_ingest):
        c = _chart_with_history(db)
        assert _post(client, c.id, uploaded_by="Someone Else").status_code == 403
        assert _post(client, c.id, uploaded_by="Someone Else",
                     passphrase=PASSPHRASE).status_code == 200

    def test_the_old_pages_go_and_the_new_ones_are_numbered_from_zero(self, client, db, stub_ingest):
        c = _chart_with_history(db)
        _uploaded, deleted = stub_ingest
        r = _post(client, c.id)
        assert r.status_code == 200, r.text
        assert r.json()["pages_removed"] == 3
        assert r.json()["pages_added"] == 2

        db.expire_all()
        rows = db.query(ChartFile).filter(ChartFile.chart_id == c.id)\
                 .order_by(ChartFile.page_order).all()
        assert len(rows) == 2, "old pages survived the replacement"
        assert [x.page_order for x in rows] == [0, 1], (
            "pages must be renumbered from zero — they are ingested above the "
            "old range so a failure leaves the original pages intact")
        assert all("old_" not in x.storage_key for x in rows)

    def test_the_old_objects_are_deleted_from_storage(self, client, db, stub_ingest):
        """A chart replaced for PHI must not leave the original pages fetchable."""
        c = _chart_with_history(db)
        _uploaded, deleted = stub_ingest
        assert _post(client, c.id).status_code == 200
        assert sorted(deleted) == sorted(
            ["charts/%d/old_%d.png" % (c.id, i) for i in range(3)])

    def test_the_key_the_results_and_the_chart_number_all_survive(self, client, db, stub_ingest):
        """The whole point: replacing pages must not orphan anything."""
        c = _chart_with_history(db)
        assert _post(client, c.id).status_code == 200
        db.expire_all()
        assert db.query(Chart).filter(Chart.id == c.id).first().chart_number == "IP700"
        assert db.query(AnswerKey).filter(AnswerKey.chart_id == c.id).first() is not None
        assert db.query(GradingResult).filter(GradingResult.chart_id == c.id).count() == 1

    def test_the_audit_entry_records_the_reason_and_the_history_at_risk(self, client, db, stub_ingest):
        c = _chart_with_history(db)
        assert _post(client, c.id).status_code == 200
        entry = db.query(AuditLog).filter(AuditLog.chart_id == c.id,
                                          AuditLog.action == "REPLACE_FILES").first()
        assert entry is not None, "a replacement left no audit trail"
        assert "PHI on page 2" in entry.details
        assert "1 existing grading result" in entry.details
