# CR-011-Nov — One review standard for every specialty

**Month: November 2026**

| | |
|---|---|
| **Commit** | `d88e158` |
| **Kind** | C (backend and frontend). No schema change |
| **Module** | Practice review (trainer Review modal, coder results, Excel export), batch Results table, Auditor review |
| **Score impact** | None. Display only; nothing is rescored |
| **Asked for** | The user (2026-11-19) asked for one standard across IP, OP, E/M and ED review screens, covering what is shown, what sits behind a click, and colours, because some information appeared twice |

## Why

Each specialty's review had grown its own shape:
- IP/OP showed the review rows **and** a "Scoring notes" block that repeated the same findings in the grader's words.
- E/M hid that block.
- The coder screen and the trainer modal used different header sizes and three shades of PASS green.
- The auditor review kept its own reds and greens.

The Scoring notes block held four facts the review rows did not:
- a principal-diagnosis POA mismatch
- a CPT diagnosis-pointer mismatch
- a wrong ED Single Path level
- the CC/MCC weight of a key line

So it could not simply be removed. Those facts move onto the rows first.

## The standard

| | Every specialty |
|---|---|
| **Header** | Chart number · score (green at 80% or over, red below) · PASS/FAIL · coder's flag, then each screen's own badges (DRG/query review, No answer key, E/M coding + reasoning sum, Pending score) |
| **Open** | Summary chips (count of correct, plus any non-zero wrong, missed, extra, differ). Every row that is wrong, missed, extra or differs |
| **Behind a click** | Correct rows. Each section ends "Show N correct lines". In the auditor review, "Show N found and corrected" |
| **Removed** | The separate Scoring notes block. It appears only as a fallback when a result's review could not be built |
| **Colours** | One set (`theme.ts → REVIEW_STATUS`): green correct; red wrong or missed; orange extra or over-call; amber differs or found-but-corrected-wrongly; blue order only. Used by the practice review, the batch Results expand and the auditor review |

## Rules (backend, `services/practice_review.py`)

1. **PDx POA:** when the PDx codes match but the grader's feedback has `PDx / Wrong_POA` (detail `POA: Y vs N`), the PDx row is `different` with note `POA: key Y, coded N`. Before this it read Correct beside withheld points.
2. **CPT pointers:** where the key line states pointers and the coder's differ, the row is `different` with note `Dx pointers: key 1, coded 2`. This is the grader's half-credit rule.
3. **ED level:** each grader line with detail `Facility ED level` or `Professional ED level` becomes a row in a new first section `ED Level` (key `ed_level`), with status `wrong`. Only a wrong level is stored, so a correct level is not shown.
4. **CC/MCC:** a review row gains an optional field `weight` (`"CC"` or `"MCC"`) taken from the key line's `ccmcc`. The screen shows it as a badge beside the key code. The Excel export appends it to the Answer key cell.

New response field: `review.sections[].rows[].weight` (optional). The OpenAPI diff cannot see it, because the route returns plain dicts.

## Verified

- Four tests, one per rule. All four fail with the rules removed.
- Full suite, API contract check and frontend build pass.

## IT action

- **Same Python backend:** `git am code.patch` and deploy.
- **Rebuilt backend:** implement rules 1–4 where you build the review first, then `git apply frontend.patch`. The frontend reads `weight` and tolerates its absence, so the order is not critical.
