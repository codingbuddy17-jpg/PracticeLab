"""
Editing an existing IP/OP answer key, and getting back exactly what you saved.

The E/M tab had no edit at all, which prompted the question of whether this
one — which has had an edit button all along — actually works. These pin the
round trip rather than the button: every field the form can set has to survive
being saved and read back, because a field that quietly drops on save produces
a key that grades everyone against something the trainer did not write.

The attributes are where a silent loss would hurt most. POA and CC/MCC are not
free text; they drive DRG-impacting and severity, and a blank that was meant to
say "Y" is not visibly different from a blank nobody filled in.
"""
import pytest

from conftest import make_chart
from models import AnswerKey, Specialty
from tests.test_auditor_api import PASS

DETAIL = "/practicelab/answer-key/%d/detail"
SAVE = "/practicelab/answer-key/%d"


def _ip_chart(db):
    chart = make_chart(db, specialty="IP-DRG")
    db.commit()
    return chart


class TestTheRoundTrip:
    def test_an_ip_key_survives_save_and_reload(self, client, db):
        chart = _ip_chart(db)
        payload = {
            "pdx_code": "J18.9", "pdx_poa": "Y",
            "sdx": [{"code": "E11.9", "poa": "N", "ccmcc": "CC"},
                    {"code": "I10", "poa": "Y", "ccmcc": ""}],
            "pcs": [{"code": "0BH17EZ"}],
            "cpt": [],
            "entered_by": "trainer",
            "passphrase": PASS,
        }
        r = client.put(SAVE % chart.id, json=payload)
        assert r.status_code == 200, r.text

        got = client.get(DETAIL % chart.id).json()
        assert got["pdx_code"] == "J18.9"
        assert got["pdx_poa"] == "Y"
        assert [s["code"] for s in got["sdx"]] == ["E11.9", "I10"]
        # The part most likely to be lost silently.
        assert [s["poa"] for s in got["sdx"]] == ["N", "Y"]
        assert [s["ccmcc"] for s in got["sdx"]] == ["CC", ""]
        assert [p["code"] for p in got["pcs"]] == ["0BH17EZ"]

    def test_an_op_key_keeps_modifiers_and_units(self, client, db):
        chart = make_chart(db, specialty="Surgery")
        db.commit()
        r = client.put(SAVE % chart.id, json={
            "pdx_code": "M17.11", "pdx_poa": "",
            "sdx": [], "pcs": [],
            "cpt": [{"code": "27447", "modifier": "RT", "units": 2,
                     "pointers": ["1"]}],
            "entered_by": "trainer", "passphrase": PASS,
        })
        assert r.status_code == 200, r.text

        line = client.get(DETAIL % chart.id).json()["cpt"][0]
        assert line["code"] == "27447"
        assert line["modifier"] == "RT"
        assert line["units"] == 2
        assert line["pointers"] == ["1"]

    def test_editing_replaces_rather_than_appends(self, client, db):
        """
        A second save of the same chart must not leave the first key's lines
        behind — a coder would then be graded against a merge of two edits.
        """
        chart = _ip_chart(db)
        client.put(SAVE % chart.id, json={
            "pdx_code": "J18.9", "pdx_poa": "Y",
            "sdx": [{"code": "E11.9", "poa": "N", "ccmcc": "CC"}],
            "pcs": [], "cpt": [], "entered_by": "t", "passphrase": PASS,
        })
        client.put(SAVE % chart.id, json={
            "pdx_code": "A41.9", "pdx_poa": "N",
            "sdx": [], "pcs": [], "cpt": [], "entered_by": "t",
            "passphrase": PASS,
        })

        got = client.get(DETAIL % chart.id).json()
        assert got["pdx_code"] == "A41.9"
        assert got["pdx_poa"] == "N"
        assert got["sdx"] == []
        assert db.query(AnswerKey).filter(
            AnswerKey.chart_id == chart.id).count() == 1

    def test_an_unkeyed_chart_reports_that_rather_than_failing(self, client, db):
        chart = _ip_chart(db)
        got = client.get(DETAIL % chart.id).json()
        assert got["exists"] is False


class TestEditingIsGated:
    def test_changing_an_existing_key_needs_the_passphrase(self, client, db):
        """
        The frontend checks this too, but a check only in the frontend is not a
        check: a key grades everyone who ever sees the chart.
        """
        chart = _ip_chart(db)
        db.add(AnswerKey(chart_id=chart.id, specialty=Specialty.IP_DRG,
                         pdx_code="J18.9", pdx_poa="Y", sdx=[], pcs=[], cpt=[],
                         entered_by="t"))
        db.commit()

        r = client.put(SAVE % chart.id, json={
            "pdx_code": "A41.9", "pdx_poa": "Y", "sdx": [], "pcs": [],
            "cpt": [], "entered_by": "t", "passphrase": "wrong",
        })
        assert r.status_code in (400, 403), (
            "an existing key was editable without the passphrase")
        assert db.query(AnswerKey).filter(
            AnswerKey.chart_id == chart.id).first().pdx_code == "J18.9"
