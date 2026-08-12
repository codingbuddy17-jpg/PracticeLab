"""
A physician query is the coder saying the record cannot be coded as documented.

Inpatient coders raise queries constantly in real work, and the form had no way
to express it — the judgement was either lost or buried in free-text notes that
nothing distinguished from "this chart was confusing". Making it a stored flag
gives the trainer something to review, the same way a DRG flag is reviewed.

Two rules this file pins down:

  * The query text lives in coder_notes. A raised query with no text written is
    not reviewable, so the coder form blocks that submission — but the flag and
    the text must survive the round trip through drafts and into the result.
  * The trainer's verdict is recorded, and it does NOT move the score. There is
    no query component in scoring_configs, so awarding or withholding points
    here would silently change what every existing IP score means.
"""
import json
import pytest
from sqlalchemy import text

from models import Chart, Batch, Specialty
from models.charts import ChartStatus, Difficulty
from models.practicelab import BatchStatus


def _chart(db, number):
    c = Chart(chart_number=number, specialty=Specialty.IP_DRG, category="Misc",
              difficulty=Difficulty.BEGINNER, status=ChartStatus.ACTIVE,
              uploaded_by="t", view_count=0)
    db.add(c); db.commit()
    return c


def _batch(db, name, status=BatchStatus.OPEN):
    b = Batch(name=name, specialty=Specialty.IP_DRG, status=status, created_by="t",
              charts_per_coder=1, is_direct_assignment=False,
              use_weighted=True, use_dpo=False, force_closed=False)
    db.add(b); db.commit()
    return b


def _session(db, batch, chart, coder="Asha R"):
    db.execute(text("""INSERT INTO practice_sessions
        (batch_id, coder_name, specialty, token, chart_ids, status)
        VALUES (:b,:n,'IP-DRG',:t,:ci,'in_progress')"""),
        {"b": batch.id, "n": coder, "t": f"QTOK{batch.id}{chart.id}",
         "ci": json.dumps([chart.id])})
    db.commit()
    return db.execute(text("SELECT id FROM practice_sessions WHERE batch_id=:b"),
                      {"b": batch.id}).fetchone()[0]


def _entry(chart_id, **kw):
    base = {
        "chart_id": chart_id, "pdx_code": "J18.9", "pdx_poa": "Y",
        "sdx": [], "pcs": [], "cpt": [], "flagged": False,
        "coder_notes": "", "query_flag": False,
    }
    base.update(kw)
    return base


@pytest.fixture()
def setup(db):
    chart = _chart(db, "QRY001")
    batch = _batch(db, "Query batch")
    sid = _session(db, batch, chart)
    return batch, chart, sid


# ── the flag survives the round trip ─────────────────────────────────────────

class TestQueryPersistence:

    def test_a_raised_query_and_its_text_come_back_on_reload(self, client, db, setup):
        """
        The coder saves, closes the tab, and reopens the token. Losing the query
        flag here would silently downgrade the chart to an ordinary submission.
        """
        _batch_, chart, sid = setup
        r = client.post(f"/practicelab/practice-sessions/{sid}/save-draft", json={
            "entries": [_entry(chart.id, query_flag=True,
                               coder_notes="Sepsis documented without organ dysfunction — please clarify.")],
        })
        assert r.status_code == 200, r.text

        token = db.execute(text("SELECT token FROM practice_sessions WHERE id=:s"),
                           {"s": sid}).fetchone()[0]
        got = client.get(f"/practicelab/practice-sessions/by-token/{token}")
        assert got.status_code == 200, got.text
        draft = got.json()["drafts"][str(chart.id)]
        assert draft["query_flag"] is True
        assert "organ dysfunction" in draft["coder_notes"]

    def test_no_query_is_the_default_shape(self, client, db, setup):
        """An entry that never mentions query_flag must not arrive as queried."""
        _batch_, chart, sid = setup
        payload = _entry(chart.id)
        payload.pop("query_flag")
        r = client.post(f"/practicelab/practice-sessions/{sid}/save-draft",
                        json={"entries": [payload]})
        assert r.status_code == 200, r.text
        flag = db.execute(text(
            "SELECT query_flag FROM practice_chart_drafts WHERE session_id=:s"
        ), {"s": sid}).fetchone()[0]
        assert not flag

    def test_the_flag_reaches_the_graded_result(self, client, db, setup):
        """
        Drafts are working state; practice_results is what the trainer reads.
        A flag that stops at the draft table is invisible to the review screen.
        """
        _batch_, chart, sid = setup
        r = client.post(f"/practicelab/practice-sessions/{sid}/submit", json={
            "entries": [_entry(chart.id, query_flag=True, coder_notes="Please clarify.")],
        })
        assert r.status_code == 200, r.text
        flag = db.execute(text(
            "SELECT query_flag FROM practice_results WHERE session_id=:s"
        ), {"s": sid}).fetchone()[0]
        assert flag


# ── the trainer's verdict ────────────────────────────────────────────────────

