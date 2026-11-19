# CR-010-Nov — E/M review shows the diagnoses behind its Dx score

**Month: November 2026**

| | |
|---|---|
| **Commit** | `cb8667b` |
| **Kind** | B (backend only). No schema change, no frontend change |
| **Module** | PracticeLab E/M and ED Profee review (trainer Review, coder results, Excel export), and Re-grade |
| **Score impact** | None |
| **Found on** | Live batch "Test with E/M" (23), session 28, chart **EM007**: Dx **23.3 of 35** over an **empty** diagnosis section, with a note claiming "full credit" |

## Why

The review builds the E/M Diagnoses and CPT rows from code lists stored on each result (`practice_results.sdx_answer_key / sdx_submitted / cpt_answer_key / cpt_submitted`). Two kinds of E/M result have those lists **empty** beside a real score:

1. **Results submitted before the lists were stored** (session 28 was submitted on 2026-08-20).
2. **Results re-graded**: the E/M Re-grade path never stored the key's lists (`em_dx_ak`, `em_cpt_ak`), while submit did.

With the lists empty, the section had no rows, and the "no key diagnoses → full credit" note appeared next to a partial score.

## Rules

1. **Review fallback (E/M and ED Profee):** if the stored key list is empty, read the key's codes from `em_answer_keys` (`dx_codes`, `procedure_cpts`). If the stored coder list is empty, read the coder's codes from the saved form (`practice_chart_drafts.em_data` → `em_dx`, `em_cpt`). The stored lists still win when present.
2. **"Full credit" is said only when the score agrees.** Otherwise, with no key codes readable, the note is "The diagnoses behind this score could not be read for this result."
3. **Re-grade stores the lists** exactly as submit does (`em_dx_ak` = key diagnoses as `[{code}]`, `em_cpt_ak` = normalised key CPT lines).

## Verified

- Tests: an E/M result with its lists blanked shows Primary Dx E11.9 *correct* and Secondary I10 *missed*, and never says "full credit"; Re-grade stores `[{"code":"E11.9"},{"code":"I10"}]`. Removing the fallback makes the first test fail.
- Live data: EM007's key holds K21.9, F32.A, G47.00. Those rows now appear against the coder's codes.

## IT action

Same Python backend: `git am code.patch`. Rebuilt backend: implement rules 1–3 where you build the review and the E/M re-grade. Nothing to apply on the frontend.
