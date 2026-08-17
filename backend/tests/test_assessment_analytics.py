"""
Assessment analytics: the pass bar and coder identity.

Both were the same class of fault the PracticeLab review kept turning up — a
threshold hardcoded where it could not be seen or changed, and an identity
grouped by a typed name when the id was sitting in the row.
"""
from datetime import datetime, timedelta, timezone

import pytest

from models import (GeneratedAssessment, GeneratedAssessmentStudent,
                    AssessmentSession, AssessmentResult, AssessmentResponse)


def _assessment(db, name="A", threshold=None, batch=None):
    a = GeneratedAssessment(assessment_name=name, batch_name=batch, student_count=1,
                            generated_by="t", pass_threshold=threshold)
    db.add(a); db.commit()
    return a


def _session(db, a, coder, emp=None, token=None, score=None, status="submitted"):
    from datetime import datetime, timedelta, timezone
    st = GeneratedAssessmentStudent(assessment_id=a.id, student_label=coder,
                                    questions_json="[]")
    db.add(st); db.commit()
    s = AssessmentSession(
        session_token=token or f"TOK{a.id}{coder}{st.id}",
        assessment_id=a.id, student_slot_id=st.id,
        coder_name=coder, employee_id=emp, duration_minutes=30,
        expires_at=datetime.now(timezone.utc) + timedelta(hours=8),
        status=status,
    )
    db.add(s); db.commit()
    if score is not None:
        db.add(AssessmentResult(session_id=s.id, total_questions=10,
                                correct_count=int(score / 10), score_pct=score))
        db.commit()
    return s


class TestConfigurablePassMark:
    def test_each_assessment_is_judged_against_its_own_bar(self, client, db):
        """
        A single module constant made every paper share one mark, invisible to
        the trainer setting it. A refresher and a certification gate are not
        the same test.
        """
        easy = _assessment(db, "Refresher", threshold=60)
        hard = _assessment(db, "Certification", threshold=95)
        _session(db, easy, "A", "E1", score=70)      # clears 60
        _session(db, hard, "B", "E2", score=70)      # misses 95
        body = client.get("/assessment/analytics/overview").json()
        assert body["overall_pass_rate"] == 50.0

    def test_the_old_default_still_applies_where_no_bar_was_set(self, client, db):
        """Existing assessments must not move underneath anyone."""
        a = _assessment(db, "Legacy", threshold=None)
        _session(db, a, "A", "E1", score=92)
        _session(db, a, "B", "E2", score=88)
        body = client.get("/assessment/analytics/overview").json()
        assert body["default_pass_threshold"] == 90.0
        assert body["overall_pass_rate"] == 50.0, "92 clears 90, 88 does not"

    def test_the_overview_says_whether_bars_differ(self, client, db):
        """A pass rate spanning papers with different marks needs saying so."""
        _session(db, _assessment(db, "One", threshold=60), "A", "E1", score=70)
        assert client.get("/assessment/analytics/overview").json()["pass_thresholds_vary"] is False
        _session(db, _assessment(db, "Two", threshold=95), "B", "E2", score=70)
        assert client.get("/assessment/analytics/overview").json()["pass_thresholds_vary"] is True

    def test_a_generated_assessment_can_carry_a_bar(self, client, db):
        a = _assessment(db, "Set", threshold=75)
        assert db.query(GeneratedAssessment).filter_by(id=a.id).one().pass_threshold == 75


