"""
A closed batch is the record — nothing may silently change a graded result in one.

Only /results/{id}/drg-decision and /batches/{id}/grade-ed enforced this. DRG
review, ED rubric scoring and session re-grade all wrote to closed batches
without comment, so a closed batch's numbers could move afterwards with no
signal. This is the same shape as the rubric-specialty gap: a rule applied at
some of the endpoints that touch a concept, not all of them.

Reopen exists because force-close can close a batch with work outstanding, so a
one-way freeze would strand it.
"""
import json
import pytest
from sqlalchemy import text

from models import Chart, Batch, Specialty, GradingResult, PassFail
from models.charts import ChartStatus, Difficulty
from models.practicelab import BatchStatus

PASSPHRASE = "test-passphrase"   # conftest sets MASTER_ADMIN_PASSPHRASE to this


def _chart(db, number, specialty=Specialty.IP_DRG):
    c = Chart(chart_number=number, specialty=specialty, category="Misc",
              difficulty=Difficulty.BEGINNER, status=ChartStatus.ACTIVE,
              uploaded_by="t", view_count=0)
    db.add(c); db.commit()
    return c


def _batch(db, name, specialty=Specialty.IP_DRG, status=BatchStatus.CLOSED):
    b = Batch(name=name, specialty=specialty, status=status, created_by="t",
              charts_per_coder=1, is_direct_assignment=False,
              use_weighted=True, use_dpo=False, force_closed=False)
    db.add(b); db.commit()
    return b


def _session(db, batch, chart, coder="Asha R", specialty="IP-DRG"):
    db.execute(text("""INSERT INTO practice_sessions
        (batch_id, coder_name, specialty, token, chart_ids, status, submitted_at)
        VALUES (:b,:n,:sp,:t,:ci,'submitted','2026-08-01 10:00:00')"""),
        {"b": batch.id, "n": coder, "sp": specialty,
         "t": f"TOK{batch.id}{chart.id}", "ci": json.dumps([chart.id])})
    db.commit()
    sid = db.execute(text("SELECT id FROM practice_sessions WHERE batch_id=:b"),
                     {"b": batch.id}).fetchone()[0]
    db.execute(text("""INSERT INTO practice_results
        (session_id, chart_id, specialty, total_score, pass_fail, drg_flag, feedback)
        VALUES (:s,:c,:sp,60,'FAIL',TRUE,'[]')"""),
        {"s": sid, "c": chart.id, "sp": specialty})
    db.execute(text("""INSERT INTO practice_chart_drafts
        (session_id, chart_id, pdx_code, sdx, pcs, cpt, flagged)
        VALUES (:s,:c,'J18.9','[]','[]','[]',FALSE)"""), {"s": sid, "c": chart.id})
    db.commit()
    return sid


class TestClosedBatchesRefuseResultChanges:
    def test_session_regrade_is_refused(self, client, db):
        b, c = _batch(db, "Closed A"), _chart(db, "IP800")
        sid = _session(db, b, c)
        r = client.post(f"/practicelab/practice-sessions/{sid}/regrade")
        assert r.status_code == 409
        assert "closed" in str(r.json()["detail"]).lower()

    def test_drg_review_is_refused(self, client, db):
        b, c = _batch(db, "Closed B"), _chart(db, "IP801")
        sid = _session(db, b, c)
        r = client.post(
            f"/practicelab/practice-sessions/{sid}/chart/{c.id}/drg-review",
            json={"drg_error": True, "reviewer": "trainer"})
        assert r.status_code == 409

    def test_ed_rubric_scoring_is_refused(self, client, db):
        b = _batch(db, "Closed C", specialty=Specialty.DENIALS)
        c = _chart(db, "DEN800", Specialty.DENIALS)
        sid = _session(db, b, c, specialty="Denials")
        r = client.post(
            f"/practicelab/practice-sessions/{sid}/chart/{c.id}/score-ed",
            json={"review_pass": True, "research_coding_pass": True,
                  "research_payer_pass": True, "research_nuances_pass": True,
                  "resolution_pass": True, "rationale_tier": "Complete",
                  "graded_by": "trainer"})
        assert r.status_code == 409

    def test_the_score_is_actually_unchanged(self, client, db):
        b, c = _batch(db, "Closed D"), _chart(db, "IP802")
        sid = _session(db, b, c)
        client.post(f"/practicelab/practice-sessions/{sid}/regrade")
        score = db.execute(text(
            "SELECT total_score FROM practice_results WHERE session_id=:s"),
            {"s": sid}).fetchone()[0]
        assert score == 60, "a refused call must not partially write"


