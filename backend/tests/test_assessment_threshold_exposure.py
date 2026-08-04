"""
Analytics must publish the bar it judged against.

A pass rate and a score are different scales. The UI coloured pass_rate — a
share of coders — against a hardcoded 90, which is a per-paper score bar, so a
cohort where 85% of coders passed rendered red. Fixing the colours only holds
if the endpoints actually say what each figure was measured against, per paper
rather than one global number.
"""
from conftest import seed_question_pool


def _payload(name, threshold=None, coders=None):
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
    if threshold is not None:
        p["pass_threshold"] = threshold
    return p


def _sit(client, token):
    started = client.post(f"/assessment/take/{token}/start").json()
    for i, q in enumerate(started["questions"]):
        client.post(f"/assessment/take/{token}/answer", json={
            "question_index": i, "question_id": q["question_id"], "selected_answer": "A",
        })
    client.post(f"/assessment/take/{token}/submit", json={"auto_submitted": False})


def test_overview_publishes_the_default_bar(client, db):
    seed_question_pool(db)
    gen = client.post("/assessment/generate", json=_payload("P1")).json()
    _sit(client, gen["sessions"][0]["session_token"])

    d = client.get("/assessment/analytics/overview").json()
    assert d["default_pass_threshold"] == 90.0
    assert d["pass_thresholds_vary"] is False


def test_overview_flags_when_bars_differ(client, db):
    """Two papers with different bars must not be shown under one number."""
    seed_question_pool(db)
    for name, th in (("Refresher", 70), ("Certification", 95)):
        gen = client.post("/assessment/generate",
                          json=_payload(name, threshold=th)).json()
        _sit(client, gen["sessions"][0]["session_token"])

    d = client.get("/assessment/analytics/overview").json()
    assert d["pass_thresholds_vary"] is True


def test_drill_publishes_that_papers_own_bar(client, db):
    seed_question_pool(db)
    gen = client.post("/assessment/generate",
                      json=_payload("Refresher", threshold=70)).json()
    _sit(client, gen["sessions"][0]["session_token"])

    d = client.get(f"/assessment/analytics/assessment/{gen['assessment_id']}").json()
    assert d["pass_threshold"] == 70.0


def test_coder_history_carries_a_bar_per_row(client, db):
    """A coder's papers can set different bars; each row must name its own."""
    seed_question_pool(db)
    alice = [{"coder_name": "Alice", "employee_id": "E001"}]
    for name, th in (("Refresher", 70), ("Certification", 95)):
        gen = client.post("/assessment/generate",
                          json=_payload(name, threshold=th, coders=alice)).json()
        _sit(client, gen["sessions"][0]["session_token"])

    d = client.get("/assessment/analytics/coder", params={"coder_name": "Alice"}).json()
    bars = sorted(r["pass_threshold"] for r in d["session_history"])
    assert bars == [70.0, 95.0]
    assert d["pass_thresholds_vary"] is True
