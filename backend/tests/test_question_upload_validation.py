"""
The upload refuses malformed rows rather than reinterpreting them.

Every case here was previously accepted and quietly changed in meaning. That is
the worst failure mode for a question bank: nothing errors, the sheet looks
imported, and the damage only surfaces when a coder sits the paper.
"""
import io

import openpyxl

from models import AssessmentQuestion

MIME = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"

HEADERS = [
    "Question_ID", "Question_Text", "Option_A", "Option_B", "Option_C", "Option_D",
    "Correct_Answer", "Difficulty", "Topic", "Question_Type", "Active_Status", "Shuffle_Options",
]


def _book(rows):
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.append(HEADERS)
    for r in rows:
        ws.append(r)
    return wb


def _row(qid="", text="A question?", a="Alpha", b="Beta", c="Gamma", d="Delta",
         correct="A", difficulty="Medium", topic="T", qtype="Conceptual",
         status="Active", shuffle="Yes"):
    return [qid, text, a, b, c, d, correct, difficulty, topic, qtype, status, shuffle]


def _upload(client, wb, specialty="ICD10CM"):
    buf = io.BytesIO()
    wb.save(buf)
    return client.post(
        "/assessment/questions/upload",
        data={"specialty": specialty, "uploaded_by": "trainer"},
        files={"file": ("q.xlsx", buf.getvalue(), MIME)},
    )


def _result(client, rows, specialty="ICD10CM"):
    r = _upload(client, _book(rows), specialty)
    assert r.status_code == 200, r.text
    return r.json()


# ── options ───────────────────────────────────────────────────────────────────

def test_duplicate_option_text_is_refused(client, db):
    """
    Two identical choices give a question two right answers but grade only one.
    Option shuffling then makes WHICH one vary per coder, so two coders picking
    the same text get different marks.
    """
    d = _result(client, [_row(a="Same text", b="Same text")])
    assert d["created"] == 0
    assert any("duplicate" in e.lower() and "option" in e.lower() for e in d["errors"]), d["errors"]


def test_duplicate_options_are_caught_regardless_of_case_or_padding(client, db):
    d = _result(client, [_row(a="Sepsis", b="  sepsis ")])
    assert d["created"] == 0
    assert d["errors"]


def test_blank_option_is_refused(client, db):
    """A blank choice reaches the coder as an empty radio button."""
    d = _result(client, [_row(c="")])
    assert d["created"] == 0
    assert any("blank" in e.lower() or "empty" in e.lower() for e in d["errors"]), d["errors"]


def test_a_clean_row_still_imports(client, db):
    d = _result(client, [_row()])
    assert d["created"] == 1
    assert d["errors"] == []


# ── status ────────────────────────────────────────────────────────────────────

def test_a_typo_in_active_status_is_refused_not_retired(client, db):
    """'Actve' used to become Inactive — a typo silently retiring a question."""
    d = _result(client, [_row(status="Actve")])
    assert d["created"] == 0
    assert any("Active_Status" in e for e in d["errors"]), d["errors"]


def test_blank_status_still_means_active(client, db):
    d = _result(client, [_row(status="")])
    assert d["created"] == 1
    q = db.query(AssessmentQuestion).first()
    assert q.status == "Active"


def test_inactive_is_still_accepted(client, db):
    d = _result(client, [_row(status="Inactive")])
    assert d["created"] == 1
    assert db.query(AssessmentQuestion).first().status == "Inactive"


# ── question type ─────────────────────────────────────────────────────────────

def test_a_typo_in_question_type_is_refused_not_recategorised(client, db):
    d = _result(client, [_row(qtype="Conceptial")])
    assert d["created"] == 0
    assert any("Question_Type" in e for e in d["errors"]), d["errors"]


def test_blank_question_type_defaults_quietly(client, db):
    """Absent is not the same as wrong — a blank cell is a default, not a typo."""
    d = _result(client, [_row(qtype="")])
    assert d["created"] == 1
    assert db.query(AssessmentQuestion).first().question_type == "Conceptual"


# ── question id prefix ────────────────────────────────────────────────────────

def test_an_id_whose_prefix_contradicts_the_specialty_is_refused(client, db):
    """
    SURG-999 uploaded under ICD10CM used to be created as an ICD10CM question
    wearing a Surgery prefix. The old check only fired when the ID already
    existed elsewhere.
    """
    d = _result(client, [_row(qid="SURG-999")])
    assert d["created"] == 0
    assert any("prefix" in e.lower() for e in d["errors"]), d["errors"]