class TestCoderIdentity:
    def test_one_person_entered_two_ways_is_one_coder(self, client, db):
        """
        employee_id was captured at generation and stored on the session all
        along — the aggregations simply grouped by the typed name.
        """
        a = _assessment(db, "A")
        _session(db, a, "Asha R", "E1", token="T1", score=90)
        _session(db, a, "asha  r", "E1", token="T2", score=90)
        body = client.get("/assessment/analytics/overview").json()
        assert body["unique_coders_assessed"] == 1

    def test_coders_without_an_id_fall_back_to_their_name(self, client, db):
        a = _assessment(db, "A")
        _session(db, a, "No Id One", None, token="T3", score=90)
        _session(db, a, "No Id Two", None, token="T4", score=90)
        assert client.get("/assessment/analytics/overview").json()["unique_coders_assessed"] == 2

    def test_the_batch_view_counts_people_not_spellings(self, client, db):
        a = _assessment(db, "A", batch="June")
        _session(db, a, "Asha R", "E1", token="B1", score=90)
        _session(db, a, "ASHA R", "E1", token="B2", score=90)
        rows = client.get("/assessment/analytics/by-batch").json()["batches"]
        june = next(r for r in rows if r["batch_name"] == "June")
        assert june["total_coders"] == 1

    def test_batch_view_counts_issued_coders_not_only_submitters(self, client, db):
        a = _assessment(db, "A", batch="June")
        _session(db, a, "Asha R", "E1", token="BI1", score=90)
        _session(db, a, "Ben K", "E2", token="BI2", status="pending")

        rows = client.get("/assessment/analytics/by-batch").json()["batches"]
        june = next(r for r in rows if r["batch_name"] == "June")
        assert june["total_coders"] == 2
        assert june["submitted_count"] == 1
        assert june["issued_count"] == 2
        assert june["completion_rate"] == 50.0
        assert june["pending_count"] == 1


class TestMixedBarsInAggregates:
    def test_a_batch_spanning_two_bars_judges_each_paper_correctly(self, client, db):
        """
        A bare list of scores cannot be re-judged later against one mark
        without lying, so the pass flag travels with the score.
        """
        easy = _assessment(db, "Easy", threshold=50, batch="Mixed")
        hard = _assessment(db, "Hard", threshold=95, batch="Mixed")
        _session(db, easy, "A", "E1", token="M1", score=60)     # clears 50
        _session(db, hard, "B", "E2", token="M2", score=60)     # misses 95
        rows = client.get("/assessment/analytics/by-batch").json()["batches"]
        mixed = next(r for r in rows if r["batch_name"] == "Mixed")
        assert mixed["pass_rate"] == 50.0


class TestBatchKeys:
    def test_a_real_batch_named_ungrouped_does_not_merge_with_null_batch(self, client, db):
        real = _assessment(db, "Named", batch="Ungrouped")
        loose = _assessment(db, "Loose", batch=None)
        _session(db, real, "Named Coder", "E1", token="UG1", score=90)
        _session(db, loose, "Loose Coder", "E2", token="UG2", score=50)

        rows = client.get("/assessment/analytics/by-batch").json()["batches"]
        assert len([r for r in rows if r["batch_name"] == "Ungrouped"]) == 2
        named = next(r for r in rows if r["batch_key"] == "name:Ungrouped")
        null = next(r for r in rows if r["batch_key"] == "__ungrouped__")
        assert named["avg_score"] == 90.0
        assert null["avg_score"] == 50.0

        drill = client.get("/assessment/analytics/batch-drill",
                           params={"batch_key": "name:Ungrouped"}).json()
        assert drill["avg_score"] == 90.0


