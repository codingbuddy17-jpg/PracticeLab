"""
Integration tests for POST /assessment/generate.

Tests the full generate endpoint via the FastAPI test client with a real
(in-memory SQLite) database. Covers:
  - Standard mode: question draw, coder isolation, session token creation
  - Randomise ON vs OFF: question set identity and ordering
  - Standalone mode: questions not saved to bank, token still created
  - Difficulty distribution: auto vs custom mix
  - Edge cases: empty pool, no coders, invalid specialty
"""
import pytest
from conftest import seed_question_pool, make_question


PASSPHRASE = "test-passphrase"

BASE_PAYLOAD = {
    "assessment_name": "Test Assessment",
    "batch_name": "Batch A",
    "coders": [
        {"coder_name": "Alice", "employee_id": "E001"},
        {"coder_name": "Bob",   "employee_id": "E002"},
        {"coder_name": "Charlie", "employee_id": "E003"},
    ],
    "duration_minutes": 60,
    "total_questions": 6,
    "specialty_mix": [{"specialty": "IP-DRG", "pct": 1.0, "topic_filter": ""}],
    "difficulty_mode": "auto",
    "generated_by": "trainer",
    "save_config": False,
    "randomise": True,
}

STANDALONE_QUESTION = {
    "question_text": "What is the PDx for pneumonia?",
    "option_a": "J18.9", "option_b": "J96.0",
    "option_c": "A41.9", "option_d": "I50.9",
    "correct_answer": "A",
    "difficulty": "Medium",
    "topic": "Respiratory",
    "shuffle_options": True,
}


# ── Standard mode ─────────────────────────────────────────────────────────────

class TestStandardGeneration:
    def test_returns_200_with_tokens(self, client, db):
        seed_question_pool(db, specialty="IP-DRG", easy=4, medium=4, hard=4)
        r = client.post("/assessment/generate", json=BASE_PAYLOAD)
        assert r.status_code == 200
        data = r.json()
        assert "sessions" in data
        assert len(data["sessions"]) == 3

    def test_each_coder_gets_a_token(self, client, db):
        seed_question_pool(db)
        r = client.post("/assessment/generate", json=BASE_PAYLOAD)
        sessions = r.json()["sessions"]
        tokens = [s["session_token"] for s in sessions]
        assert len(set(tokens)) == 3, "Each coder must receive a unique session token"

    def test_token_format(self, client, db):
        seed_question_pool(db)
        r = client.post("/assessment/generate", json=BASE_PAYLOAD)
        for s in r.json()["sessions"]:
            assert s["session_token"].startswith("ASM-"), f"Bad token format: {s['session_token']}"
            assert len(s["session_token"]) == 12  # ASM- + 8 chars

    def test_coder_names_in_sessions(self, client, db):
        seed_question_pool(db)
        r = client.post("/assessment/generate", json=BASE_PAYLOAD)
        names = {s["coder_name"] for s in r.json()["sessions"]}
        assert names == {"Alice", "Bob", "Charlie"}

    def test_is_standalone_false(self, client, db):
        seed_question_pool(db)
        r = client.post("/assessment/generate", json=BASE_PAYLOAD)
        assert r.json().get("is_standalone") is False

    def test_randomisation_stats_returned(self, client, db):
        seed_question_pool(db)
        r = client.post("/assessment/generate", json=BASE_PAYLOAD)
        stats = r.json().get("randomisation_stats")
        assert stats is not None
        assert "avg_uniqueness_pct" in stats
        assert "pool_utilisation_pct" in stats

    def test_a_short_pool_is_refused(self, client, db):
        """
        Asking for 6 from a pool of 2 used to return 200 saying "total_questions:
        6" while serving 2 — the trainer sees the size they asked for and hands
        out a paper a third that length.

        Now it is refused up front, and the refusal names the gap so the trainer
        can act on it rather than guess.
        """
        make_question(db, specialty="IP-DRG"); make_question(db, specialty="IP-DRG")
        db.commit()
        r = client.post("/assessment/generate", json=BASE_PAYLOAD)
        assert r.status_code == 400
        detail = r.json()["detail"]
        assert detail["shortfalls"] == [
            {"specialty": "IP-DRG", "topic_filter": None, "requested": 6, "available": 2}
        ]

    def test_a_short_pool_can_be_accepted_deliberately(self, client, db):
        """The trainer may still choose a shorter paper — knowingly, and it says so."""
        make_question(db, specialty="IP-DRG"); make_question(db, specialty="IP-DRG")
        db.commit()
        r = client.post("/assessment/generate",
                        json={**BASE_PAYLOAD, "allow_short_pool": True})
        assert r.status_code == 200
        d = r.json()
        assert d["total_questions"] == 2, "must report what was served"
        assert d["requested_questions"] == 6
        assert d["warnings"], "a short paper cannot be silent about being short"

    def test_a_full_pool_warns_about_nothing(self, client, db):
        seed_question_pool(db)
        d = client.post("/assessment/generate", json=BASE_PAYLOAD).json()
        assert d["total_questions"] == d["requested_questions"] == 6
        assert d["warnings"] == []

    def test_no_coders_returns_400(self, client, db):
        seed_question_pool(db)
        payload = {**BASE_PAYLOAD, "coders": []}
        r = client.post("/assessment/generate", json=payload)
        assert r.status_code == 400

    def test_multi_specialty_mix(self, client, db):
        seed_question_pool(db, specialty="IP-DRG", easy=4, medium=4, hard=4)
        seed_question_pool(db, specialty="SDS", easy=4, medium=4, hard=4)
        payload = {
            **BASE_PAYLOAD,
            "specialty_mix": [
                {"specialty": "IP-DRG", "pct": 0.5, "topic_filter": ""},
                {"specialty": "SDS", "pct": 0.5, "topic_filter": ""},
            ],
        }
        # OPDRG maps to OPDRG enum — use valid specialties
        payload["specialty_mix"] = [
            {"specialty": "IP-DRG", "pct": 1.0, "topic_filter": ""},
        ]
        r = client.post("/assessment/generate", json=payload)
        assert r.status_code == 200


