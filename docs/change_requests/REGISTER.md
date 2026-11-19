# Change request register

Changes made in the original application, for the IT team to carry into the
migrated deployment. That deployment kept this React frontend, restored the
PostgreSQL dump, and **reimplemented the backend in .NET**, so:

| Part of a change | Arrives as | IT does |
|---|---|---|
| Frontend | `frontend.patch` | `git apply` it to the frontend, unchanged |
| Backend | the CR's business rules + API contract | implement in .NET |
| Database | portable DDL in the CR | run it; a new column on an existing table also needs your migration step |
| Proof | `scripts/smoke_deployed.py --base <your API> …` | run it against your deployment |

**Order matters for Kind C.** The frontend is shared, so a frontend patch that
calls new backend behaviour breaks your deployment until that behaviour
exists. Implement the backend half first, then apply the patch.

Each CR folder holds `CR-NNN.md` (the spec), `frontend.patch`,
`openapi.diff.txt` (generated: routes added, removed or changed), and the
originating commit. Python in a CR is reference reading, never something to
port line by line.

Kinds: **A** frontend only · **B** backend only · **C** both · **D** schema.

<!-- register:start -->
| CR | Title | Kind | Score impact | Schema | Commits | Apply order |
|---|---|---|---|---|---|---|
| [001](CR-001/CR-001.md) | Practice review shows right as well as wrong; E/M review classified; Excel export | C | No | None | `db51300, f6198ef` | Backend first, then frontend patch |
| [002](CR-002/CR-002.md) | E/M primary diagnosis becomes a scoring factor; diagnosis dots ignored | B | Yes | None | `bccf4ff` | After CR-001 |
| [003](CR-003/CR-003.md) | Code descriptions on review, DRG, key-check, auditor-review and analytics screens | C | No | None | `08e8b3a` | After CR-001; backend first, then frontend patch |

Built 19 November 2026 by `docs/_change_register_build.py`, which also writes `docs/PracticeLab_Change_Register.xlsx` — the detailed version, with one row per file-level change and the columns IT uses to track progress.

**Backlog: proposed, not built**

| Item | Title | Status |
|---|---|---|
| B-001 | Auditor results review after submission | Logged at the user's request; design to be proposed before building. |
<!-- register:end -->
