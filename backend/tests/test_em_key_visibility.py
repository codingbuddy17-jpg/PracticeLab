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
