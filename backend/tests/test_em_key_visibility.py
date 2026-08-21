"""
E/M keys have to be visible to everything that asks "does this chart have one".

`em_answer_keys` has no ORM model and no row in `answer_keys`, so any check
written as a join against AnswerKey reports zero for every E/M chart. That is
not hypothetical: the batch pool preview told a trainer who had just entered
five keys that no chart in the pool had one.

Also pinned here: the three MDM levels mean nothing on a chart that is not
graded on MDM, and the list must say so rather than printing the derivation's
default as though someone had decided it.
"""
import json

import pytest
from sqlalchemy import text

from conftest import make_chart
from models import AnswerKey, Specialty
from tests.test_auditor_api import PASS


def _em_key(db, chart_id, em_code="99214", category=None, method="MDM"):
    db.execute(text("""
        INSERT INTO em_answer_keys
          (chart_id, em_code, em_modifier, dx_codes, procedure_cpts,
           copa_level, dr_level, risk_level, em_category, level_method,
           entered_by)
        VALUES (:c, :code, '', :dx, '[]', 'Minimal', 'Minimal', 'Minimal',
                :cat, :method, 't')"""),
        {"c": chart_id, "code": em_code, "dx": json.dumps(["J18.9"]),
         "cat": category, "method": method})
    db.commit()


class TestThePoolPreviewSeesEmKeys:
    def test_an_em_chart_with_a_key_is_counted(self, client, db):
        chart = make_chart(db, specialty="E/M")
        db.commit()
        _em_key(db, chart.id)

        r = client.get("/practicelab/batches/pool-preview",
                       params={"specialty": "E/M"})
        assert r.status_code == 200, r.text
        body = r.json()
        assert body["total_matching"] >= 1
        assert body["with_answer_key"] >= 1, (
            "an E/M chart with a key counted as unkeyed — the screen then says "
            "nothing can be graded")

    def test_an_em_chart_without_a_key_is_not_counted(self, client, db):
        make_chart(db, specialty="E/M")
        db.commit()
        r = client.get("/practicelab/batches/pool-preview",
                       params={"specialty": "E/M"})
        assert r.json()["with_answer_key"] == 0

    def test_an_ordinary_specialty_still_counts_answer_keys(self, client, db):
        chart = make_chart(db, specialty="IP-DRG")
        db.add(AnswerKey(chart_id=chart.id, specialty=Specialty.IP_DRG,
                         pdx_code="J18.9", pdx_poa="Y", sdx=[], pcs=[], cpt=[],
                         entered_by="t"))
        db.commit()
        r = client.get("/practicelab/batches/pool-preview",
                       params={"specialty": "IP-DRG"})
        assert r.json()["with_answer_key"] >= 1

    def test_an_em_key_does_not_leak_into_another_specialty_count(self, client, db):
        """The count must be of THIS pool, not of every E/M key in the system."""
        em = make_chart(db, specialty="E/M")
        make_chart(db, specialty="IP-DRG")
        db.commit()
        _em_key(db, em.id)
        r = client.get("/practicelab/batches/pool-preview",
                       params={"specialty": "IP-DRG"})
        assert r.json()["with_answer_key"] == 0


