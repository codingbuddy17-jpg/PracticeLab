"""
An audit batch must be closable even when a session was never submitted.

Closing refused while any assigned chart was outstanding, and that was the ONLY
behaviour — so an auditor who left, or simply never sat their session, left the
batch open permanently. The button was disabled with its reason in a hover
title, which is why it read as a button that does nothing.

PracticeLab has had force-close since it was built. This is the same escape
hatch, gated the same way.
"""
from models import AuditBatch, BatchStatus, Specialty
# `library` is a fixture defined in that module; pytest does not share
# fixtures across test files, so it is imported explicitly.
from tests.test_auditor_api import PASS, library  # noqa: F401

from conftest import make_chart


def _batch(db, name="Force me"):
    b = AuditBatch(name=name, specialty=Specialty.IP_DRG, created_by="t",
                   charts_per_auditor=2)
    db.add(b); db.commit()
    return b


class TestForceClose:

    def test_a_reason_is_required(self, client, db):
        b = _batch(db)
        r = client.post(f"/auditor/batches/{b.id}/force-close", json={
            "closed_by": "t", "reason": "   ", "passphrase": PASS})
        assert r.status_code == 400
        assert "reason" in r.text.lower()

    def test_the_passphrase_is_required(self, client, db):
        b = _batch(db)
        r = client.post(f"/auditor/batches/{b.id}/force-close", json={
            "closed_by": "t", "reason": "auditor left", "passphrase": "wrong"})
        assert r.status_code in (401, 403)

    def test_it_closes_and_records_why(self, client, db):
        b = _batch(db)
        r = client.post(f"/auditor/batches/{b.id}/force-close", json={
            "closed_by": "Asha", "reason": "Auditor left the team",
            "passphrase": PASS})
        assert r.status_code == 200, r.text
        assert r.json()["forced"] is True
        db.expire_all()
        got = db.query(AuditBatch).filter(AuditBatch.id == b.id).first()
        assert got.status == BatchStatus.CLOSED
        assert got.force_closed is True
        assert got.force_close_reason == "Auditor left the team"
        assert got.closed_by == "Asha"

    def test_an_already_closed_batch_is_refused(self, client, db):
        b = _batch(db)
        body = {"closed_by": "t", "reason": "x", "passphrase": PASS}
        assert client.post(f"/auditor/batches/{b.id}/force-close", json=body).status_code == 200
        r = client.post(f"/auditor/batches/{b.id}/force-close", json=body)
        assert r.status_code == 400
        assert "already closed" in r.text.lower()

    def test_an_ordinary_close_still_refuses_outstanding_work(self, client, db, library):
        """
        The control. Force-close is the exception, so the rule it is an
        exception to has to still hold — otherwise this test suite would be
        happy with a force-close that had simply replaced the check.
        """
        from tests.test_auditor_api import make_batch, allocate
        batch_id = make_batch(client, charts_per=2)
        allocate(client, batch_id)
        r = client.post(f"/auditor/batches/{batch_id}/close", json={"closed_by": "t"})
        assert r.status_code == 400
        assert "not been submitted" in r.text.lower()