class TestOpenBatchesAreUnaffected:
    def test_regrade_allowed_while_open(self, client, db):
        b, c = _batch(db, "Open A", status=BatchStatus.OPEN), _chart(db, "IP810")
        sid = _session(db, b, c)
        r = client.post(f"/practicelab/practice-sessions/{sid}/regrade")
        assert r.status_code == 200, r.text

    def test_standalone_drg_review_records_decision(self, client, db):
        b, c = _batch(db, "Open DRG", status=BatchStatus.OPEN), _chart(db, "IP811")
        gr = GradingResult(
            batch_id=b.id, coder_name="Asha R", chart_id=c.id,
            specialty=Specialty.IP_DRG, pdx_score=20, sdx_score=20,
            pcs_score=20, total_score=60, pass_fail=PassFail.FAIL,
            drg_flag=True, drg_reviewed=False,
        )
        db.add(gr); db.commit()

        r = client.post(f"/practicelab/results/{gr.id}/drg-decision",
                        json={"drg_error": False, "reviewer": "Trainer"})

        assert r.status_code == 200, r.text
        assert r.json()["total_score"] == 100
        db.expire_all()
        saved = db.query(GradingResult).filter(GradingResult.id == gr.id).first()
        assert saved.drg_reviewed is True
        assert saved.drg_reviewed_by == "Trainer"
        assert saved.pass_fail == PassFail.PASS

    def test_standalone_drg_review_syncs_released_coder_results(self, client, db):
        b, c = _batch(db, "Open DRG Sync", status=BatchStatus.OPEN), _chart(db, "IP812")
        sid = _session(db, b, c)
        gr = GradingResult(
            batch_id=b.id, coder_name="Asha R", chart_id=c.id,
            specialty=Specialty.IP_DRG, pdx_score=20, sdx_score=20,
            pcs_score=20, total_score=60, pass_fail=PassFail.FAIL,
            drg_flag=True, drg_reviewed=False,
        )
        db.add(gr); db.commit()

        r = client.post(f"/practicelab/results/{gr.id}/drg-decision",
                        json={"drg_error": False, "reviewer": "Trainer"})

        assert r.status_code == 200, r.text
        released = db.execute(text("""
            SELECT total_score, pass_fail, drg_reviewed, drg_override
            FROM practice_results WHERE session_id=:s AND chart_id=:c
        """), {"s": sid, "c": c.id}).fetchone()
        assert released == (100, "PASS", True, "N")

    def test_session_drg_review_syncs_reporting_results(self, client, db):
        b, c = _batch(db, "Open Session DRG Sync", status=BatchStatus.OPEN), _chart(db, "IP813")
        sid = _session(db, b, c)
        db.execute(text("""
            UPDATE practice_results SET total_score=100, pass_fail='PASS'
            WHERE session_id=:s AND chart_id=:c
        """), {"s": sid, "c": c.id})
        gr = GradingResult(
            batch_id=b.id, coder_name="Asha R", chart_id=c.id,
            specialty=Specialty.IP_DRG, pdx_score=20, sdx_score=20,
            pcs_score=20, drg_score=40, total_score=100, pass_fail=PassFail.PASS,
            drg_flag=True, drg_reviewed=False,
        )
        db.add(gr); db.commit()

        r = client.post(
            f"/practicelab/practice-sessions/{sid}/chart/{c.id}/drg-review",
            json={"drg_error": True, "reviewed_by": "Trainer"})

        assert r.status_code == 200, r.text
        db.expire_all()
        saved = db.query(GradingResult).filter(GradingResult.id == gr.id).first()
        assert saved.drg_reviewed is True
        assert saved.drg_override == "Y"
        assert saved.drg_score == 0
        assert saved.total_score == 60