def test_the_right_prefix_is_accepted(client, db):
    d = _result(client, [_row(qid="ICDX-500")])
    assert d["created"] == 1
    assert db.query(AssessmentQuestion).first().question_id == "ICDX-500"


# ── reporting ─────────────────────────────────────────────────────────────────

def test_errors_name_their_row_so_a_big_sheet_can_be_fixed(client, db):
    d = _result(client, [_row(), _row(a="Dup", b="Dup"), _row(status="Actve")])
    assert d["created"] == 1
    assert len(d["errors"]) == 2
    assert all(e.startswith("Row ") for e in d["errors"]), d["errors"]


# ── dry run ───────────────────────────────────────────────────────────────────

def _dry(client, rows, specialty="ICD10CM"):
    buf = io.BytesIO()
    _book(rows).save(buf)
    r = client.post(
        "/assessment/questions/upload",
        data={"specialty": specialty, "uploaded_by": "trainer", "dry_run": "true"},
        files={"file": ("q.xlsx", buf.getvalue(), MIME)},
    )
    assert r.status_code == 200, r.text
    return r.json()


def test_a_dry_run_writes_nothing(client, db):
    d = _dry(client, [_row(text="Q1?"), _row(text="Q2?")])
    assert d["dry_run"] is True
    assert d["created"] == 2, "it must still report what WOULD happen"
    assert db.query(AssessmentQuestion).count() == 0, "nothing may be persisted"


def test_a_dry_run_counts_the_overwrites_it_would_cause(client, db):
    """The whole point: know how many existing questions a sheet will replace."""
    _result(client, [_row(text="Original?")])
    qid = db.query(AssessmentQuestion).first().question_id

    d = _dry(client, [_row(qid=qid, text="Rewritten?")])
    assert d["updated"] == 1
    assert d["updated_ids"] == [qid]
    assert db.query(AssessmentQuestion).first().question_text == "Original?"


def test_a_dry_run_reports_the_same_errors_as_the_real_thing(client, db):
    rows = [_row(), _row(a="Dup", b="Dup"), _row(status="Actve")]
    preview = _dry(client, rows)
    real = _result(client, rows)
    assert preview["errors"] == real["errors"]
    assert preview["created"] == real["created"]


def test_a_dry_run_leaves_no_audit_trail(client, db):
    from models import AssessmentAuditLog
    before = db.query(AssessmentAuditLog).count()
    _dry(client, [_row()])
    assert db.query(AssessmentAuditLog).count() == before


def test_a_real_upload_still_writes(client, db):
    d = _result(client, [_row()])
    assert d["dry_run"] is False
    assert db.query(AssessmentQuestion).count() == 1


# ── questions with fewer than four options ────────────────────────────────────

def test_a_true_false_question_is_accepted(client, db):
    """
    Not every question has four choices. Requiring all four refused True/False
    outright — a regression the blank-option rule introduced.
    """
    d = _result(client, [_row(a="True", b="False", c="", d="")])
    assert d["created"] == 1, d["errors"]


def test_a_three_option_question_is_accepted(client, db):
    d = _result(client, [_row(a="One", b="Two", c="Three", d="")])
    assert d["created"] == 1, d["errors"]


def test_a_single_option_is_still_refused(client, db):
    d = _result(client, [_row(a="Only one", b="", c="", d="")])
    assert d["created"] == 0
    assert any("at least two" in e.lower() for e in d["errors"]), d["errors"]


def test_a_gap_in_the_middle_is_refused(client, db):
    """
    Options are positional. A hole silently shifts what the coder sees, so a
    blank B with a filled C is a mistake rather than a shorter question.
    """
    d = _result(client, [_row(a="One", b="Two", c="", d="Four")])
    assert d["created"] == 0
    assert any("no gaps" in e.lower() for e in d["errors"]), d["errors"]


def test_a_lone_first_option_reports_the_count_not_the_gap(client, db):
    """One option is too few whatever the shape — say that, not "gap"."""
    d = _result(client, [_row(a="One", b="", c="Three", d="")])
    assert d["created"] == 0
    assert any("at least two" in e.lower() for e in d["errors"]), d["errors"]


def test_an_answer_pointing_past_the_last_option_is_refused(client, db):
    """Keying C on a True/False question marks every coder wrong."""
    d = _result(client, [_row(a="True", b="False", c="", d="", correct="C")])
    assert d["created"] == 0
    assert any("does not have" in e for e in d["errors"]), d["errors"]


def test_duplicates_are_still_refused_in_a_short_question(client, db):
    d = _result(client, [_row(a="True", b="true", c="", d="")])
    assert d["created"] == 0
    assert any("duplicate" in e.lower() for e in d["errors"]), d["errors"]
