"""
Unspecified-code usage, and where it was wrong.

The only measurement in coder analytics that is not a re-slice of the error
counts. Everything else reads grading_feedback, which holds only mistakes, so
it can report shares of errors and never a rate. This needs every code a coder
SUBMITTED — right or wrong — which lives in the practice tables.

Two figures that must not be confused:

  usage rate       a habit. Sometimes unspecified is the correct code.
  specificity drop an error. The key wanted a specific code and got a vague one.
"""
import json

import pytest
from sqlalchemy import text

from models import (Batch, Chart, CodeDescription, GradingFeedback,
                    GradingResult, PassFail, Specialty)
from models.charts import ChartStatus, Difficulty
from models.practicelab import BatchStatus

URL = "/practicelab/analytics/specificity"


@pytest.fixture()
def codes(db):
    db.add_all([
        CodeDescription(code="J189", code_system="ICD10CM",
                        description="Pneumonia, unspecified organism",
                        chapter="Diseases of the respiratory system",
                        chapter_no=10, is_billable=True),
        CodeDescription(code="J13", code_system="ICD10CM",
                        description="Pneumonia due to Streptococcus pneumoniae",
                        chapter="Diseases of the respiratory system",
                        chapter_no=10, is_billable=True),
        CodeDescription(code="N179", code_system="ICD10CM",
                        description="Acute kidney failure, unspecified",
                        chapter="Diseases of the genitourinary system",
                        chapter_no=14, is_billable=True),
        CodeDescription(code="E1122", code_system="ICD10CM",
                        description="Type 2 diabetes with diabetic chronic "
                                    "kidney disease",
                        chapter="Endocrine, nutritional and metabolic diseases",
                        chapter_no=4, is_billable=True),
        CodeDescription(code="Z79899", code_system="ICD10CM",
                        description="Other long term drug therapy",
                        chapter="Factors influencing health status",
                        chapter_no=21, is_billable=True),
    ])
    db.commit()
    return db


_SEQ = iter(range(1, 9999))


def _setup(db, submitted, coder="Ann", emp="E1"):
    """One graded chart with a recorded submission behind it."""
    n = next(_SEQ)
    chart = Chart(chart_number="IP%03d" % n, specialty=Specialty.IP_DRG,
                  category="Sepsis", difficulty=Difficulty.BEGINNER,
                  status=ChartStatus.ACTIVE, uploaded_by="t", view_count=0)
    batch = Batch(name="B%d" % n, specialty=Specialty.IP_DRG, status=BatchStatus.OPEN,
                  created_by="t", charts_per_coder=1, is_direct_assignment=False,
                  use_weighted=True, use_dpo=False, force_closed=False)
    db.add_all([chart, batch]); db.commit()
    result = GradingResult(batch_id=batch.id, coder_name=coder, emp_id=emp,
                           chart_id=chart.id, specialty=Specialty.IP_DRG,
                           total_score=70, pass_fail=PassFail.FAIL)
    db.add(result); db.commit()
    db.execute(text("INSERT INTO practice_sessions "
                    "(id, batch_id, coder_name, specialty, token, chart_ids, status) "
                    "VALUES (:i, :b, :c, 'IP-DRG', :t, '[]', 'submitted')"),
               {"i": result.id, "b": batch.id, "c": coder, "t": "T%d" % result.id})
    db.execute(text("INSERT INTO practice_results "
                    "(session_id, chart_id, specialty, total_score, "
                    " pdx_submitted, sdx_submitted) "
                    "VALUES (:s, :ch, 'IP-DRG', 70, :pdx, :sdx)"),
               {"s": result.id, "ch": chart.id,
                "pdx": submitted[0],
                "sdx": json.dumps([{"code": c, "poa": "Y"} for c in submitted[1:]])})
    db.commit()
    return batch, chart, result


class TestUsageRate:
    def test_the_rate_is_over_everything_submitted_not_over_errors(self, client, db, codes):
        """
        The whole reason this endpoint exists. Two of four submitted diagnoses
        are unspecified — whether or not any of them were marked wrong.
        """
        _setup(db, ["J18.9", "N17.9", "J13", "E11.22"])
        body = client.get(URL, params={"scope": "all"}).json()
        assert body["available"] is True
        assert body["team"]["resolved"] == 4
        assert body["team"]["unspecified"] == 2
        assert body["team"]["rate"] == 50.0

    def test_a_correct_unspecified_code_still_counts_as_usage(self, client, db, codes):
        """It is a habit, not an error — no feedback row is involved."""
        _setup(db, ["J18.9"])
        assert client.get(URL, params={"scope": "all"}).json()["team"]["rate"] == 100.0

    def test_other_specified_is_not_unspecified(self, client, db, codes):
        """
        "Other" means the documentation named something the classification has
        no code for. That is a different situation from it not saying.
        """
        _setup(db, ["Z79.899"])
        assert client.get(URL, params={"scope": "all"}).json()["team"]["rate"] == 0.0

    def test_codes_the_tables_do_not_know_are_left_out_of_the_denominator(
            self, client, db, codes):
        """
        A code we cannot describe is not evidence either way. Counting it would
        depress every coder's rate by however stale their answer keys are.
        """
        _setup(db, ["J18.9", "Q99.999"])
        team = client.get(URL, params={"scope": "all"}).json()["team"]
        assert team["submitted"] == 2 and team["resolved"] == 1
        assert team["rate"] == 100.0

    def test_it_is_reported_per_coder(self, client, db, codes):
        _setup(db, ["J18.9", "N17.9"], coder="Ann", emp="E1")
        _setup(db, ["J13"], coder="Bob", emp="E2")
        rows = client.get(URL, params={"scope": "all"}).json()["by_coder"]
        assert [r["coder_name"] for r in rows] == ["Ann", "Bob"]   # worst first
        assert rows[0]["rate"] == 100.0 and rows[1]["rate"] == 0.0