class TestTheListSaysWhereMdmDoesNotApply:
    @pytest.mark.parametrize("category,method,expected", [
        ("office", "MDM", True),
        ("emergency", "MDM", True),
        ("preventive", "MDM", False),     # not graded on MDM at all
        ("office", "TIME", False),        # levelled by time, not by reasoning
    ])
    def test_uses_mdm_matches_how_the_chart_is_graded(
            self, client, db, category, method, expected):
        chart = make_chart(db, specialty="E/M")
        db.commit()
        _em_key(db, chart.id, category=category, method=method)

        row = [r for r in client.get("/practicelab/em/answer-key/list").json()
               if r["chart_id"] == chart.id][0]
        assert row["uses_mdm"] is expected

    def test_it_agrees_with_the_grader_rather_than_restating_the_rule(
            self, client, db):
        """
        The flag exists so a screen can hide levels that do not count. If it
        ever disagreed with the weights the grader actually applies, the screen
        would be lying in the other direction.
        """
        from routers.practicelab_pkg.em_grading import applicable_weights

        cfg = {"copa_weight": 10.0, "dr_weight": 10.0, "risk_weight": 10.0,
               "em_level_weight": 23.33, "cpt_weight": 23.33, "dx_weight": 23.34,
               "line1_weight": 70.0, "line2_weight": 30.0,
               "pass_threshold": 80.0, "overcoding_penalty": True}

        for category, method in (("office", "MDM"), ("preventive", "MDM"),
                                 ("office", "TIME"), ("emergency", "MDM")):
            chart = make_chart(db, specialty="E/M")
            db.commit()
            _em_key(db, chart.id, category=category, method=method)
            row = [r for r in client.get("/practicelab/em/answer-key/list").json()
                   if r["chart_id"] == chart.id][0]
            graded = "copa" in applicable_weights(cfg, category, True, method)
            assert row["uses_mdm"] is graded, (
                "%s/%s: list says uses_mdm=%s, grader says %s"
                % (category, method, row["uses_mdm"], graded))


class TestEMScoringConfigValidation:
    def _payload(self, **overrides):
        payload = {
            "line1_weight": 70.0,
            "line2_weight": 30.0,
            "em_level_weight": 23.33,
            "cpt_weight": 23.33,
            "dx_weight": 23.34,
            "copa_weight": 10.0,
            "dr_weight": 10.0,
            "risk_weight": 10.0,
            "pass_threshold": 80.0,
            "overcoding_penalty": True,
            "updated_by": "QA",
            "passphrase": PASS,
        }
        payload.update(overrides)
        return payload

    def test_line_weights_must_sum_to_100_on_the_backend(self, client, db):
        r = client.put("/practicelab/em/scoring-config",
                       json=self._payload(line1_weight=80, line2_weight=30))

        assert r.status_code == 400
        assert "sum to 100" in r.json()["detail"]

    def test_coding_metric_weights_must_sum_to_line1(self, client, db):
        r = client.put("/practicelab/em/scoring-config",
                       json=self._payload(em_level_weight=30, cpt_weight=30,
                                          dx_weight=30))

        assert r.status_code == 400
        assert "Coding Accuracy metric weights" in r.json()["detail"]

    def test_reasoning_metric_weights_must_sum_to_line2(self, client, db):
        r = client.put("/practicelab/em/scoring-config",
                       json=self._payload(copa_weight=15, dr_weight=15,
                                          risk_weight=15))

        assert r.status_code == 400
        assert "Reasoning Accuracy metric weights" in r.json()["detail"]


class TestEditing:
    def test_a_stored_key_can_be_read_back_whole(self, client, db):
        """
        Editing needed no new save path — the save already upserts on chart_id.
        What it needed was a way to get the key back, including the element
        ticks the list omits. Without it, fixing a typo meant deleting the key
        and retyping twenty-six ticks.
        """
        chart = make_chart(db, specialty="E/M")
        db.commit()
        _em_key(db, chart.id, category="office")

        r = client.get("/practicelab/em/answer-key/%d" % chart.id)
        assert r.status_code == 200
        body = r.json()
        assert body["em_code"] == "99214"
        assert "copa_self_limited" in body, "element ticks are needed to edit"

    def test_saving_the_same_chart_twice_updates_rather_than_duplicates(
            self, client, db):
        chart = make_chart(db, specialty="E/M")
        db.commit()
        _em_key(db, chart.id)

        r = client.post("/practicelab/em/answer-key", json={
            "chart_id": chart.id, "em_code": "99215", "dx_codes": ["J18.9"],
            "procedure_cpts": [], "entered_by": "t", "passphrase": PASS,
        })
        assert r.status_code == 200, r.text
        rows = db.execute(text(
            "SELECT em_code FROM em_answer_keys WHERE chart_id = :c"),
            {"c": chart.id}).fetchall()
        assert [r[0] for r in rows] == ["99215"]


