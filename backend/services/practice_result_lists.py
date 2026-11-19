"""
The code lists a practice result stored, repaired where they were stored empty.

From late August to CR-012-Nov the coding screen sent a blank E/M form with
every chart, and the result writer took that as "this is an E/M chart": every
graded IP, OP and ED Single Path result stored its SDx and CPT lists EMPTY, on
both the key side and the coder side. Scores were right (the grader saw the
real codes); only the stored copy was lost.

The truth survives elsewhere: the coder's codes in practice_chart_drafts (the
submit writes the draft before grading), the key in answer_keys. Every reader
of the stored lists goes through here, so the review, the auditor's observed
plantings and Specificity Drops all see the same repaired lists.

A stored list that is non-empty always wins. An empty one is replaced only
when the fallback has something, so a chart that genuinely had no secondary
diagnoses still reads as none.
"""
import json
from typing import Any, List


def as_list(v: Any) -> List:
    if v is None or v == "":
        return []
    if isinstance(v, str):
        try:
            v = json.loads(v)
        except ValueError:
            return []
    return v if isinstance(v, list) else []


def pick(stored: Any, fallback: Any) -> List:
    """The stored list, or the fallback when the stored one is empty."""
    s = as_list(stored)
    return s if s else as_list(fallback)