class TestSpecificityDrops:
    def _wrong_code(self, db, result, coded, expected, section="SDx"):
        db.add(GradingFeedback(result_id=result.id, section=section,
                               issue_type="Wrong_Code", ak_code=expected,
                               coder_code=coded, detail=""))
        db.commit()

    def test_a_vague_code_where_a_specific_one_was_wanted_is_reported(
            self, client, db, codes):
        _b, _c, r = _setup(db, ["J18.9"])
        self._wrong_code(db, r, "J18.9", "J13")
        drops = client.get(URL, params={"scope": "all"}).json()["drops"]
        assert len(drops) == 1
        assert drops[0]["coded"] == "J18.9"
        assert drops[0]["expected"] == "J13"
        assert "Streptococcus" in drops[0]["expected_description"]

    def test_the_other_direction_is_not_a_drop(self, client, db, codes):
        """Coding specifically where the key was vague is not this finding."""
        _b, _c, r = _setup(db, ["J13"])
        self._wrong_code(db, r, "J13", "J18.9")
        assert client.get(URL, params={"scope": "all"}).json()["drops"] == []

    def test_two_specific_codes_are_not_a_drop(self, client, db, codes):
        _b, _c, r = _setup(db, ["J13"])
        self._wrong_code(db, r, "J13", "E11.22")
        assert client.get(URL, params={"scope": "all"}).json()["drops"] == []

    def test_only_wrong_code_findings_count(self, client, db, codes):
        """
        A Missed row carries one real code and one absence, so pairing them
        gives two unrelated diagnoses — which is exactly the nonsense this
        guard exists to prevent.
        """
        _b, _c, r = _setup(db, ["J18.9"])
        db.add(GradingFeedback(result_id=r.id, section="SDx", issue_type="Missed",
                               ak_code="J13", coder_code="J18.9", detail=""))
        db.commit()
        assert client.get(URL, params={"scope": "all"}).json()["drops"] == []

    def test_two_unrelated_diagnoses_are_not_a_specificity_drop(self, client, db, codes):
        """
        Found by looking at real output. Filtering to Wrong_Code was not
        enough: production reported "J18.9 -> N18.6", pneumonia coded where end
        stage renal disease was expected. That is a wrong code that happens to
        pair a vague one with a specific one, and nobody would coach it as a
        specificity habit. The two codes must at least share a chapter.
        """
        _b, _c, r = _setup(db, ["J18.9"])
        self._wrong_code(db, r, "J18.9", "N17.9")     # respiratory -> genitourinary
        assert client.get(URL, params={"scope": "all"}).json()["drops"] == []

    def test_the_same_chapter_still_counts(self, client, db, codes):
        """J18.9 -> J13 is the classic finding and must survive the guard."""
        _b, _c, r = _setup(db, ["J18.9"])
        self._wrong_code(db, r, "J18.9", "J13")
        assert len(client.get(URL, params={"scope": "all"}).json()["drops"]) == 1

    def test_a_drop_carries_its_spread(self, client, db, codes):
        _b, _c, r1 = _setup(db, ["J18.9"], coder="Ann", emp="E1")
        _b2, _c2, r2 = _setup(db, ["J18.9"], coder="Bob", emp="E2")
        self._wrong_code(db, r1, "J18.9", "J13")
        self._wrong_code(db, r2, "J18.9", "J13")
        row = client.get(URL, params={"scope": "all"}).json()["drops"][0]
        assert row["count"] == 2 and row["coders_affected"] == 2


class TestItRefusesToGuess:
    def test_without_the_code_sets_it_says_so(self, client, db):
        _setup(db, ["J18.9"])
        body = client.get(URL, params={"scope": "all"}).json()
        assert body["available"] is False
        assert "code sets" in body["reason"]

    def test_with_no_graded_work_it_says_so(self, client, db, codes):
        body = client.get(URL, params={"scope": "all"}).json()
        assert body["available"] is False and body["team"] is None

    def test_charts_without_a_recorded_submission_are_counted_separately(
            self, client, db, codes):
        """
        Work from the removed Excel workflow has no submitted codes stored. The
        rate must describe what it actually read, not imply full coverage.
        """
        _setup(db, ["J18.9"])
        chart = Chart(chart_number="IP%03d" % next(_SEQ), specialty=Specialty.IP_DRG,
                      category="X", difficulty=Difficulty.BEGINNER,
                      status=ChartStatus.ACTIVE, uploaded_by="t", view_count=0)
        db.add(chart); db.commit()
        batch = db.query(Batch).first()
        db.add(GradingResult(batch_id=batch.id, coder_name="Zoe", emp_id="E9",
                             chart_id=chart.id, specialty=Specialty.IP_DRG,
                             total_score=90, pass_fail=PassFail.PASS))
        db.commit()
        body = client.get(URL, params={"scope": "all"}).json()
        assert body["charts_in_scope"] == 2
        assert body["charts_with_submissions"] == 1