class TestReopen:
    """force-close can close a batch with work outstanding — without a way back
    that work is stranded, so the freeze needs an escape hatch."""

    def test_reopen_requires_the_master_passphrase(self, client, db):
        b = _batch(db, "Closed E")
        r = client.post(f"/practicelab/batches/{b.id}/reopen",
                        json={"reopened_by": "trainer", "passphrase": "wrong"})
        assert r.status_code == 403

    def test_reopen_restores_open_status(self, client, db):
        b = _batch(db, "Closed F")
        r = client.post(f"/practicelab/batches/{b.id}/reopen",
                        json={"reopened_by": "trainer", "passphrase": PASSPHRASE,
                              "reason": "late DRG review"})
        assert r.status_code == 200
        db.expire_all()
        assert db.query(Batch).filter(Batch.id == b.id).first().status == BatchStatus.OPEN

    def test_reopening_unblocks_the_write(self, client, db):
        b, c = _batch(db, "Closed G"), _chart(db, "IP820")
        sid = _session(db, b, c)
        assert client.post(f"/practicelab/practice-sessions/{sid}/regrade").status_code == 409
        client.post(f"/practicelab/batches/{b.id}/reopen",
                    json={"reopened_by": "trainer", "passphrase": PASSPHRASE})
        assert client.post(f"/practicelab/practice-sessions/{sid}/regrade").status_code == 200

    def test_reopen_is_recorded_in_the_batch_notes(self, client, db):
        b = _batch(db, "Closed H")
        client.post(f"/practicelab/batches/{b.id}/reopen",
                    json={"reopened_by": "Priya", "passphrase": PASSPHRASE,
                          "reason": "missed a chart"})
        db.expire_all()
        notes = db.query(Batch).filter(Batch.id == b.id).first().notes or []
        assert any("Reopened by Priya" in n.get("text", "") for n in notes)

    def test_cannot_reopen_an_open_batch(self, client, db):
        b = _batch(db, "Open B", status=BatchStatus.OPEN)
        r = client.post(f"/practicelab/batches/{b.id}/reopen",
                        json={"reopened_by": "trainer", "passphrase": PASSPHRASE})
        assert r.status_code == 400


class TestTheCoderTokenExpiresWithTheBatch:
    """
    Closing a batch is what ends a coder's session, rather than a clock.

    Practice tokens have no expiry column and never have. A timer would be the
    obvious fix and the wrong one: tokens are handed out days before the work,
    a batch runs for days rather than a sitting, and any duration would either
    fire mid-batch or be so long it protected nothing. Closing is a deliberate
    trainer action that already means "the work is done", so it is the honest
    place to end access.

    Only the trainer-side writes enforced this. The coder's own submit did not,
    so a token could still write results into a batch whose results had already
    become the record.
    """

    def _open_session(self, db):
        """A session on an OPEN batch, not yet submitted."""
        b = _batch(db, "Still open", status=BatchStatus.OPEN)
        c = _chart(db, "IPX01")
        db.execute(text("""INSERT INTO practice_sessions
            (batch_id, coder_name, specialty, token, chart_ids, status)
            VALUES (:b,:n,'IP-DRG',:t,:ci,'in_progress')"""),
            {"b": b.id, "n": "Asha R", "t": f"OPEN{b.id}", "ci": json.dumps([c.id])})
        db.commit()
        sid = db.execute(text(
            "SELECT id FROM practice_sessions WHERE batch_id=:b"), {"b": b.id}).fetchone()[0]
        return b, c, sid

    def _submit(self, client, sid, chart_id):
        return client.post(f"/practicelab/practice-sessions/{sid}/submit", json={
            "entries": [{"chart_id": chart_id, "pdx_code": "J18.9", "pdx_poa": "Y",
                         "sdx": [], "pcs": [], "cpt": []}]})

    def test_a_coder_can_submit_while_the_batch_is_open(self, client, db):
        """The control. Without it the test below passes for the wrong reason."""
        b, c, sid = self._open_session(db)
        assert self._submit(client, sid, c.id).status_code == 200

    def test_a_coder_cannot_submit_once_the_batch_is_closed(self, client, db):
        b, c, sid = self._open_session(db)
        db.execute(text("UPDATE batches SET status='CLOSED' WHERE id=:b"), {"b": b.id})
        db.commit()
        r = self._submit(client, sid, c.id)
        assert r.status_code == 409, r.text
        assert "closed" in r.text.lower()

    def test_closing_does_not_take_away_the_coders_own_results(self, client, db):
        """
        The write is what ends, not the reading.

        A coder who can no longer see how they did has lost the point of the
        exercise, so an expired token must still open its own feedback. This is
        the half that stops the change being an annoyance.
        """
        b, c, sid = self._open_session(db)
        assert self._submit(client, sid, c.id).status_code == 200
        db.execute(text("UPDATE batches SET status='CLOSED' WHERE id=:b"), {"b": b.id})
        db.commit()
        token = db.execute(text(
            "SELECT token FROM practice_sessions WHERE id=:s"), {"s": sid}).fetchone()[0]
        r = client.get(f"/practicelab/practice-sessions/by-token/{token}")
        assert r.status_code == 200, r.text
        assert r.json()["status"] == "submitted"
