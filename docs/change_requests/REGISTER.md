# Change request register

Changes made in the original application after the migration, for the IT team
to carry into their deployment. **Every CR works for either kind of
deployment:**

| If your deployment… | For each CR, in number order |
|---|---|
| **runs this same Python backend** | `git am docs/change_requests/CR-NNN/code.patch`, run the checks, deploy. `code.patch` is the complete committed change (backend, frontend, scripts, tests); schema columns are added automatically on startup. Applied in order to the pre-CR-001 code, all patches reproduce the original app exactly. |
| **rebuilt the backend** (e.g. .NET) and kept this React frontend | implement the rules in `CR-NNN.md`, run any DDL it lists, then `git apply frontend.patch`. For a Kind C change, the backend comes first: the shared frontend calls the new behaviour. |

Each CR folder holds `CR-NNN.md` (what changed, why, the exact rules, acceptance
tests, and a section for the same-backend route), `code.patch`,
`frontend.patch`, and `openapi.diff.txt`. Verify a deployment with
`python3 scripts/smoke_deployed.py --base <your API> [--session <id>]`.

`docs/PracticeLab_Change_Register.xlsx` is the detailed index: one row per CR
(with the same-backend action and IT's status columns), one row per file-level
change, and a backlog of what is proposed but not built.

Kinds: **A** frontend only · **B** backend only · **C** both · **D** schema · **Docs** documentation.

<!-- register:start -->
| CR | Title | Kind | Score impact | Schema | Commits | Apply order |
|---|---|---|---|---|---|---|
| [001](CR-001/CR-001.md) | Practice review shows right as well as wrong; E/M review classified; Excel export | C | No | None | `db51300, f6198ef` | Backend first, then frontend patch |
| [002](CR-002/CR-002.md) | E/M primary diagnosis becomes a scoring factor; diagnosis dots ignored | B | Yes | None | `bccf4ff` | After CR-001 |
| [003](CR-003/CR-003.md) | Code descriptions on review, DRG, key-check, auditor-review and analytics screens | C | No | None | `08e8b3a` | After CR-001; backend first, then frontend patch |
| [004](CR-004/CR-004.md) | Chart viewer reads charts as documents and sections, like an EHR | A | No | None | `3846e06` | Any time: frontend patch only |
| [005](CR-005/CR-005.md) | CMS POA exempt list applied everywhere POA is keyed, coded, audited or graded | C+D | Yes | code_descriptions.poa_exempt BOOLEAN | `6e32710, 2847e8b` | DDL, backend rules, run loader, then frontend patch |
| [006](CR-006/CR-006.md) | Report button on each Auditor batch row | A | No | None | `9c443bc` | Any time: frontend patch only |
| [007](CR-007/CR-007.md) | A same-family code is a wrong code, not a miss | C | No | None | `78256e8` | Backend first, then frontend patch |
| [008](CR-008/CR-008.md) | Runbook and container guide updated for the POA exempt list (documentation) | Docs | No | None | `30daf10` | Read with CR-005 |

Built 19 November 2026 by `docs/_change_register_build.py`, which also writes `docs/PracticeLab_Change_Register.xlsx` — the detailed version, with one row per file-level change and the columns IT uses to track progress.

**Backlog: proposed, not built**

| Item | Title | Status |
|---|---|---|
| B-001 | Auditor results review after submission | Logged at the user's request; design to be proposed before building. |
| B-002 | Text for scanned / image-only charts (OCR) | Deferred: the user reports scanned charts are rare. |
<!-- register:end -->