class TestTheAuditorIsNotAskedAboutMdmWhereItDoesNotApply:
    """
    The audit form is served per SPECIALTY, but E/M is not uniform. A
    preventive visit, or one levelled by time, is not graded on medical
    decision making — so asking an auditor for a verdict on COPA, Data Review
    and Risk asks them to judge something that carries no weight, against three
    stored levels that are the derivation's default rather than a decision.

    This keys on CATEGORY, which is a property of the encounter and already
    plain from the code on the claim. It must never key on whether anything was
    planted: a chart has to render identically either way.
    """
    import pytest as _pytest

    @_pytest.mark.parametrize("category,method,mdm_expected", [
        ("office", "MDM", True),
        ("emergency", "MDM", True),
        ("preventive", "MDM", False),
        ("office", "TIME", False),
    ])
    def test_the_mdm_section_appears_only_where_it_is_graded(
            self, client, db, category, method, mdm_expected):
        from routers.auditor_pkg.shared import sections_for_chart
        from models import Specialty as Sp

        chart = make_chart(db, specialty="E/M")
        db.commit()
        _em_key(db, chart.id, category=category, method=method)

        sections = sections_for_chart(db, chart, Sp.EM)
        assert ("MDM" in sections) is mdm_expected
        # The code sections are never affected — every E/M chart is reviewed on
        # its diagnoses and its codes whatever the category.
        for always in ("PDx", "SDx", "CPT"):
            assert always in sections

    def test_an_ordinary_specialty_is_untouched(self, client, db):
        from routers.auditor_pkg.shared import form_spec, sections_for_chart
        from models import Specialty as Sp

        chart = make_chart(db, specialty="IP-DRG")
        db.commit()
        assert (sections_for_chart(db, chart, Sp.IP_DRG)
                == [s["key"] for s in form_spec(Sp.IP_DRG)["sections"]])

    def test_a_chart_with_no_em_key_keeps_the_full_form(self, client, db):
        """
        Absence of a key is not evidence the chart is preventive. Narrowing on
        a guess would hide a section the chart may well be graded on.
        """
        from routers.auditor_pkg.shared import sections_for_chart
        from models import Specialty as Sp

        chart = make_chart(db, specialty="E/M")
        db.commit()
        assert "MDM" in sections_for_chart(db, chart, Sp.EM)

    def test_the_trainer_key_screen_narrows_the_same_way(self, client, db):
        """
        A trainer must not be offered an MDM error to plant on a chart the
        generator will refuse to plant one on — the mutation would be
        configured and then silently never fire.
        """
        chart = make_chart(db, specialty="E/M")
        db.commit()
        _em_key(db, chart.id, category="preventive")

        body = client.get("/auditor/keys/chart/%d" % chart.id).json()
        keys = [s["key"] for s in body["form"]["sections"]]
        assert "MDM" not in keys
        assert "PDx" in keys


