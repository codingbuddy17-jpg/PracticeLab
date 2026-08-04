"""
The Coder Matrix identifies people the way the rest of the module does, and
exports the whole grid rather than the page on screen.
"""
import io

from openpyxl import load_workbook

from conftest import seed_question_pool


def _payload(name, coders):
    return {
        "assessment_name": name,
        "coders": coders,
        "duration_minutes": 60,
        "total_questions": 3,
        "specialty_mix": [{"specialty": "IP-DRG", "pct": 1.0, "topic_filter": ""}],
        "difficulty_mode": "auto",
        "generated_by": "trainer",
        "save_config": False,
        "randomise": True,
    }


def _sit(client, token):
    started = client.post(f"/assessment/take/{token}/start").json()
    for i, q in enumerate(started["questions"]):
        client.post(f"/assessment/take/{token}/answer", json={
            "question_index": i, "question_id": q["question_id"], "selected_answer": "A",
        })
    client.post(f"/assessment/take/{token}/submit", json={"auto_submitted": False})


def _run(client, db, coders):
    seed_question_pool(db)
    gen = client.post("/assessment/generate", json=_payload("Paper", coders)).json()
    for s in gen["sessions"]:
        _sit(client, s["session_token"])


def test_same_named_coders_are_separate_rows(client, db):
    """Grouping on the typed name alone merged two people into one row."""
    _run(client, db, [{"coder_name": "Alice", "employee_id": "E001"},
                      {"coder_name": "Alice", "employee_id": "E002"}])
    d = client.get("/assessment/analytics/coder-matrix").json()
    assert len(d["coders"]) == 2
    assert sorted(c["employee_id"] for c in d["coders"]) == ["E001", "E002"]


def test_matrix_publishes_the_bar_for_below_threshold(client, db):
    _run(client, db, [{"coder_name": "Alice", "employee_id": "E001"}])
    d = client.get("/assessment/analytics/coder-matrix").json()
    assert d["default_pass_threshold"] == 90.0


def test_export_returns_a_readable_workbook(client, db):
    _run(client, db, [{"coder_name": "Alice", "employee_id": "E001"},
                      {"coder_name": "Bob", "employee_id": "E002"}])
    r = client.get("/assessment/analytics/coder-matrix.xlsx")
    assert r.status_code == 200
    wb = load_workbook(io.BytesIO(r.content))
    text = "\n".join(
        " ".join(str(c) for c in row if c is not None)
        for row in wb.active.iter_rows(values_only=True)
    )
    assert "Alice" in text and "Bob" in text
    assert "E001" in text and "E002" in text


def test_export_honours_the_window(client, db):
    """The export takes the same filters as the screen."""
    seed_question_pool(db)
    for batch in ("Wave 1", "Wave 2"):
        p = _payload(f"{batch} paper", [{"coder_name": f"C-{batch}", "employee_id": batch}])
        p["batch_name"] = batch
        gen = client.post("/assessment/generate", json=p).json()
        _sit(client, gen["sessions"][0]["session_token"])

    r = client.get("/assessment/analytics/coder-matrix.xlsx", params={"batch_name": "Wave 1"})
    wb = load_workbook(io.BytesIO(r.content))
    text = "\n".join(
        " ".join(str(c) for c in row if c is not None)
        for row in wb.active.iter_rows(values_only=True)
    )
    assert "C-Wave 1" in text
    assert "C-Wave 2" not in text
