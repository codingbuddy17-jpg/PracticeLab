"""
Edits and Denials are graded by a manual rubric and have NO answer key.

Every answer-key surface must say so consistently. Previously only upload and
save refused them, so the UI happily listed Denials charts as "missing a key"
and opened an OP-shaped editor that could never save — a gap that by definition
can never be closed.

Nothing covered rubric specialties across these endpoints before.
"""
import pytest

from models import Chart, Specialty, AnswerKey
from models.charts import ChartStatus, Difficulty
from routers.practicelab_pkg.shared import _is_ed

RUBRIC = [Specialty.EDITS, Specialty.DENIALS]
KEYED = [Specialty.IP_DRG, Specialty.SDS, Specialty.SURGERY, Specialty.ANCILLARY]


def _chart(db, number, specialty):
    c = Chart(chart_number=number, specialty=specialty, category="Misc",
              difficulty=Difficulty.BEGINNER, status=ChartStatus.ACTIVE,
              uploaded_by="t", view_count=0)
    db.add(c); db.commit()
    return c


class TestClassification:
    @pytest.mark.parametrize("spec", RUBRIC)
    def test_rubric_specialties_flagged(self, spec):
        assert _is_ed(spec)

    @pytest.mark.parametrize("spec", KEYED)
    def test_keyed_specialties_not_flagged(self, spec):
        assert not _is_ed(spec)


class TestMissingKeysList:
    @pytest.mark.parametrize("spec", RUBRIC)
    def test_rubric_charts_are_never_listed_as_missing_a_key(self, client, db, spec):
        _chart(db, f"{spec.name[:3]}900", spec)
        r = client.get("/practicelab/answer-key/missing", params={"specialty": spec.value})
        assert r.status_code == 200
        assert r.json() == [], "a keyless-by-design chart is not an outstanding task"

    def test_unfiltered_list_also_excludes_them(self, client, db):
        _chart(db, "DEN901", Specialty.DENIALS)
        _chart(db, "SDS901", Specialty.SDS)
        numbers = [c["chart_number"] for c in client.get("/practicelab/answer-key/missing").json()]
        assert "SDS901" in numbers
        assert "DEN901" not in numbers

    def test_keyed_specialty_still_reports_missing(self, client, db):
        _chart(db, "SDS902", Specialty.SDS)
        r = client.get("/practicelab/answer-key/missing", params={"specialty": "SDS"})
        assert any(c["chart_number"] == "SDS902" for c in r.json())


class TestStatusCounts:
    @pytest.mark.parametrize("spec", RUBRIC)
    def test_status_reports_no_outstanding_keys(self, client, db, spec):
        _chart(db, f"{spec.name[:3]}910", spec)
        body = client.get("/practicelab/answer-key/status",
                          params={"specialty": spec.value}).json()
        assert body["without_answer_key"] == 0
        assert body["uses_answer_keys"] is False

    def test_keyed_specialty_reports_normally(self, client, db):
        _chart(db, "SDS910", Specialty.SDS)
        body = client.get("/practicelab/answer-key/status",
                          params={"specialty": "SDS"}).json()
        assert body["without_answer_key"] >= 1
        assert body["uses_answer_keys"] is True


class TestEditorCannotBeOpened:
    @pytest.mark.parametrize("spec", RUBRIC)
    def test_detail_is_refused(self, client, db, spec):
        """
        This is what let the OP-shaped form open for a Denials chart: the
        editor fetches /detail, which had no rubric guard.
        """
        c = _chart(db, f"{spec.name[:3]}920", spec)
        r = client.get(f"/practicelab/answer-key/{c.id}/detail")
        assert r.status_code == 400
        assert "rubric" in r.json()["detail"].lower()

    def test_detail_works_for_a_keyed_specialty(self, client, db):
        c = _chart(db, "SDS920", Specialty.SDS)
        r = client.get(f"/practicelab/answer-key/{c.id}/detail")
        assert r.status_code == 200
        assert r.json()["exists"] is False


class TestSaveIsRefused:
    @pytest.mark.parametrize("spec", RUBRIC)
    def test_put_is_refused(self, client, db, spec):
        c = _chart(db, f"{spec.name[:3]}930", spec)
        r = client.put(f"/practicelab/answer-key/{c.id}", json={
            "pdx_code": "J18.9", "sdx": [], "pcs": [], "cpt": [],
            "entered_by": "trainer",
        })
        assert r.status_code == 400
        assert db.query(AnswerKey).filter(AnswerKey.chart_id == c.id).first() is None


class TestEMKeyStatusCountsTheRightTable:
    """
    E/M and ED Profee keys live in em_answer_keys, not answer_keys. The status
    endpoint joined answer_keys for every specialty, so it reported
    "0 with answer key" for E/M no matter how many existed.
    """

    def test_em_status_counts_em_answer_keys(self, client, db):
        from sqlalchemy import text
        c = _chart(db, "EM800", Specialty.EM)
        db.execute(text(
            "INSERT INTO em_answer_keys (chart_id, em_code, dx_codes, procedure_cpts, "
            "entered_by, copa_level, dr_level, risk_level) "
            "VALUES (:c, '99214', '[]', '[]', 'trainer', 'Moderate', 'Moderate', 'Moderate')"),
            {"c": c.id})
        db.commit()

        body = client.get("/practicelab/answer-key/status",
                          params={"specialty": "E/M"}).json()
        assert body["with_answer_key"] == 1, "must count em_answer_keys, not answer_keys"
        assert body["without_answer_key"] == 0
        assert body["key_store"] == "em"

    def test_em_chart_without_a_key_is_reported_missing(self, client, db):
        _chart(db, "EM801", Specialty.EM)
        body = client.get("/practicelab/answer-key/status",
                          params={"specialty": "E/M"}).json()
        assert body["total_charts"] >= 1
        assert body["without_answer_key"] >= 1

    def test_keyed_specialty_still_uses_the_standard_store(self, client, db):
        _chart(db, "SDS800", Specialty.SDS)
        body = client.get("/practicelab/answer-key/status",
                          params={"specialty": "SDS"}).json()
        assert body["key_store"] == "standard"