class TestNonMdmChartsDoNotProduceMdmJudgements:
    """
    A preventive visit, or one levelled by time, is not graded on medical
    decision making. It used to get COPA / Data Review / Risk feedback rows
    anyway, carrying the key's stored default against the coder's derived
    default — both "Minimal", so they matched every time.

    Analytics counted those as judgements. A coder who had never been asked
    about MDM read 100% on all three, and every preventive chart was flagged
    "right code, wrong reasoning" because its reasoning total is 0.
    """

    def _items(self, uses_mdm, method="MDM"):
        from routers.practicelab_pkg.practice_sessions import _em_feedback_items
        scoring = {
            "em_level_score": 35.0, "cpt_score": 0.0, "dx_score": 23.3,
            "copa_element_score": 0.0, "dr_element_score": 0.0,
            "risk_element_score": 0.0, "derived_copa_level": "Minimal",
            "derived_dr_level": "Minimal", "derived_risk_level": "Minimal",
            "uses_mdm": uses_mdm, "ak_level_method": method,
            "reasoning_accuracy_total": 30.0,
        }
        return _em_feedback_items(
            scoring, {"em_code": "99214", "copa_level": "Minimal",
                      "dr_level": "Minimal", "risk_level": "Minimal",
                      "total_time": 35},
            {"em_code": "99214", "total_time": 35}, {"em_level_weight": 35.0})

    def test_an_mdm_chart_still_reports_its_three_levels(self):
        ra = [i["issue"] for i in self._items(True)
              if i["section"] == "Reasoning Accuracy"]
        assert any(i.startswith("COPA") for i in ra)
        assert any(i.startswith("Data Review") for i in ra)
        assert any(i.startswith("Risk") for i in ra)

    def test_a_preventive_chart_reports_none_of_them(self):
        ra = [i["issue"] for i in self._items(False, method="MDM")]
        assert not [i for i in ra if i.startswith(("COPA", "Data Review", "Risk"))]

    def test_a_time_levelled_chart_says_what_its_reasoning_was_worth(self):
        """
        Not simply blank: time-levelled charts DO have a reasoning component —
        the time supporting the code — and an empty section reads as though
        nothing was assessed.
        """
        ra = [i["issue"] for i in self._items(False, method="TIME")
              if i["section"] == "Reasoning Accuracy"]
        assert ra, "a time-levelled chart reported no reasoning at all"
        assert any(i.startswith("Time") for i in ra), ra

    def test_a_chart_nobody_was_asked_about_does_not_move_the_percentage(self):
        """NA is a real value: neither 100% nor 0%."""
        from routers.practicelab_pkg.practice_sessions import _match_pct
        charts = [{"mdm_judged_chart": False, "copa_match": False},
                  {"mdm_judged_chart": False, "copa_match": False}]
        assert _match_pct(charts, "copa_match") is None

    def test_judged_charts_alone_set_the_percentage(self):
        from routers.practicelab_pkg.practice_sessions import _match_pct
        charts = [{"mdm_judged_chart": True, "copa_match": True},
                  {"mdm_judged_chart": True, "copa_match": False},
                  {"mdm_judged_chart": False, "copa_match": False}]
        assert _match_pct(charts, "copa_match") == 50.0


class TestScoresAreAveragedNotPooledAcrossDifferentDenominators:
    """
    Charts do not share a denominator. A preventive chart scores its coding out
    of 100, because with no reasoning line the reasoning weight folds into
    coding; a time-levelled chart scores it out of 70.

    Averaging the POINTS and dividing by an averaged maximum produced "79.2 of
    85" — a denominator belonging to no chart, and a percentage (93.2%) that is
    not the average of the two chart scores (91.7%).
    """

    def test_the_average_is_of_chart_scores(self):
        from routers.practicelab_pkg.practice_sessions import _avg_pct
        charts = [
            {"coding_pct": 100.0},   # preventive: 100 of 100
            {"coding_pct": 83.3},    # time-levelled: 58.33 of 70
        ]
        assert _avg_pct(charts, "coding_pct") == 91.7

    def test_a_chart_without_that_line_is_left_out_rather_than_counted_as_zero(self):
        from routers.practicelab_pkg.practice_sessions import _avg_pct
        charts = [{"reasoning_pct": None}, {"reasoning_pct": 100.0}]
        assert _avg_pct(charts, "reasoning_pct") == 100.0

    def test_no_chart_with_the_line_is_NA_not_zero(self):
        from routers.practicelab_pkg.practice_sessions import _avg_pct
        assert _avg_pct([{"reasoning_pct": None}], "reasoning_pct") is None

    def test_the_two_lines_add_up_to_the_chart_score(self):
        """
        The headline is coding + reasoning out of 100. If they ever stopped
        summing, the results card would show a total contradicting the panels
        printed directly beneath it.
        """
        import json
        from routers.practicelab_pkg.em_grading import grade_em_chart

        cfg = {"line1_weight": 70.0, "line2_weight": 30.0, "em_level_weight": 23.33,
               "cpt_weight": 23.33, "dx_weight": 23.34, "copa_weight": 10.0,
               "dr_weight": 10.0, "risk_weight": 10.0, "pass_threshold": 80.0,
               "overcoding_penalty": True}
        for category, method, minutes in (("office", "TIME", 35),
                                          ("preventive", "MDM", None),
                                          ("office", "MDM", None)):
            ak = {"em_code": "99214" if category != "preventive" else "99395",
                  "em_modifier": "", "patient_type": "ESTABLISHED",
                  "level_method": method, "total_time": minutes,
                  "em_category": category,
                  "dx_codes": json.dumps(["J18.9", "E11.9", "I10"]),
                  "procedure_cpts": "[]", "copa_level": "Moderate",
                  "dr_level": "Moderate", "risk_level": "Moderate"}
            sub = {"sub_em_code": ak["em_code"], "sub_em_modifier": "",
                   "sub_patient_type": "ESTABLISHED", "sub_level_method": method,
                   "sub_total_time": minutes,
                   "sub_dx_codes": json.dumps(["J18.9", "E11.9", "Z00.00"])}
            r = grade_em_chart(ak, sub, cfg)
            total = r["coding_accuracy_total"] + r["reasoning_accuracy_total"]
            assert abs(total - r["total_score"]) < 0.15, (
                "%s/%s: %s + %s != %s" % (category, method,
                                          r["coding_accuracy_total"],
                                          r["reasoning_accuracy_total"],
                                          r["total_score"]))