class TestQueryReview:

    def _submit_queried(self, client, chart, sid):
        return client.post(f"/practicelab/practice-sessions/{sid}/submit", json={
            "entries": [_entry(chart.id, query_flag=True,
                               coder_notes="Please clarify the sepsis documentation.")],
        })

    def test_trainer_records_a_verdict(self, client, db, setup):
        _batch_, chart, sid = setup
        self._submit_queried(client, chart, sid)
        r = client.post(
            f"/practicelab/practice-sessions/{sid}/chart/{chart.id}/query-review",
            json={"verdict": "appropriate", "trainer_note": "Good catch.",
                  "reviewed_by": "Trainer A"},
        )
        assert r.status_code == 200, r.text
        row = db.execute(text(
            "SELECT query_reviewed, query_verdict, query_trainer_note, query_reviewed_by "
            "FROM practice_results WHERE session_id=:s"
        ), {"s": sid}).fetchone()
        assert row[0]
        assert row[1] == "appropriate"
        assert row[2] == "Good catch."
        assert row[3] == "Trainer A"

    def test_the_verdict_does_not_move_the_score(self, client, db, setup):
        """
        Unlike the DRG decision, which is worth drg_weight. There is no query
        component to award, and inventing one here would change the meaning of
        every IP score already recorded.
        """
        _batch_, chart, sid = setup
        self._submit_queried(client, chart, sid)
        before = db.execute(text(
            "SELECT total_score, pass_fail FROM practice_results WHERE session_id=:s"
        ), {"s": sid}).fetchone()

        client.post(f"/practicelab/practice-sessions/{sid}/chart/{chart.id}/query-review",
                    json={"verdict": "not_warranted"})

        after = db.execute(text(
            "SELECT total_score, pass_fail FROM practice_results WHERE session_id=:s"
        ), {"s": sid}).fetchone()
        assert (after[0], after[1]) == (before[0], before[1])

    def test_an_unknown_verdict_is_refused(self, client, setup):
        _batch_, chart, sid = setup
        self._submit_queried(client, chart, sid)
        r = client.post(
            f"/practicelab/practice-sessions/{sid}/chart/{chart.id}/query-review",
            json={"verdict": "looks_fine_to_me"},
        )
        assert r.status_code == 400

    def test_a_chart_with_no_query_cannot_be_query_reviewed(self, client, setup):
        """
        Otherwise the review screen could manufacture a query decision on a
        chart where the coder never raised one.
        """
        _batch_, chart, sid = setup
        client.post(f"/practicelab/practice-sessions/{sid}/submit",
                    json={"entries": [_entry(chart.id)]})
        r = client.post(
            f"/practicelab/practice-sessions/{sid}/chart/{chart.id}/query-review",
            json={"verdict": "appropriate"},
        )
        assert r.status_code == 400

    def test_a_closed_batch_refuses_a_query_decision(self, client, db, setup):
        """Same freeze that guards DRG review and rubric scoring."""
        batch, chart, sid = setup
        self._submit_queried(client, chart, sid)
        batch.status = BatchStatus.CLOSED
        db.commit()
        r = client.post(
            f"/practicelab/practice-sessions/{sid}/chart/{chart.id}/query-review",
            json={"verdict": "appropriate"},
        )
        assert r.status_code == 409

    def test_the_batch_header_counts_only_charts_a_coder_queried(self, client, db, setup):
        """
        The counter must be a count of raised queries, not of charts. A batch
        where nobody raised one has to read zero — a "pending" badge on every
        IP batch would train trainers to ignore it.
        """
        batch, chart, sid = setup

        # A second chart in the same session, submitted with no query raised.
        other = _chart(db, "QRY002")
        db.execute(text("UPDATE practice_sessions SET chart_ids=:ci WHERE id=:s"),
                   {"ci": json.dumps([chart.id, other.id]), "s": sid})
        db.commit()
        client.post(f"/practicelab/practice-sessions/{sid}/submit", json={
            "entries": [
                _entry(chart.id, query_flag=True, coder_notes="Please clarify."),
                _entry(other.id),
            ],
        })

        r = client.get(f"/practicelab/batches/{batch.id}")
        assert r.status_code == 200, r.text
        assert r.json()["pending_query_review"] == 1

        # Once reviewed it drops out of the pending count.
        client.post(f"/practicelab/practice-sessions/{sid}/chart/{chart.id}/query-review",
                    json={"verdict": "appropriate"})
        r = client.get(f"/practicelab/batches/{batch.id}")
        assert r.json()["pending_query_review"] == 0

    def test_a_batch_with_no_queries_reports_zero(self, client, db, setup):
        batch, chart, sid = setup
        client.post(f"/practicelab/practice-sessions/{sid}/submit",
                    json={"entries": [_entry(chart.id)]})
        r = client.get(f"/practicelab/batches/{batch.id}")
        assert r.status_code == 200, r.text
        assert r.json()["pending_query_review"] == 0

    def test_the_review_screen_shows_the_query_and_its_verdict(self, client, setup):
        """
        The trainer reads this through the batch review payload, not the DB.
        A field that never reaches the payload cannot be acted on.
        """
        batch, chart, sid = setup
        self._submit_queried(client, chart, sid)
        client.post(f"/practicelab/practice-sessions/{sid}/chart/{chart.id}/query-review",
                    json={"verdict": "poorly_framed", "trainer_note": "Leading question."})

        r = client.get(f"/practicelab/practice-sessions/{sid}/review")
        assert r.status_code == 200, r.text
        chart_row = r.json()["charts"][0]
        assert chart_row["query_flag"] is True
        assert chart_row["query_reviewed"] is True
        assert chart_row["query_verdict"] == "poorly_framed"
        assert chart_row["query_trainer_note"] == "Leading question."
        assert "clarify" in (chart_row["coder_notes"] or "")
