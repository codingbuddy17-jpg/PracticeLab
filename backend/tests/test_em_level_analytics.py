"""
The E/M level direction tab.

Reads BOTH places a level is coded: the E/M specialties and ED Facility, where
the level is an ordinary CPT line. A tab covering one would quietly describe
half the team.
"""
import pytest

from models import (Batch, Chart, GradingFeedback, GradingResult, PassFail,
                    Specialty)
from models.charts import ChartStatus, Difficulty
from models.practicelab import BatchStatus

URL = "/practicelab/analytics/em-levels"

_SEQ = iter(range(1, 9999))


def _chart(db, specialty=Specialty.ED_FACILITY):
    c = Chart(chart_number="ED%03d" % next(_SEQ), specialty=specialty,
              category="Chest pain", difficulty=Difficulty.INTERMEDIATE,
              status=ChartStatus.ACTIVE, uploaded_by="t", view_count=0)
    db.add(c); db.commit()
    return c


def _error(db, coded, expected, coder="Ann", emp="E1",
           specialty=Specialty.ED_FACILITY, section="CPT"):
    chart = _chart(db, specialty)
    batch = Batch(name="B%d" % next(_SEQ), specialty=specialty,
                  status=BatchStatus.OPEN, created_by="t", charts_per_coder=1,
                  is_direct_assignment=False, use_weighted=True,
                  use_dpo=False, force_closed=False)
    db.add(batch); db.commit()
    r = GradingResult(batch_id=batch.id, coder_name=coder, emp_id=emp,
                      chart_id=chart.id, specialty=specialty,
                      total_score=60, pass_fail=PassFail.FAIL)
    db.add(r); db.commit()
    db.add(GradingFeedback(result_id=r.id, section=section,
                           issue_type="Wrong_Code", ak_code=expected,
                           coder_code=coded, detail=""))
    db.commit()
    return r


class TestDirection:
    def test_upcoding_and_downcoding_are_counted_apart(self, client, db):
        _error(db, "99285", "99284")          # up
        _error(db, "99283", "99284")          # down
        _error(db, "99282", "99284")          # down
        team = client.get(URL, params={"scope": "all"}).json()["team"]
        assert team["upcoded"] == 1
        assert team["downcoded"] == 2
        assert team["upward"] == 1 and team["downward"] == 2

    def test_a_coder_who_errs_one_way_has_a_lean(self, client, db):
        for _ in range(3):
            _error(db, "99285", "99284", coder="Ann", emp="E1")
        row = client.get(URL, params={"scope": "all"}).json()["by_coder"][0]
        assert row["lean"] == "up"

    def test_erring_both_ways_equally_is_not_a_lean(self, client, db):
        """
        A precision problem rather than a habit — and calling it a lean would
        send a trainer to correct a bias that is not there.
        """
        _error(db, "99285", "99284", coder="Bob", emp="E2")
        _error(db, "99283", "99284", coder="Bob", emp="E2")
        row = next(r for r in client.get(URL, params={"scope": "all"}).json()["by_coder"]
                   if r["emp_id"] == "E2")
        assert row["lean"] is None


class TestPatientTypeAndCriticalCare:
    def test_new_versus_established_is_its_own_finding(self, client, db):
        _error(db, "99204", "99214")
        team = client.get(URL, params={"scope": "all"}).json()["team"]
        assert team["patient_type"] == 1
        assert team["upcoded"] == 0 and team["downcoded"] == 0

    def test_the_critical_care_boundary_is_reported_both_ways(self, client, db):
        _error(db, "99291", "99285")          # overreach
        _error(db, "99285", "99291")          # missed
        team = client.get(URL, params={"scope": "all"}).json()["team"]
        assert team["critical_care_overreach"] == 1
        assert team["critical_care_missed"] == 1

    def test_the_boundary_counts_into_the_direction_totals(self, client, db):
        """
        Overreach IS upcoding and a missed one IS downcoding — the boundary is
        only where it happens. Leaving them out would understate the lean.
        """
        _error(db, "99291", "99285")
        team = client.get(URL, params={"scope": "all"}).json()["team"]
        assert team["upward"] == 1 and team["downward"] == 0


class TestWhatItDoesNotCount:
    def test_a_non_level_code_pair_is_ignored(self, client, db):
        _error(db, "20610", "36415")
        body = client.get(URL, params={"scope": "all"}).json()
        assert body["team"]["total"] == 0
        # But it says it looked, so an empty tab is not mistaken for no data.
        assert body["code_pairs_examined"] == 1

    def test_a_diagnosis_error_is_not_a_level_error(self, client, db):
        _error(db, "J18.9", "J13", section="SDx")
        assert client.get(URL, params={"scope": "all"}).json()["team"]["total"] == 0

    def test_the_add_on_unit_is_not_a_level_error(self, client, db):
        _error(db, "99292", "99291")
        assert client.get(URL, params={"scope": "all"}).json()["team"]["total"] == 0

    def test_an_empty_installation_reports_zero_rather_than_failing(self, client, db):
        body = client.get(URL, params={"scope": "all"}).json()
        assert body["team"]["total"] == 0
        assert body["by_coder"] == [] and body["graded_charts"] == 0


class TestItCoversBothSources:
    def test_ed_facility_levels_are_read_from_ordinary_cpt_lines(self, client, db):
        """
        ED Facility is graded by the main engine, so its level is a CPT line
        like any other. This is the half a tab built only on the E/M
        specialties would have missed.
        """
        _error(db, "99285", "99284", specialty=Specialty.ED_FACILITY)
        assert client.get(URL, params={"scope": "all"}).json()["team"]["upcoded"] == 1

    def test_the_em_specialty_is_read_too(self, client, db):
        _error(db, "99215", "99214", specialty=Specialty.EM)
        assert client.get(URL, params={"scope": "all"}).json()["team"]["upcoded"] == 1

    def test_a_specialty_filter_still_applies(self, client, db):
        _error(db, "99285", "99284", specialty=Specialty.ED_FACILITY)
        _error(db, "99215", "99214", specialty=Specialty.EM)
        body = client.get(URL, params={"scope": "all", "specialty": "E/M"}).json()
        assert body["team"]["total"] == 1