class TestTheStoredTotalIsTheGradersTotal:
    """
    The stored score was recomputed by hand as the sum of six named components
    — E/M level, CPT, Dx, COPA, Data Review, Risk. That list has no TIME in it,
    so every time-levelled chart was stored ~30 points below what it scored.

    A real chart: level 99215 correct, 45 minutes correct, 2 of 3 diagnoses.
    Graded 88.3, stored 58, shown to the coder as a FAIL.
    """

    def _cfg(self):
        return {"line1_weight": 70.0, "line2_weight": 30.0, "em_level_weight": 23.33,
                "cpt_weight": 23.33, "dx_weight": 23.34, "copa_weight": 10.0,
                "dr_weight": 10.0, "risk_weight": 10.0, "pass_threshold": 80.0,
                "overcoding_penalty": True}

    def test_a_time_levelled_chart_keeps_its_reasoning_points(self):
        import json
        from routers.practicelab_pkg.em_grading import grade_em_chart

        ak = {"em_code": "99215", "em_modifier": "", "patient_type": "ESTABLISHED",
              "level_method": "TIME", "total_time": 45, "em_category": "office",
              "dx_codes": json.dumps(["J18.9", "E11.9", "I10"]),
              "procedure_cpts": "[]", "copa_level": "Minimal",
              "dr_level": "Minimal", "risk_level": "Minimal"}
        sub = {"sub_em_code": "99215", "sub_em_modifier": "",
               "sub_patient_type": "ESTABLISHED", "sub_level_method": "TIME",
               "sub_total_time": 45,
               "sub_dx_codes": json.dumps(["J18.9", "E11.9", "Z00.00"])}
        sc = grade_em_chart(ak, sub, self._cfg())

        assert sc["total_score"] > 85, sc["total_score"]
        # And the hand-rolled sum that used to be stored is demonstrably lower,
        # which is the whole point of never recomputing it.
        by_hand = (sc["em_level_score"] + sc["cpt_score"] + sc["dx_score"]
                   + sc["copa_element_score"] + sc["dr_element_score"]
                   + sc["risk_element_score"])
        assert by_hand < sc["total_score"] - 25

    def test_no_call_site_recomputes_the_total(self):
        """
        Two places did, and both were wrong the same way. A grep is the only
        thing that stops a third appearing.
        """
        import pathlib
        src = (pathlib.Path(__file__).resolve().parents[1] / "routers"
               / "practicelab_pkg" / "practice_sessions.py").read_text()
        assert 'scoring["copa_element_score"] + scoring["dr_element_score"]' not in src, (
            "a total is being rebuilt from components again — use "
            "scoring['total_score']")

    def test_a_chart_with_no_procedures_shows_no_cpt_line(self):
        from routers.practicelab_pkg.practice_sessions import _em_feedback_items
        items = _em_feedback_items(
            {"em_level_score": 35.0, "cpt_score": 0.0, "dx_score": 23.3,
             "applied_weights": {"em_level": 35.0, "dx": 35.0},
             "uses_mdm": False, "ak_level_method": "TIME",
             "reasoning_accuracy_total": 30.0},
            {"em_code": "99215", "total_time": 45},
            {"em_code": "99215", "total_time": 45}, {"em_level_weight": 23.33})
        assert not [i for i in items if i["issue"].startswith("CPT")]
