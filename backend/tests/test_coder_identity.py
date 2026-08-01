"""
Coder identity.

coder_name is free text, so it is not a safe key: spelling variants fork one
person's history and two people sharing a name merge into one. emp_id is the
stable identity; name remains a fallback for coders enrolled without one.
"""
import pytest
from sqlalchemy import text

from models import Chart, Batch, Specialty, GradingResult, BatchCoder, PassFail
from models.charts import ChartStatus, Difficulty
from models.practicelab import BatchStatus
from routers.practicelab_pkg.analytics import _coder_filter, list_coders


def _chart(db, number):
    c = Chart(chart_number=number, specialty=Specialty.SDS, category="Ortho",
              difficulty=Difficulty.BEGINNER, status=ChartStatus.ACTIVE,
              uploaded_by="t", view_count=0)
    db.add(c); db.commit()
    return c


def _batch(db, name, status=BatchStatus.OPEN, direct=False):
    b = Batch(name=name, specialty=Specialty.SDS, status=status, created_by="t",
              charts_per_coder=1, is_direct_assignment=direct,
              use_weighted=True, use_dpo=False, force_closed=False)
    db.add(b); db.commit()
    return b


def _result(db, batch, chart, coder_name, emp_id, score=90):
    r = GradingResult(batch_id=batch.id, submission_id=None, coder_name=coder_name,
                      emp_id=emp_id, chart_id=chart.id, specialty=Specialty.SDS,
                      total_score=score,
                      pass_fail=PassFail.PASS if score >= 80 else PassFail.FAIL)
    db.add(r); db.commit()
    return r


class TestEmpIdIsTheIdentity:
    def test_name_variants_resolve_to_one_person_by_emp_id(self, db):
        """The exact failure the string key produced: three spellings, one coder."""
        b, c = _batch(db, "B1"), _chart(db, "SDS001")
        for spelling in ("John Smith", "john smith", "Smith, John"):
            _result(db, b, _chart(db, f"SDS_{spelling[:4]}_{len(spelling)}"),
                    spelling, "E1042")

        by_emp = _coder_filter(db.query(GradingResult), None, "E1042").all()
        assert len(by_emp) == 3, "emp_id must gather every spelling"

        by_name = _coder_filter(db.query(GradingResult), "John Smith", None).all()
        assert len(by_name) == 1, "name alone sees only its own spelling"

    def test_two_people_sharing_a_name_stay_separate(self, db):
        b = _batch(db, "B2")
        _result(db, b, _chart(db, "SDS010"), "A Patel", "E100", score=95)
        _result(db, b, _chart(db, "SDS011"), "A Patel", "E200", score=40)

        assert len(_coder_filter(db.query(GradingResult), None, "E100").all()) == 1
        assert len(_coder_filter(db.query(GradingResult), None, "E200").all()) == 1
        # ...whereas the name alone conflates them
        assert len(_coder_filter(db.query(GradingResult), "A Patel", None).all()) == 2

    def test_falls_back_to_name_when_no_emp_id(self, db):
        b = _batch(db, "B3")
        _result(db, b, _chart(db, "SDS020"), "No Id", None)
        assert len(_coder_filter(db.query(GradingResult), "No Id", None).all()) == 1


class TestCoderDirectory:
    def test_includes_coders_from_open_batches(self, db):
        """
        The old picker read coder-matrix, which is restricted to CLOSED,
        non-direct batches — so anyone only in an open batch was unselectable.
        """
        b = _batch(db, "Open B", status=BatchStatus.OPEN)
        _result(db, b, _chart(db, "SDS030"), "Open Coder", "E300")
        names = [c["coder_name"] for c in list_coders(db=db)["coders"]]
        assert "Open Coder" in names

    def test_includes_coders_from_direct_assignments(self, db):
        b = _batch(db, "Direct B", direct=True)
        _result(db, b, _chart(db, "SDS031"), "Direct Coder", "E301")
        names = [c["coder_name"] for c in list_coders(db=db)["coders"]]
        assert "Direct Coder" in names

    def test_includes_roster_entries_with_no_results_yet(self, db):
        b = _batch(db, "Rostered")
        db.add(BatchCoder(batch_id=b.id, coder_name="Fresh Hire", emp_id="E400"))
        db.commit()
        rec = next(c for c in list_coders(db=db)["coders"]
                   if c["coder_name"] == "Fresh Hire")
        assert rec["emp_id"] == "E400"
        assert rec["result_count"] == 0

    def test_reports_result_counts(self, db):
        b = _batch(db, "Counting")
        for i in range(3):
            _result(db, b, _chart(db, f"SDS04{i}"), "Busy Coder", "E500")
        rec = next(c for c in list_coders(db=db)["coders"]
                   if c["emp_id"] == "E500")
        assert rec["result_count"] == 3
        assert rec["last_activity"] is not None

    def test_search_matches_name_or_emp_id(self, db):
        b = _batch(db, "Searchable")
        _result(db, b, _chart(db, "SDS050"), "Priya Nair", "E777")
        assert any(c["emp_id"] == "E777"
                   for c in list_coders(q="priya", db=db)["coders"])
        assert any(c["emp_id"] == "E777"
                   for c in list_coders(q="777", db=db)["coders"])
        assert list_coders(q="zzzz-nobody", db=db)["coders"] == []

    def test_surfaces_name_variants_for_one_emp_id(self, db):
        """A trainer should SEE the split rather than silently inherit it."""
        b = _batch(db, "Variants")
        _result(db, b, _chart(db, "SDS060"), "Meera K", "E900")
        _result(db, b, _chart(db, "SDS061"), "meera k", "E900")
        rec = next(c for c in list_coders(db=db)["coders"] if c["emp_id"] == "E900")
        assert set(rec["name_variants"]) == {"Meera K", "meera k"}


class TestBackfill:
    def test_fills_emp_id_from_the_roster(self, db, engine):
        from database import _backfill_grading_result_emp_ids
        b, c = _batch(db, "Backfill B"), _chart(db, "SDS070")
        db.add(BatchCoder(batch_id=b.id, coder_name="Legacy Coder", emp_id="E999"))
        db.commit()
        r = _result(db, b, c, "Legacy Coder", None)   # written before the column existed
        assert r.emp_id is None

        from unittest.mock import patch
        with patch("database.engine", engine):
            _backfill_grading_result_emp_ids()
        db.expire_all()
        assert db.query(GradingResult).filter(GradingResult.id == r.id).first().emp_id == "E999"