class TestAssessmentDrilldown:
    def test_topic_and_difficulty_use_pooled_response_accuracy(self, client, db):
        """
        Randomised papers can give each question a different response count.
        The drilldown should report pooled accuracy, not an average of question
        percentages that gives low-exposure questions the same weight.
        """
        a = _assessment(db, "Uneven drill")
        questions = [
            {"question_id": "Q1", "question_text": "Common question", "topic": "Diabetes", "difficulty": "Easy"},
            {"question_id": "Q2", "question_text": "Less seen question", "topic": "Diabetes", "difficulty": "Easy"},
        ]
        slots = [
            GeneratedAssessmentStudent(assessment_id=a.id, student_label="Asha", questions_json=questions),
            GeneratedAssessmentStudent(assessment_id=a.id, student_label="Ben", questions_json=questions[:1]),
        ]
        db.add_all(slots)
        db.commit()

        expires = datetime.now(timezone.utc) + timedelta(hours=8)
        sessions = [
            AssessmentSession(session_token="DRILL1", assessment_id=a.id, student_slot_id=slots[0].id,
                              coder_name="Asha", employee_id="E1", duration_minutes=30,
                              expires_at=expires, status="submitted"),
            AssessmentSession(session_token="DRILL2", assessment_id=a.id, student_slot_id=slots[1].id,
                              coder_name="Ben", employee_id="E2", duration_minutes=30,
                              expires_at=expires, status="submitted"),
        ]
        db.add_all(sessions)
        db.commit()
        db.add_all([
            AssessmentResult(session_id=sessions[0].id, total_questions=2, correct_count=1, score_pct=50),
            AssessmentResult(session_id=sessions[1].id, total_questions=1, correct_count=1, score_pct=100),
            AssessmentResponse(session_id=sessions[0].id, question_index=0, question_id="Q1",
                               selected_answer="A", is_correct=True),
            AssessmentResponse(session_id=sessions[0].id, question_index=1, question_id="Q2",
                               selected_answer="B", is_correct=False),
            AssessmentResponse(session_id=sessions[1].id, question_index=0, question_id="Q1",
                               selected_answer="A", is_correct=True),
        ])
        db.commit()

        body = client.get(f"/assessment/analytics/assessment/{a.id}").json()
        topic = body["topic_breakdown"][0]
        difficulty = next(d for d in body["difficulty_calibration"] if d["difficulty"] == "Easy")

        assert topic["avg_accuracy"] == 66.7
        assert topic["question_avg_accuracy"] == 50.0
        assert topic["correct"] == 2
        assert topic["total"] == 3
        assert difficulty["actual_accuracy"] == 66.7
        assert difficulty["question_count"] == 2


class TestSpecialtyAnalytics:
    def test_specialty_counts_unique_coders_not_sessions(self, client, db):
        a = _assessment(db, "Specialty identity")
        questions = [{
            "question_id": "S1",
            "question_text": "Specialty question",
            "specialty": "IP-DRG",
            "topic": "DRG",
            "difficulty": "Medium",
        }]
        slots = [
            GeneratedAssessmentStudent(assessment_id=a.id, student_label="Asha 1", questions_json=questions),
            GeneratedAssessmentStudent(assessment_id=a.id, student_label="Asha 2", questions_json=questions),
        ]
        db.add_all(slots)
        db.commit()

        expires = datetime.now(timezone.utc) + timedelta(hours=8)
        sessions = [
            AssessmentSession(session_token="SPEC1", assessment_id=a.id, student_slot_id=slots[0].id,
                              coder_name="Asha R", employee_id="E1", duration_minutes=30,
                              expires_at=expires, status="submitted"),
            AssessmentSession(session_token="SPEC2", assessment_id=a.id, student_slot_id=slots[1].id,
                              coder_name="asha  r", employee_id="E1", duration_minutes=30,
                              expires_at=expires, status="submitted"),
        ]
        db.add_all(sessions)
        db.commit()
        db.add_all([
            AssessmentResult(session_id=sessions[0].id, total_questions=1, correct_count=1, score_pct=100),
            AssessmentResult(session_id=sessions[1].id, total_questions=1, correct_count=0, score_pct=0),
            AssessmentResponse(session_id=sessions[0].id, question_index=0, question_id="S1",
                               selected_answer="A", is_correct=True),
            AssessmentResponse(session_id=sessions[1].id, question_index=0, question_id="S1",
                               selected_answer="B", is_correct=False),
        ])
        db.commit()

        body = client.get("/assessment/analytics/by-specialty").json()
        row = body["specialties"][0]

        assert row["specialty"] == "IP-DRG"
        assert row["coder_count"] == 1
        assert row["total_responses"] == 2
        assert row["accuracy_pct"] == 50.0
        assert body["overall_accuracy"] == 50.0
