"""
Checking the answer keys ALREADY stored.

The upload check only sees what passes through it, which does nothing for keys
written before that check existed — and those are the keys that have been
grading people. The first run against real data found two codes that do not
exist and two CC/MCC labels contradicting the published list.
"""
from conftest import make_chart

from models import AnswerKey, CodeDescription, Specialty


def _key(db, chart, pdx="J18.9", sdx=None, pcs=None, cpt=None):
    ak = AnswerKey(chart_id=chart.id, specialty=chart.specialty,
                   pdx_code=pdx, pdx_poa="Y", sdx=sdx or [],
                   pcs=pcs or [], cpt=cpt or [], entered_by="trainer")
    db.add(ak)
    db.commit()
    return ak


def _codes(db):
    db.add_all([
        CodeDescription(code="J189", code_system="ICD10CM",
                        description="Pneumonia", is_billable=True),
        CodeDescription(code="A419", code_system="ICD10CM",
                        description="Sepsis", cc_mcc_status="MCC",
                        is_billable=True),
        CodeDescription(code="E119", code_system="ICD10CM",
                        description="Type 2 diabetes", cc_mcc_status=None,
                        is_billable=True),
    ])
    db.commit()


class TestItFindsWhatTheUploadCheckWouldHaveCaught:
    def test_a_stored_key_with_a_code_that_does_not_exist_is_reported(
            self, client, db):
        chart = make_chart(db, chart_number="IP001")
        db.commit()
        _key(db, chart, pdx="E18.3")        # not a code, well formed
        _codes(db)
        body = client.get("/practicelab/answer-key/check").json()
        assert body["codes_checked"] is True
        assert [(u["chart"], u["code"]) for u in body["unknown_codes"]] == [
            ("IP001", "E183")]

    def test_a_key_whose_codes_all_exist_reports_nothing(self, client, db):
        chart = make_chart(db, chart_number="IP002")
        db.commit()
        _key(db, chart, pdx="J18.9")
        _codes(db)
        body = client.get("/practicelab/answer-key/check").json()
        assert body["unknown_codes"] == []
        assert body["keys_checked"] == 1

    def test_a_contradicted_ccmcc_label_is_reported(self, client, db):
        chart = make_chart(db, chart_number="IP003")
        db.commit()
        _key(db, chart, sdx=[{"code": "E11.9", "poa": "Y", "ccmcc": "CC"}])
        _codes(db)
        body = client.get("/practicelab/answer-key/check").json()
        assert [(c["code"], c["claimed"], c["published"])
                for c in body["ccmcc_mismatches"]] == [("E119", "CC", "neither")]

    def test_outpatient_keys_are_not_judged_on_ccmcc(self, client, db):
        """A CC/MCC label is an inpatient concept; OP keys have no column."""
        chart = make_chart(db, specialty="Surgery", chart_number="OP001")
        db.commit()
        _key(db, chart, sdx=[{"code": "E11.9", "ccmcc": "CC"}])
        _codes(db)
        assert client.get("/practicelab/answer-key/check"
                          ).json()["ccmcc_mismatches"] == []

    def test_it_can_be_scoped_to_one_specialty(self, client, db):
        ip = make_chart(db, chart_number="IP004")
        op = make_chart(db, specialty="Surgery", chart_number="OP004")
        db.commit()
        _key(db, ip, pdx="E18.3")
        _key(db, op, pdx="E18.3")
        _codes(db)
        body = client.get("/practicelab/answer-key/check",
                          params={"specialty": "IP-DRG"}).json()
        assert body["keys_checked"] == 1
        assert [u["chart"] for u in body["unknown_codes"]] == ["IP004"]


class TestItIsHonestAboutWhatItLookedAt:
    def test_nothing_loaded_reports_not_checked_rather_than_clean(
            self, client, db):
        """
        The distinction the whole feature rests on: an empty result must not
        read as approval when nothing was compared against.
        """
        chart = make_chart(db, chart_number="IP005")
        db.commit()
        _key(db, chart, pdx="E18.3")
        body = client.get("/practicelab/answer-key/check").json()
        assert body["codes_checked"] is False
        assert body["unknown_codes"] is None

    def test_the_total_counts_every_key_not_just_the_scanned_ones(
            self, client, db):
        """
        Counted over the whole filtered set. Telling a trainer "no problems"
        because the bad key sat past the cap is a defect this codebase has
        already paid for elsewhere.
        """
        for i in range(6):
            c = make_chart(db, chart_number=f"IP1{i:02d}")
            db.commit()
            _key(db, c)
        _codes(db)
        body = client.get("/practicelab/answer-key/check",
                          params={"scan_limit": 2}).json()
        assert body["keys_checked"] == 2
        assert body["keys_total"] == 6
        assert body["truncated"] is True

    def test_an_installation_with_no_keys_at_all_is_fine(self, client, db):
        body = client.get("/practicelab/answer-key/check").json()
        assert body["keys_total"] == 0 and body["keys_checked"] == 0


class TestRouteOrdering:
    def test_the_literal_path_precedes_the_parameterised_one(self):
        """
        `/answer-key/{chart_id}` would otherwise swallow `/answer-key/check`
        and answer it with a 422 about an invalid integer. The same trap has
        already been pinned for the E/M routes.
        """
        import pathlib
        src = (pathlib.Path(__file__).resolve().parents[1]
               / "routers" / "practicelab_pkg" / "config.py").read_text()
        assert src.index('"/answer-key/check"') < src.index('"/answer-key/{chart_id}')
