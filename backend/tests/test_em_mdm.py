"""
E/M MDM breakdown.

Its defining constraint used to be the batch id in the URL: every question
about E/M was a per-batch question, and nothing about the specialty as a whole
could be asked. Nothing in the aggregation required that — the batch was in the
WHERE clause, not the maths.
"""
import json

import pytest
from sqlalchemy import text

from models import Chart, Batch, Specialty
from models.charts import ChartStatus, Difficulty
from models.practicelab import BatchStatus

CUM = "/practicelab/analytics/em-mdm"


def _chart(db, n, sp=Specialty.EM):
    c = Chart(chart_number=n, specialty=sp, category="Office Visit",
              difficulty=Difficulty.BEGINNER, status=ChartStatus.ACTIVE,
              uploaded_by="t", view_count=0)
    db.add(c); db.commit()
    return c


def _batch(db, name, sp=Specialty.EM):
    b = Batch(name=name, specialty=sp, status=BatchStatus.OPEN, created_by="t",
              charts_per_coder=1, is_direct_assignment=False,
              use_weighted=True, use_dpo=False, force_closed=False)
    db.add(b); db.commit()
    return b


def _session(db, b, coder, emp=None, token=None):
    db.execute(text(
        "INSERT INTO practice_sessions (batch_id, coder_name, specialty, token, chart_ids, status) "
        "VALUES (:b, :c, 'EM', :tok, '[]', 'submitted')"
    ), {"b": b.id, "c": coder, "tok": token or f"T{b.id}{coder}"})
    if emp:
        db.execute(text("INSERT INTO batch_coders (batch_id, coder_name, emp_id) "
                        "VALUES (:b, :c, :e)"), {"b": b.id, "c": coder, "e": emp})
    db.commit()
    return db.execute(text("SELECT id FROM practice_sessions WHERE token = :t"),
                      {"t": token or f"T{b.id}{coder}"}).scalar()


def _result(db, sid, chart, total, feedback, spec="E/M"):
    db.execute(text(
        "INSERT INTO practice_results (session_id, chart_id, total_score, pass_fail, "
        "feedback, specialty) VALUES (:s, :c, :t, :p, :f, :sp)"
    ), {"s": sid, "c": chart.id, "t": total, "p": "PASS" if total >= 80 else "FAIL",
        "f": json.dumps(feedback), "sp": spec})
    db.commit()


def _fb(copa=10.0, dr=10.0, risk=10.0, copa_ok=True, dr_ok=True, risk_ok=True,
        level_ok=True):
    """
    Feedback in the shape grading actually writes it.

    Two things matter and both are easy to get wrong: the section names are
    "Coding Accuracy" and "Reasoning Accuracy", and a component counts as
    MATCHED when ak_code equals coder_code — not from the text of the label.
    """
    def row(label, pts, ok):
        return {"section": "Reasoning Accuracy",
                "issue": f"{label} (Moderate) — {pts} pts",
                "ak_code": "Moderate",
                "coder_code": "Moderate" if ok else "Low"}
    return [
        row("COPA", copa, copa_ok),
        row("Data Review", dr, dr_ok),
        row("Risk", risk, risk_ok),
        {"section": "Coding Accuracy", "issue": "E/M Level (99213) — 20 pts",
         "ak_code": "99213", "coder_code": "99213" if level_ok else "99214"},
    ]


class TestCumulative:
    def test_it_spans_every_batch(self, client, db):
        """The question the tab could not previously ask."""
        for i in (1, 2):
            b = _batch(db, f"EM Batch {i}")
            sid = _session(db, b, f"Coder {i}", f"E{i}")
            _result(db, sid, _chart(db, f"EM{i}"), 80, _fb())
        body = client.get(CUM).json()
        assert body["has_data"] is True
        assert body["team"]["chart_count"] == 2

    def test_a_single_batch_is_still_reachable(self, client, db):
        b1, b2 = _batch(db, "One"), _batch(db, "Two")
        _result(db, _session(db, b1, "A", "E1"), _chart(db, "EM1"), 80, _fb())
        _result(db, _session(db, b2, "B", "E2"), _chart(db, "EM2"), 60, _fb())
        one = client.get(f"/practicelab/practice-sessions/batch/{b1.id}/em-breakdown").json()
        assert one["team"]["chart_count"] == 1

    def test_ed_profee_is_included_alongside_em(self, client, db):
        """Both share the MDM structure, so the cumulative view holds a mix —
        and has to say which specialties are in it."""
        b = _batch(db, "Mixed")
        sid = _session(db, b, "A", "E1")
        _result(db, sid, _chart(db, "EM9"), 80, _fb())
        _result(db, sid, _chart(db, "EDP1", Specialty.ED_PROFEE), 70, _fb(), spec="ED Profee")
        body = client.get(CUM).json()
        assert body["team"]["chart_count"] == 2
        assert set(body["specialties"]) == {"E/M", "ED Profee"}

    def test_the_specialty_filter_narrows_it(self, client, db):
        b = _batch(db, "Mixed")
        sid = _session(db, b, "A", "E1")
        _result(db, sid, _chart(db, "EM8"), 80, _fb())
        _result(db, sid, _chart(db, "EDP2", Specialty.ED_PROFEE), 70, _fb(), spec="ED Profee")
        body = client.get(CUM, params={"specialty": "ED Profee"}).json()
        assert body["team"]["chart_count"] == 1
        assert body["specialties"] == ["ED Profee"]


class TestIdentity:
    def test_a_coder_is_one_row_across_batches(self, client, db):
        """
        Keyed on the typed name, one person appeared twice — and on a
        per-coder table that reads as two people each doing half the work.
        """
        for i, name in enumerate(("Asha R", "asha  r")):
            b = _batch(db, f"B{i}")
            sid = _session(db, b, name, "E1", token=f"TOK{i}")
            _result(db, sid, _chart(db, f"EMI{i}"), 80, _fb())
        body = client.get(CUM).json()
        assert len(body["coders"]) == 1
        assert body["coders"][0]["chart_count"] == 2
        assert body["coders"][0]["emp_id"] == "E1"


class TestConfigDrift:
    def test_the_reasoning_maximum_comes_from_config(self, client, db):
        """
        "Right code, wrong reasoning" compared against a hardcoded 15 — half of
        an assumed 30. Change the config and the count silently means something
        else.
        """
        b = _batch(db, "B")
        _result(db, _session(db, b, "A", "E1"), _chart(db, "EMC1"), 80, _fb())
        body = client.get(CUM).json()
        assert body["reasoning_max"] > 0
        assert "pass_threshold" in body


class TestWeakestComponent:
    def test_the_weakest_reasoning_component_is_named(self, client, db):
        """Three percentages are already on screen; naming the lowest is the
        step a reader takes next, and what a session gets built around."""
        b = _batch(db, "B")
        sid = _session(db, b, "A", "E1")
        for i in range(4):
            _result(db, sid, _chart(db, f"EMW{i}"), 70,
                    _fb(copa=0.0, copa_ok=False))
        w = client.get(CUM).json()["weakest_component"]
        assert w["component"] == "COPA"
        assert w["match_pct"] <= w["strongest_pct"]


class TestEmpty:
    def test_no_em_work_is_not_an_error(self, client):
        body = client.get(CUM).json()
        assert body["has_data"] is False
        assert body["coders"] == []
