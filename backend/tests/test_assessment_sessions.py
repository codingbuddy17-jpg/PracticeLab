"""
Integration tests for the assessment session lifecycle:
  - /take/{token}          — load session info
  - /take/{token}/start    — start timer
  - /take/{token}/answer   — save answer
  - /take/{token}/submit   — submit and get score
  - Token expiry and duplicate submission handling
"""
import json

import pytest
from conftest import seed_question_pool

PASS = {"passphrase": "test-passphrase"}
from models import AssessmentSession, AssessmentResult, GeneratedAssessmentStudent

PASSPHRASE = "test-passphrase"

GENERATE_PAYLOAD = {
    "assessment_name": "Session Test",
    "coders": [{"coder_name": "Alice", "employee_id": "E001"}],
    "duration_minutes": 60,
    "total_questions": 6,
    "specialty_mix": [{"specialty": "IP-DRG", "pct": 1.0, "topic_filter": ""}],
    "difficulty_mode": "auto",
    "generated_by": "trainer",
    "save_config": False,
    "randomise": True,
}


def generate_and_get_token(client, db) -> str:
    seed_question_pool(db)
    r = client.post("/assessment/generate", json=GENERATE_PAYLOAD)
    assert r.status_code == 200
    return r.json()["sessions"][0]["session_token"]


class TestSessionLoad:
    def test_get_session_info(self, client, db):
        token = generate_and_get_token(client, db)
        r = client.get(f"/assessment/take/{token}")
        assert r.status_code == 200

    def test_session_info_counts_questions_without_revealing_them(self, client, db):
        """Before start, a coder learns how many questions await — not what they are."""
        token = generate_and_get_token(client, db)
        data = client.get(f"/assessment/take/{token}").json()
        assert data["total_questions"] == 6
        assert "questions" not in data

    def test_invalid_token_returns_404(self, client, db):
        r = client.get("/assessment/take/ASM-INVALID1")
        assert r.status_code == 404

    def test_questions_have_required_fields(self, client, db):
        token = generate_and_get_token(client, db)
        data = client.post(f"/assessment/take/{token}/start").json()
        for q in data["questions"]:
            for field in ["question_text", "option_a", "option_b", "option_c", "option_d"]:
                assert field in q, f"Question missing field: {field}"
            # Correct answer must NOT be revealed to the coder
            assert "correct_answer" not in q, "Correct answer must be hidden from coder"

    def test_session_status_is_pending_before_start(self, client, db):
        token = generate_and_get_token(client, db)
        data = client.get(f"/assessment/take/{token}").json()
        assert data.get("status") in ("pending", "not_started", None)


class TestSessionStart:
    def test_start_session(self, client, db):
        token = generate_and_get_token(client, db)
        r = client.post(f"/assessment/take/{token}/start")
        assert r.status_code == 200

    def test_start_sets_status_in_progress(self, client, db):
        token = generate_and_get_token(client, db)
        client.post(f"/assessment/take/{token}/start")
        data = client.get(f"/assessment/take/{token}").json()
        assert data.get("status") == "in_progress"

    def test_start_twice_is_idempotent(self, client, db):
        """Starting an already-started session should not error."""
        token = generate_and_get_token(client, db)
        client.post(f"/assessment/take/{token}/start")
        r = client.post(f"/assessment/take/{token}/start")
        assert r.status_code == 200


class TestAnswerSaving:
    def _started_session(self, client, db):
        token = generate_and_get_token(client, db)
        questions = client.post(f"/assessment/take/{token}/start").json()["questions"]
        return token, questions

    def test_save_answer(self, client, db):
        token, qs = self._started_session(client, db)
        r = client.post(f"/assessment/take/{token}/answer", json={
            "question_index": 0,
            "question_id": qs[0].get("question_id", str(qs[0].get("id", ""))),
            "selected_answer": "A",
        })
        assert r.status_code == 200

    def test_save_null_answer(self, client, db):
        """Clearing an answer (null) should be accepted."""
        token, qs = self._started_session(client, db)
        r = client.post(f"/assessment/take/{token}/answer", json={
            "question_index": 0,
            "question_id": qs[0].get("question_id", str(qs[0].get("id", ""))),
            "selected_answer": None,
        })
        assert r.status_code == 200

    def test_save_all_answers(self, client, db):
        token, qs = self._started_session(client, db)
        for i, q in enumerate(qs):
            r = client.post(f"/assessment/take/{token}/answer", json={
                "question_index": i,
                "question_id": q.get("question_id", str(q.get("id", ""))),
                "selected_answer": "A",
            })
            assert r.status_code == 200, f"Failed on question {i}"


