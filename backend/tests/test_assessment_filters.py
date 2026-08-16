"""
Assessment analytics answer for a window, not for all time.

Two things had to hold. The window must be applied in SQL — the overview used
to load every session and every result into Python and filter them with list
comprehensions, with no date bound at all. And it must be applied to a date
that every session has: filtering on submitted_at alone silently drops
pending, expired and abandoned sessions, which are exactly the rows completion
rate exists to count.
"""
from datetime import timedelta

from sqlalchemy import text

from conftest import seed_question_pool

from models import AssessmentSession
from services.timeutil import utc_now


def _payload(name, batch=None, coders=None):
    p = {
        "assessment_name": name,
        "coders": coders or [{"coder_name": "Alice", "employee_id": "E001"}],
        "duration_minutes": 60,
        "total_questions": 3,
        "specialty_mix": [{"specialty": "IP-DRG", "pct": 1.0, "topic_filter": ""}],
        "difficulty_mode": "auto",
        "generated_by": "trainer",
        "save_config": False,
        "randomise": True,
    }
    if batch:
        p["batch_name"] = batch
    return p


def _sit(client, token):
    started = client.post(f"/assessment/take/{token}/start").json()
    for i, q in enumerate(started["questions"]):
        client.post(f"/assessment/take/{token}/answer", json={
            "question_index": i, "question_id": q["question_id"], "selected_answer": "A",
        })
    client.post(f"/assessment/take/{token}/submit", json={"auto_submitted": False})


def _make(client, db, name, batch=None, sit=True, days_ago=0):
    gen = client.post("/assessment/generate", json=_payload(name, batch)).json()
    token = gen["sessions"][0]["session_token"]
    if sit:
        _sit(client, token)
    if days_ago:
        when = utc_now() - timedelta(days=days_ago)
        db.execute(text(
            "UPDATE assessment_sessions SET submitted_at=:w, created_at=:w"
            " WHERE session_token=:t"
        ), {"w": when, "t": token})
        db.commit()
    return gen["assessment_id"], token


def _overview(client, **params):
    r = client.get("/assessment/analytics/overview", params=params)
    assert r.status_code == 200, r.text
    return r.json()


def test_unfiltered_overview_sees_everything(client, db):
    seed_question_pool(db)
    _make(client, db, "Recent")
    _make(client, db, "Old", days_ago=90)
    assert _overview(client)["total_submitted"] == 2


def test_date_from_excludes_older_work(client, db):
    seed_question_pool(db)
    _make(client, db, "Recent")
    _make(client, db, "Old", days_ago=90)
    cutoff = (utc_now() - timedelta(days=30)).date().isoformat()
    assert _overview(client, date_from=cutoff)["total_submitted"] == 1


def test_date_to_is_inclusive_of_its_own_day(client, db):
    """A trainer picking 1-31 March means all of the 31st."""
    seed_question_pool(db)
    _make(client, db, "Today")
    today = utc_now().date().isoformat()
    assert _overview(client, date_to=today)["total_submitted"] == 1


def test_batch_filter_isolates_a_cohort(client, db):
    seed_question_pool(db)
    _make(client, db, "W1 paper", batch="Wave 1")
    _make(client, db, "W2 paper", batch="Wave 2")

    assert _overview(client)["total_submitted"] == 2
    assert _overview(client, batch_name="Wave 1")["total_submitted"] == 1


def test_an_unsat_session_still_counts_against_completion(client, db):
    """
    The trap: date-filtering on submitted_at would drop the never-submitted
    session, and completion rate would report 100% for a window where half the
    coders never turned up.
    """
    seed_question_pool(db)
    _make(client, db, "Sat")
    _make(client, db, "Never sat", sit=False)

    today = utc_now().date().isoformat()
    d = _overview(client, date_from=today, date_to=today)
    assert d["total_sessions"] == 2, "the unsat session must remain in the window"
    assert d["total_submitted"] == 1
    assert d["completion_rate"] == 50.0


def test_headline_assessment_count_matches_the_window(client, db):
    """The count of assessments must not contradict the figures beside it."""
    seed_question_pool(db)
    _make(client, db, "W1 paper", batch="Wave 1")
    _make(client, db, "W2 paper", batch="Wave 2")

    d = _overview(client, batch_name="Wave 1")
    assert d["total_assessments"] == 1
    assert len(d["per_assessment_pass_rates"]) == 1


def test_by_specialty_and_by_topic_honour_the_window(client, db):
    seed_question_pool(db)
    _make(client, db, "W1 paper", batch="Wave 1")
    _make(client, db, "W2 paper", batch="Wave 2")

    for route, key in (("by-specialty", "specialties"), ("by-topic", "topics")):
        wide = client.get(f"/assessment/analytics/{route}").json()[key]
        narrow = client.get(f"/assessment/analytics/{route}",
                            params={"batch_name": "Wave 1"}).json()[key]
        wide_n = sum(x["total_responses"] for x in wide)
        narrow_n = sum(x["total_responses"] for x in narrow)
        assert narrow_n < wide_n, f"{route} ignored the batch filter"


def test_coder_matrix_honours_the_window(client, db):
    seed_question_pool(db)
    _make(client, db, "W1 paper", batch="Wave 1")
    _make(client, db, "W2 paper", batch="Wave 2")

    narrow = client.get("/assessment/analytics/coder-matrix",
                        params={"batch_name": "Wave 1"}).json()
    assert narrow["coders"], "filter must not empty the matrix entirely"


def test_a_nonsense_date_is_ignored_not_fatal(client, db):
    seed_question_pool(db)
    _make(client, db, "Recent")
    assert _overview(client, date_from="not-a-date")["total_submitted"] == 1


def test_unsat_papers_cannot_push_scored_ones_off_the_chart(client, db):
    """
    The bar chart selects papers WITH results first, then the ten most recent
    of those.

    Taking the ten newest and dropping the unscored afterwards meant a run of
    freshly generated papers nobody had sat could push every scored paper out
    of the window — the chart drew four bars, or none, while the data existed
    the whole time. Eleven unsat papers here is one more than the limit, which
    is exactly the case that used to empty it.
    """
    seed_question_pool(db)
    _make(client, db, "Scored paper", sit=True)
    for i in range(11):
        _make(client, db, f"Never sat {i}", sit=False)

    rates = _overview(client)["per_assessment_pass_rates"]
    names = [r["assessment_name"] for r in rates]
    assert names == ["Scored paper"], (
        f"the only scored paper must still be charted; got {names}")


def test_the_chart_keeps_the_ten_most_recent_scored_papers(client, db):
    seed_question_pool(db)
    for i in range(12):
        _make(client, db, f"Paper {i:02d}", sit=True)
    rates = _overview(client)["per_assessment_pass_rates"]
    assert len(rates) == 10, "still capped at ten"
    # oldest two drop off, and the list reads oldest-to-newest for the chart
    assert "Paper 00" not in [r["assessment_name"] for r in rates]
    assert "Paper 11" in [r["assessment_name"] for r in rates]
