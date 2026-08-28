"""
One device at a time on a session, and the claim expires.

A practice access code opened on a second machine while the first was mid-chart
and both were live, because the code was the whole credential. A hard
single-use lock would strand anyone who closed a tab, so the claim goes stale
instead — and that same mechanism is the idle timeout the owner asked for. The
two are one feature, which is why they are tested together.

Nothing is destroyed when a claim lapses: drafts are saved as the coder types,
and re-entering the code re-claims the session with the work still there.
"""
from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import text

from services.session_claim import IDLE_MINUTES, check, is_stale


class TestTheRule:
    """The decision itself, before any HTTP."""

    def _now(self):
        return datetime.now(timezone.utc)

    def test_an_unclaimed_session_is_granted(self):
        assert check(None, None, "A") == "A"

    def test_the_holder_keeps_it(self):
        assert check("A", self._now(), "A") == "A"

    def test_another_device_is_refused_while_the_claim_is_fresh(self):
        with pytest.raises(Exception) as e:
            check("A", self._now() - timedelta(minutes=5), "B")
        assert e.value.status_code == 409
        assert "another device" in e.value.detail

    def test_the_refusal_says_how_to_get_in(self):
        """A 409 a coder cannot act on is just a locked door."""
        with pytest.raises(Exception) as e:
            check("A", self._now() - timedelta(minutes=5), "B")
        assert "Close it there" in e.value.detail
        assert str(IDLE_MINUTES) in e.value.detail

    def test_an_idle_claim_can_be_taken_over(self):
        old = self._now() - timedelta(minutes=IDLE_MINUTES + 1)
        assert check("A", old, "B") == "B"

    def test_a_claim_just_inside_the_window_still_holds(self):
        """The boundary, so the timeout is the stated hour and not roughly it."""
        recent = self._now() - timedelta(minutes=IDLE_MINUTES - 1)
        assert not is_stale(recent)
        with pytest.raises(Exception):
            check("A", recent, "B")

    def test_a_client_that_sends_no_device_is_not_locked_out(self):
        """Older clients keep working — they simply get no protection."""
        assert check("A", self._now(), "") == "A"


class TestOverHttp:

    def _session(self, db, token="TOKDEV1", status="in_progress"):
        from models import Batch, BatchStatus, Chart, ChartStatus, Difficulty, Specialty
        import json
        c = Chart(chart_number="IP800", specialty=Specialty.IP_DRG, category="C",
                  difficulty=Difficulty.INTERMEDIATE, status=ChartStatus.ACTIVE,
                  uploaded_by="t")
        b = Batch(name="Dev", specialty=Specialty.IP_DRG, status=BatchStatus.OPEN,
                  created_by="t", charts_per_coder=1, is_direct_assignment=False,
                  use_weighted=True, use_dpo=False, force_closed=False)
        db.add_all([c, b]); db.commit()
        db.execute(text("""INSERT INTO practice_sessions
            (batch_id, coder_name, specialty, token, chart_ids, status)
            VALUES (:b,'Asha','IP-DRG',:t,:ci,:st)"""),
            {"b": b.id, "t": token, "ci": json.dumps([c.id]), "st": status})
        db.commit()
        return token

    def test_the_second_device_is_refused(self, client, db):
        tok = self._session(db)
        assert client.get(f"/practicelab/practice-sessions/by-token/{tok}",
                          params={"device": "laptop"}).status_code == 200
        r = client.get(f"/practicelab/practice-sessions/by-token/{tok}",
                       params={"device": "phone"})
        assert r.status_code == 409, r.text
        # and the first device still works
        assert client.get(f"/practicelab/practice-sessions/by-token/{tok}",
                          params={"device": "laptop"}).status_code == 200

    def test_an_idle_session_can_be_picked_up_elsewhere(self, client, db):
        tok = self._session(db)
        assert client.get(f"/practicelab/practice-sessions/by-token/{tok}",
                          params={"device": "laptop"}).status_code == 200
        db.execute(text(
            "UPDATE practice_sessions SET last_seen_at=:t WHERE token=:tok"),
            {"t": datetime.now(timezone.utc) - timedelta(minutes=IDLE_MINUTES + 5),
             "tok": tok})
        db.commit()
        r = client.get(f"/practicelab/practice-sessions/by-token/{tok}",
                       params={"device": "phone"})
        assert r.status_code == 200, "an idle claim should be takeable"

    def test_a_submitted_session_is_readable_from_anywhere(self, client, db):
        """
        It is a record, not work. Refusing would take a coder's own feedback
        away from them, and two people reading a finished result harm nothing.
        """
        tok = self._session(db, token="TOKDEV2", status="submitted")
        assert client.get(f"/practicelab/practice-sessions/by-token/{tok}",
                          params={"device": "laptop"}).status_code == 200
        assert client.get(f"/practicelab/practice-sessions/by-token/{tok}",
                          params={"device": "phone"}).status_code == 200

    def test_saving_a_draft_keeps_the_claim_alive(self, client, db):
        """
        Without this, an hour of steady typing would let the claim go stale
        underneath the coder — nothing but re-opening the session touched it.
        """
        tok = self._session(db, token="TOKDEV3")
        info = client.get(f"/practicelab/practice-sessions/by-token/{tok}",
                          params={"device": "laptop"}).json()
        stale = datetime.now(timezone.utc) - timedelta(minutes=IDLE_MINUTES + 5)
        db.execute(text("UPDATE practice_sessions SET last_seen_at=:t WHERE token=:tok"),
                   {"t": stale, "tok": tok})
        db.commit()

        client.post(f"/practicelab/practice-sessions/{info['session_id']}/save-draft",
                    json={"device": "laptop", "entries": []})
        # The heartbeat refreshed it, so another device is refused again.
        assert client.get(f"/practicelab/practice-sessions/by-token/{tok}",
                          params={"device": "phone"}).status_code == 409