class TestSessionSubmit:
    def _submit_session(self, client, db, answer_all=True):
        token = generate_and_get_token(client, db)
        questions = client.post(f"/assessment/take/{token}/start").json()["questions"]
        if answer_all:
            for i, q in enumerate(questions):
                client.post(f"/assessment/take/{token}/answer", json={
                    "question_index": i,
                    "question_id": q.get("question_id", str(q.get("id", ""))),
                    "selected_answer": "A",
                })
        return token, questions

    @staticmethod
    def _served_key(db, token):
        """question_id -> correct letter, as actually served to this coder."""
        session = db.query(AssessmentSession).filter(
            AssessmentSession.session_token == token
        ).first()
        slot = db.query(GeneratedAssessmentStudent).filter(
            GeneratedAssessmentStudent.id == session.student_slot_id
        ).first()
        qs = slot.questions_json
        if isinstance(qs, str):
            qs = json.loads(qs)
        return {q["question_id"]: q["correct_answer"] for q in qs}

    def test_submit_returns_200(self, client, db):
        token, _ = self._submit_session(client, db)
        r = client.post(f"/assessment/take/{token}/submit", json={"auto_submitted": False})
        assert r.status_code == 200

    def test_submit_withholds_the_score_from_the_coder(self, client, db):
        """The trainer releases results; the submit response must not leak them."""
        token, _ = self._submit_session(client, db)
        data = client.post(f"/assessment/take/{token}/submit",
                           json={"auto_submitted": False}).json()
        assert data["submitted"] is True
        assert "score_pct" not in data and "correct_count" not in data

    def test_score_is_100_when_all_correct(self, client, db):
        """
        The seed bank marks 'A' correct everywhere, but generation shuffles the
        options per coder, so the served letter differs. Answer from the coder's
        own served key, not from the bank.
        """
        token, questions = self._submit_session(client, db, answer_all=False)
        key = self._served_key(db, token)
        for i, q in enumerate(questions):
            client.post(f"/assessment/take/{token}/answer", json={
                "question_index": i,
                "question_id": q["question_id"],
                "selected_answer": key[q["question_id"]],
            })
        client.post(f"/assessment/take/{token}/submit", json={"auto_submitted": False})
        session = db.query(AssessmentSession).filter(
            AssessmentSession.session_token == token
        ).first()
        result = db.query(AssessmentResult).filter(
            AssessmentResult.session_id == session.id
        ).first()
        assert result.score_pct == pytest.approx(100.0, abs=1.0)

    def test_submit_twice_returns_error(self, client, db):
        token, _ = self._submit_session(client, db)
        client.post(f"/assessment/take/{token}/submit", json={"auto_submitted": False})
        r = client.post(f"/assessment/take/{token}/submit", json={"auto_submitted": False})
        assert r.status_code in (400, 409, 422)

    def test_auto_submit_flag_recorded(self, client, db):
        token, _ = self._submit_session(client, db)
        r = client.post(f"/assessment/take/{token}/submit", json={"auto_submitted": True})
        assert r.status_code == 200
        session = db.query(AssessmentSession).filter(
            AssessmentSession.session_token == token
        ).first()
        assert session.auto_submitted is True


class TestSessionsList:
    def test_list_sessions_for_assessment(self, client, db):
        seed_question_pool(db)
        gen = client.post("/assessment/generate", json=GENERATE_PAYLOAD).json()
        assessment_id = gen["assessment_id"]
        r = client.get(f"/assessment/{assessment_id}/sessions", params=PASS)
        assert r.status_code == 200
        data = r.json()
        assert "sessions" in data
        assert len(data["sessions"]) == 1  # 1 coder

    def test_session_row_has_token(self, client, db):
        seed_question_pool(db)
        gen = client.post("/assessment/generate", json=GENERATE_PAYLOAD).json()
        assessment_id = gen["assessment_id"]
        sessions = client.get(f"/assessment/{assessment_id}/sessions", params=PASS).json()["sessions"]
        assert sessions[0]["session_token"].startswith("ASM-")
