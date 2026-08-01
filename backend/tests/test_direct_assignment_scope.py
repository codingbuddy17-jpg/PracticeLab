"""
Direct assignments are one-off charts, not formal batches.

The rule: TEAM/BATCH-level aggregates exclude them so they cannot dilute batch
counts or trends; CODER-level views include them, because a coder's record
should reflect all their work regardless of where it came from.

That split is deliberate but spread across a dozen endpoints, several of which
enforce it in a different way (an exclude_direct flag, _batch_base, an inline
filter, a direct query predicate). Nothing asserted it held at all of them.
"""
import pytest

from models import Chart, Batch, Specialty, GradingResult, PassFail
from models.charts import ChartStatus, Difficulty
from models.practicelab import BatchStatus


def _chart(db, number, category="Sepsis"):
    c = Chart(chart_number=number, specialty=Specialty.SDS, category=category,
              difficulty=Difficulty.BEGINNER, status=ChartStatus.ACTIVE,
              uploaded_by="t", view_count=0)
    db.add(c); db.commit()
    return c


def _batch(db, name, direct, status=BatchStatus.CLOSED):
    b = Batch(name=name, specialty=Specialty.SDS, status=status, created_by="t",
              charts_per_coder=1, is_direct_assignment=direct,
              use_weighted=True, use_dpo=False, force_closed=False)
    db.add(b); db.commit()
    return b


def _result(db, batch, chart, coder, score):
    r = GradingResult(batch_id=batch.id, submission_id=None, coder_name=coder,
                      emp_id="E1", chart_id=chart.id, specialty=Specialty.SDS,
                      total_score=score,
                      pass_fail=PassFail.PASS if score >= 80 else PassFail.FAIL)
    db.add(r); db.commit()
    return r


@pytest.fixture()
def seeded(db):
    """One formal batch result (100) and one direct-assignment result (0).

    Chosen so any endpoint that wrongly includes the direct one shows an
    average of 50 rather than 100 — a mistake that is impossible to misread.
    """
    formal = _batch(db, "Formal", direct=False)
    direct = _batch(db, "Direct", direct=True)
    _result(db, formal, _chart(db, "SDS100"), "Asha R", 100)
    _result(db, direct, _chart(db, "SDS101"), "Asha R", 0)
    return formal, direct


class TestTeamAggregatesExcludeDirect:
    def test_overview(self, client, seeded):
        body = client.get("/practicelab/analytics/overview").json()
        assert body["total_graded"] == 1, "direct assignment must not count as batch work"
        assert body["overall_pass_rate"] == 100.0

    def test_by_specialty(self, client, seeded):
        rows = client.get("/practicelab/analytics/by-specialty").json()
        sds = next(r for r in rows if r["specialty"] == "SDS")
        assert sds["total"] == 1
        assert sds["avg_score"] == 100.0

    def test_by_chart(self, client, seeded):
        numbers = [r["chart_number"] for r in
                   client.get("/practicelab/analytics/by-chart").json()]
        assert "SDS100" in numbers
        assert "SDS101" not in numbers

    def test_by_batch_lists_only_formal_batches(self, client, seeded):
        names = [b["batch_name"] for b in
                 client.get("/practicelab/analytics/by-batch").json()]
        assert "Formal" in names
        assert "Direct" not in names

    def test_category_team_view(self, client, seeded):
        team = client.get("/practicelab/analytics/by-category").json()["team"]
        sepsis = next((r for r in team if r["category"] == "Sepsis"), None)
        assert sepsis is not None
        assert sepsis["avg_score"] == 100.0, "direct work must not drag the team average"

    def test_coder_matrix(self, client, seeded):
        names = [b["name"] for b in
                 client.get("/practicelab/analytics/coder-matrix").json()["batches"]]
        assert "Direct" not in names

    def test_chart_detail(self, client, seeded):
        r = client.get("/practicelab/analytics/chart-detail/SDS101")
        body = r.json()
        assert not body.get("attempts"), "a direct-assignment chart has no batch history"


class TestCoderViewsIncludeDirect:
    def test_coder_summary_counts_both(self, client, seeded):
        body = client.get("/practicelab/analytics/coder-summary",
                          params={"coder_name": "Asha R"}).json()
        assert body["total_charts"] == 2, "a coder's record covers all their work"
        assert body["weighted_accuracy"] == 50.0

    def test_coder_trend_covers_both(self, client, seeded):
        rows = client.get("/practicelab/analytics/coder-trend",
                          params={"coder_name": "Asha R"}).json()
        names = [r.get("batch_name") for r in rows]
        assert "Direct" in names

    def test_category_coder_view_includes_direct(self, client, seeded):
        body = client.get("/practicelab/analytics/by-category").json()
        rows = [r for r in body["coder_category"] if r.get("coder_name") == "Asha R"]
        assert rows, "coder-level category breakdown should exist"
        assert any(r.get("charts", 0) == 2 or r.get("avg_score") == 50.0 for r in rows), \
            "coder-level view should include the direct-assignment result"

    def test_coder_directory_includes_direct_only_coders(self, client, db):
        """Someone who has ONLY ever done direct assignments must still be findable."""
        direct = _batch(db, "Direct Only", direct=True)
        _result(db, direct, _chart(db, "SDS102"), "Direct Only Coder", 70)
        names = [c["coder_name"] for c in
                 client.get("/practicelab/coders").json()["coders"]]
        assert "Direct Only Coder" in names


class TestDPOScope:
    """
    DPO is a defects-per-opportunity measure over CODES, so it only makes sense
    where the coder enters codes. E/M and ED Profee are MDM-graded and Edits and
    Denials are rubric-graded, so none of them produce DPO.

    The flag was applied at batch creation, batch detail, grading, analytics and
    the OP grading path — but not the IP one. Harmless today because every
    specialty reaching that branch is a DPO specialty; a latent trap otherwise.
    """

    def test_code_based_specialties_use_dpo(self):
        from routers.practicelab_pkg.shared import _uses_dpo
        for spec in (Specialty.IP_DRG, Specialty.ED_FACILITY, Specialty.SDS,
                     Specialty.SURGERY, Specialty.ANCILLARY, Specialty.ED_SINGLE_PATH):
            assert _uses_dpo(spec), spec

    def test_mdm_and_rubric_specialties_do_not(self):
        from routers.practicelab_pkg.shared import _uses_dpo
        for spec in (Specialty.EM, Specialty.ED_PROFEE,
                     Specialty.EDITS, Specialty.DENIALS):
            assert not _uses_dpo(spec), spec

    def test_both_grading_branches_gate_on_the_flag(self):
        """The IP branch used to compute DPO unconditionally."""
        import pathlib
        src = (pathlib.Path(__file__).resolve().parent.parent
               / "routers" / "practicelab_pkg" / "chart_grading.py").read_text()
        assert src.count("if _uses_dpo(chart.specialty):") == 2, \
            "both the IP and OP branches must gate DPO on the specialty"

    def test_batch_creation_refuses_dpo_for_a_non_dpo_specialty(self, client, db):
        r = client.post("/practicelab/batches", json={
            "name": "EM DPO", "specialty": "E/M", "categories": [], "difficulties": [],
            "charts_per_coder": 1, "coders": [{"name": "A", "emp_id": "E1"}],
            "created_by": "t", "use_weighted": True, "use_dpo": True,
        })
        # Either rejected outright, or accepted with DPO forced off — never on.
        if r.status_code == 200:
            bid = r.json().get("batch_id") or r.json().get("id")
            assert db.query(Batch).filter(Batch.id == bid).first().use_dpo is False
