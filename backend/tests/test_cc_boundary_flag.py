"""
Marking a chart as sitting on the critical care boundary.

The 99285-versus-99291 planting is generated ONLY where a trainer has said the
question is fair to ask. An answer key says which code is right; it cannot say
whether a chart is genuinely borderline, and the generator must not guess —
planted on a chart where critical care is plainly absent, the error is spotted
without reading anything, which teaches auditors to distrust the module.
"""
import pytest

from conftest import make_chart
from models import AnswerKey, Specialty
from tests.test_auditor_api import PASS

URL = "/auditor/keys/chart/%d/cc-boundary"


def _ed_chart(db, cpt):
    chart = make_chart(db, specialty="ED Facility")
    db.add(AnswerKey(chart_id=chart.id, specialty=Specialty.ED_FACILITY,
                     pdx_code="R07.9", pdx_poa="", sdx=[], pcs=[],
                     cpt=cpt, entered_by="t"))
    db.commit()
    return chart


class TestMarking:
    def test_an_ed_chart_can_be_marked_borderline(self, client, db):
        chart = _ed_chart(db, [{"code": "99285", "modifier": "", "units": 1}])
        r = client.post(URL % chart.id,
                        json={"cc_boundary": "borderline", "passphrase": PASS})
        assert r.status_code == 200, r.text
        assert r.json()["cc_boundary"] == "borderline"

    def test_the_mark_can_be_taken_off_again(self, client, db):
        chart = _ed_chart(db, [{"code": "99291", "modifier": "", "units": 1}])
        client.post(URL % chart.id,
                    json={"cc_boundary": "borderline", "passphrase": PASS})
        r = client.post(URL % chart.id, json={"cc_boundary": "", "passphrase": PASS})
        assert r.json()["cc_boundary"] is None

    def test_it_shows_on_the_chart_view(self, client, db):
        chart = _ed_chart(db, [{"code": "99285", "modifier": "", "units": 1}])
        client.post(URL % chart.id,
                    json={"cc_boundary": "borderline", "passphrase": PASS})
        body = client.get(f"/auditor/keys/chart/{chart.id}").json()
        assert body["cc_boundary"] == "borderline"


class TestItRefusesWhatWouldBeInvisible:
    def test_a_chart_with_no_ed_level_cannot_be_marked(self, client, db):
        """
        A no-op the trainer could not see is worse than a refusal: they would
        believe the question had been enabled and it never fires.
        """
        chart = _ed_chart(db, [{"code": "20610", "modifier": "", "units": 1}])
        r = client.post(URL % chart.id,
                        json={"cc_boundary": "borderline", "passphrase": PASS})
        assert r.status_code == 400
        assert "does not arise" in r.json()["detail"]

    def test_a_typo_is_refused_rather_than_stored(self, client, db):
        """
        The generator keys on one exact value. "Borderline-ish" would store
        cleanly and silently mean "never plant this".
        """
        chart = _ed_chart(db, [{"code": "99285", "modifier": "", "units": 1}])
        r = client.post(URL % chart.id,
                        json={"cc_boundary": "maybe", "passphrase": PASS})
        assert r.status_code == 400

    def test_a_chart_with_no_answer_key_is_refused(self, client, db):
        chart = make_chart(db, specialty="ED Facility")
        db.commit()
        r = client.post(URL % chart.id,
                        json={"cc_boundary": "borderline", "passphrase": PASS})
        assert r.status_code == 400

    def test_it_is_passphrase_gated(self, client, db):
        """It changes what auditors will be asked."""
        chart = _ed_chart(db, [{"code": "99285", "modifier": "", "units": 1}])
        r = client.post(URL % chart.id,
                        json={"cc_boundary": "borderline", "passphrase": "wrong"})
        assert r.status_code == 403


class TestItReachesTheGenerator:
    def test_a_marked_chart_can_carry_the_boundary_planting(self, client, db):
        """
        End to end: the flag set here is what the generator reads. Without it
        the planting never fires, which is the whole guard.
        """
        from services.audit_mutation import MUTATION_KINDS, MutationConfig, generate

        chart = _ed_chart(db, [{"code": "99285", "modifier": "", "units": 1}])
        client.post(URL % chart.id,
                    json={"cc_boundary": "borderline", "passphrase": PASS})
        key = db.query(AnswerKey).filter(AnswerKey.chart_id == chart.id).first()

        zeros = {f: 0 for _k, f in MUTATION_KINDS}
        zeros["mix_cc_boundary"] = 100
        cfg = MutationConfig(**zeros)

        _claim, gt = generate(key, Specialty.ED_FACILITY, seed=4, cfg=cfg,
                              budget=1, cc_boundary=key.cc_boundary)
        assert gt and gt[0]["kind"] == "cc_boundary"
        assert gt[0]["claim_value"] == "99291"

        # And the same chart unmarked plants nothing.
        _claim2, gt2 = generate(key, Specialty.ED_FACILITY, seed=4, cfg=cfg,
                                budget=1, cc_boundary=None)
        assert gt2 == []
