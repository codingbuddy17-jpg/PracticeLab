# CR-012-Nov — Code lists stored per specialty; PDx POA and the exempt rule in the review

**Month: November 2026**

| | |
|---|---|
| **Commit** | `38d8a64` |
| **Kind** | C (backend and frontend). No schema change |
| **Module** | Practice submit and Re-grade; review (trainer, coder, Excel); auditor observed plantings; Specificity Drops analytics |
| **Score impact** | None. Scores were always right; only the stored copies of the lists were wrong |
| **Found by** | The user, after CR-011-Nov: a missed CC secondary diagnosis, and POA-exempt codes, absent from the review |

## Root cause

The coding screen built a blank E/M form for **every** chart and sent it on save and submit. The result writer (`_upsert_practice_result`) decided "is this E/M?" by whether that form was present. So every IP-DRG, SDS, ED Facility, Surgery, Ancillary and ED Single Path result was treated as E/M at storage time. Its SDx and CPT lists were saved **empty**, on both the key and the coder side, copied from the blank form. The grader received the real codes, so scores were unaffected.

This happened from late August 2026 until this CR. Re-grade repeated it, because it rebuilds from the saved draft, which holds the same blank form. The existing per-specialty tests submitted without the form, so they never saw it.

Before CR-011-Nov, the "Scoring notes" block listed missed codes from the grader's own findings, which hid the gap. CR-011 removed that block.

## Effects, by measurement

| Area | Effect before this CR |
|---|---|
| Review, coder results, Excel review export | SDx section absent (all six specialties); CPT section absent (all except IP and Ancillary) |
| Auditor observed plantings (`audit_observations`) | Invented errors: "coder missed CPT 11042" when the coder had coded it; the coder's extra diagnoses dropped |
| Specificity Drops analytics | Secondary diagnosis drops missing for affected results |
| Scores, pass/fail, DPO, error analysis, batch results | Unaffected: these read the grader's findings |

E/M, ED Profee, Edits and Denials were unaffected. The coding forms and graders were already wired correctly for every specialty; the full sweep is in the session record.

## Rules

1. **E/M is a property of the specialty** (`E/M`, `ED Profee`), never of the payload. Submit, Re-grade and result storage all decide by specialty.
2. **The coding screen creates the E/M form only for E/M and ED Profee charts.** Drafts saved earlier with a blank form do not reload it.
3. **Repair on read.** When a stored SDx, PCS or CPT list is empty, read it from the fallback:
   - the coder's side from `practice_chart_drafts` (submit writes the draft before grading);
   - the key's side from `answer_keys`.

   A non-empty stored list always wins. An empty one is replaced only when the fallback has codes, so a chart that genuinely had none still reads as none. This applies to the review, the observed plantings and Specificity Drops (`services/practice_result_lists.pick`). No data migration is needed.
4. **Principal diagnosis POA** is shown on both sides (`J18.9  POA Y`), from the draft and the key. A mismatch reads `different` with a note `POA: key Y, coded N`.
5. **POA exempt.** A row whose key POA is `E` is never marked as differing, and carries the note *POA exempt (CMS) — not graded*. This applies to PDx and SDx and matches `services/poa_exempt.py`.

## Verified

- `tests/test_specialty_flow.py`, 17 tests. Each code-graded specialty is submitted with the payload the screen really sent. The tests check the stored lists, the review's missed and extra rows (with the CC badge on IP), repair of a result stored empty, observed plantings, PDx POA and the exempt rule. All 17 fail on the code before this CR.
- Full suite (2,884), API contract check, specialty sync, frontend build and boot check all pass.

## IT action

- **Same Python backend:** `git am code.patch` and deploy. Past results are repaired on read, so nothing needs re-grading.
- **Rebuilt backend:** implement rules 1 and 3–5 first, then `git apply frontend.patch`. Rule 2 alone would stop new damage but repair nothing.