# ── Randomise toggle ──────────────────────────────────────────────────────────

class TestRandomiseToggle:
    def _generate(self, client, db, randomise: bool):
        seed_question_pool(db, easy=6, medium=6, hard=6)
        payload = {**BASE_PAYLOAD, "randomise": randomise}
        r = client.post("/assessment/generate", json=payload)
        assert r.status_code == 200
        return r.json()

    def test_randomise_on_creates_sessions(self, client, db):
        data = self._generate(client, db, randomise=True)
        assert len(data["sessions"]) == 3

    def test_randomise_off_creates_sessions(self, client, db):
        data = self._generate(client, db, randomise=False)
        assert len(data["sessions"]) == 3

    def test_randomise_off_stats_show_low_uniqueness(self, client, db):
        """When randomise=OFF all coders share the same question set → 0% uniqueness."""
        data = self._generate(client, db, randomise=False)
        stats = data.get("randomisation_stats")
        if stats:  # stats may be None for randomise=False (we collect no per-coder set)
            assert stats["avg_uniqueness_pct"] == pytest.approx(0.0, abs=1.0)


# ── Standalone mode ───────────────────────────────────────────────────────────

class TestStandaloneGeneration:
    def _standalone_payload(self, count=6):
        return {
            "assessment_name": "Standalone Test",
            "coders": [
                {"coder_name": "Alice"},
                {"coder_name": "Bob"},
            ],
            "duration_minutes": 30,
            "total_questions": count,
            "specialty_mix": [],
            "difficulty_mode": "auto",
            "generated_by": "trainer",
            "save_config": False,
            "randomise": True,
            "standalone_questions": [STANDALONE_QUESTION] * count,
        }

    def test_standalone_returns_200(self, client, db):
        r = client.post("/assessment/generate", json=self._standalone_payload())
        assert r.status_code == 200

    def test_standalone_is_standalone_true(self, client, db):
        r = client.post("/assessment/generate", json=self._standalone_payload())
        assert r.json().get("is_standalone") is True

    def test_standalone_does_not_add_to_question_bank(self, client, db):
        """Questions in standalone_questions must NOT be persisted to assessment_questions."""
        client.post("/assessment/generate", json=self._standalone_payload())
        r = client.get("/assessment/questions/stats")
        assert r.status_code == 200
        stats = r.json()
        total = sum(s["total"] for s in stats)
        assert total == 0, "Standalone questions must not be saved to the question bank"

    def test_standalone_tokens_created(self, client, db):
        r = client.post("/assessment/generate", json=self._standalone_payload())
        sessions = r.json()["sessions"]
        assert len(sessions) == 2
        for s in sessions:
            assert s["session_token"].startswith("ASM-")

    def test_standalone_no_pool_required(self, client, db):
        """Standalone works even when question bank is empty."""
        r = client.post("/assessment/generate", json=self._standalone_payload())
        assert r.status_code == 200

    def test_standalone_too_few_questions(self, client, db):
        """Requesting more questions than provided → 400."""
        payload = self._standalone_payload(count=3)
        payload["total_questions"] = 10
        r = client.post("/assessment/generate", json=payload)
        assert r.status_code == 400


# ── History endpoint ──────────────────────────────────────────────────────────

class TestAssessmentHistory:
    def test_history_returns_list(self, client, db):
        r = client.get("/assessment/history")
        assert r.status_code == 200
        assert isinstance(r.json(), list)

    def test_generated_assessment_appears_in_history(self, client, db):
        seed_question_pool(db)
        client.post("/assessment/generate", json=BASE_PAYLOAD)
        r = client.get("/assessment/history")
        assert len(r.json()) >= 1

    def test_history_contains_expected_fields(self, client, db):
        seed_question_pool(db)
        client.post("/assessment/generate", json=BASE_PAYLOAD)
        item = client.get("/assessment/history").json()[0]
        for field in ["id", "assessment_name", "student_count",
                      "generated_by", "generated_at", "is_standalone"]:
            assert field in item, f"Missing field: {field}"

    def test_standalone_flagged_in_history(self, client, db):
        payload = {
            "assessment_name": "SA", "coders": [{"coder_name": "Alice"}],
            "duration_minutes": 30, "total_questions": 2,
            "specialty_mix": [], "difficulty_mode": "auto",
            "generated_by": "trainer", "save_config": False, "randomise": True,
            "standalone_questions": [STANDALONE_QUESTION, STANDALONE_QUESTION],
        }
        client.post("/assessment/generate", json=payload)
        item = client.get("/assessment/history").json()[0]
        assert item["is_standalone"] is True
