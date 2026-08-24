# PracticeLab — working notes

A medical coding training platform. Trainers upload charts and answer keys;
coders practise against them and are graded; auditors review pre-coded charts
carrying deliberately introduced errors.

Four modules: **Chart Library**, **PracticeLab** (coder), **Assessment** (MCQ),
**Auditor**. See `docs/DATABASE_MIGRATION_RUNBOOK.md` and
`docs/DATA_STORAGE_MODEL.md` for the data side.

---

## Stack, and what not to add

| | |
|---|---|
| Frontend | React 18 · TypeScript · Vite |
| — libraries | `lucide-react` icons · `recharts` charts · `axios` · `react-router-dom` · `react-hot-toast` · `@tiptap` rich text |
| Backend | FastAPI · Python 3.11 (prod, `backend/runtime.txt`) · SQLAlchemy 2.0, **sync** |
| Database | PostgreSQL (Render). Tests and local dev use SQLite |
| Storage | S3-compatible (Cloudflare R2) for chart page images |
| Hosting | Render, `render.yaml`. **Auto-deploy is ON** — a push to `main` deploys |

**Do not introduce new dependencies, frameworks or patterns** without asking.
This codebase is being migrated to an internal environment by a team that did
not write it, and every added tool is something they must adopt. That includes
CSS libraries, state managers, ORMs and test frameworks.

The libraries above are already sanctioned — use them rather than hand-rolling.
Charts are `recharts`; there is no second charting approach.

**Styling is inline `style={{}}` objects only.** No CSS modules, no Tailwind,
no styled-components. Shared style objects live in a `styles.ts` per feature
folder; a new screen should spread an existing one rather than start over
(`const s = { ...pl, ...mine }`).

Local Python is 3.9 (`.venv/`), production is 3.11 — so the local environment
is the *stricter* one. Keep backend code 3.9-compatible (no `match`, no `X | Y`
in runtime positions); 3.10+ syntax would run on Render but breaks the local
test suite, which is where it gets caught.

---

## The four checks

Run all four before pushing anything non-trivial. The suite alone is not enough
— see the migration trap below for a bug that passed 2000+ tests and still took
production down.

**CI runs all of this on every push** (`.github/workflows/checks.yml`), so a
push no longer depends on anyone remembering. Two things live there that you
cannot get locally without a PostgreSQL: `scripts/check_pg_parity.py` on every
push, and the full suite against PostgreSQL nightly.

```bash
cd backend && PYTHONPATH="$PWD:$PWD/tests" ../.venv/bin/python -m pytest tests -q -p no:warnings
```

```bash
.venv/bin/python scripts/check_api_contracts.py
```

```bash
.venv/bin/python scripts/check_specialty_sync.py
```

```bash
cd frontend && npm run build
```

`check_api_contracts.py` asserts every path the frontend calls resolves to a
real backend route. It scans source statically, so a path built by
interpolation (`` `/x${q}` ``) is invisible to it — append query strings
**after** the template literal.

`check_specialty_sync.py` asserts the frontend specialty lists match the
backend `Specialty` enum. They are duplicated with no shared source of truth,
so adding an enum member silently leaves dropdowns stale.

**Two more, for the two things none of the above can see.**

`scripts/check_pg_parity.py` builds the schema on a real PostgreSQL and
inspects it. SQLite is more permissive in ways that have taken production down,
and those are properties of the built schema, so this finds them in seconds
without running a test. Ids with no default FAIL; prose in a bounded VARCHAR
warns.

`scripts/smoke_deployed.py --base https://chart-viewer-api-rxrd.onrender.com`
exercises the DEPLOYED app. Everything else checks local code, and the gap
between "the code is correct" and "the running service works" is where this
project has actually been hurt. **Use `--write`**: this codebase degrades to
silence, so reads pass against a database that cannot be written to — which is
exactly how a total E/M outage looked healthy from outside. A run that asks
for `--write` and cannot perform one now FAILS rather than skipping: the script
once asked for `/charts` (not a route), read the 404 as an empty environment,
skipped the write and printed PASS while nine E/M charts sat there. It is
stdlib-only, so `python3` runs it without the project's dependencies.

The API's host is `chart-viewer-api-rxrd.onrender.com`. The obvious name
without the suffix does not serve. The UI **is** at the obvious
`chart-viewer-ui.onrender.com`, so `CORS_ORIGINS` in `render.yaml` is correct —
only the API service name there lacks the `-rxrd` suffix Render assigned it.

**Boot check** — the only one that catches a total outage, and the one the test
suite cannot give you, because tests never start the app:

```bash
cd backend && DATABASE_URL=sqlite:////tmp/boot.db STORAGE_ENDPOINT_URL=x STORAGE_ACCESS_KEY=x STORAGE_SECRET_KEY=x STORAGE_BUCKET_NAME=x STORAGE_PUBLIC_URL=x MASTER_ADMIN_PASSPHRASE=x ../.venv/bin/python -c "import uvicorn,threading,time,urllib.request; from main import app; r=[x for x in app.routes if hasattr(x,'methods')]; s=uvicorn.Server(uvicorn.Config(app,host='127.0.0.1',port=8899,log_level='error')); threading.Thread(target=s.run,daemon=True).start(); [time.sleep(0.25) for _ in range(20) if not s.started]; print(urllib.request.urlopen('http://127.0.0.1:8899/openapi.json',timeout=5).status,len(r)); s.should_exit=True"
```

---

## Schema: there is no Alembic

`init_db()` runs on **every** boot:

```python
Base.metadata.create_all(bind=engine)   # ORM-defined tables
_run_migrations()                        # 21 raw CREATE TABLE + 92 ALTERs
report_schema_drift()                    # logs columns the models expect and the DB lacks
```

**`create_all()` creates missing TABLES. It never alters an existing one.**

This is the single most expensive trap in the codebase. Adding a column to an
existing model is invisible to `create_all()`, so:

- every test passes, because the test database is rebuilt from the models each run
- production breaks, because its table is old and has no such column

**A new column on an existing table needs an `_add_col()` call in
`database.py`.** A new table does not.

**A new raw-DDL table needs `_PK`, not `id INTEGER PRIMARY KEY`.** That exact
phrase is SQLite's auto-assigning rowid alias; in PostgreSQL it is a plain
integer with no default, so every insert omitting `id` raises
`NotNullViolation`. It bites only tables with **no ORM model** — for the others
`create_all()` builds them properly and the raw statement is a no-op behind
`IF NOT EXISTS`. It took the whole E/M module down: no answer key, grading
result or scoring config could be written, with 2,510 tests green.

**Migrations fail silently on PostgreSQL and pass on SQLite.** Four had never
run in production. Write dialect-portable SQL: `TRUE`/`FALSE` not `1`/`0` for
booleans, and `CAST(x AS TEXT)` rather than `::text`, which SQLite rejects. This took `/auditor/batches` down with
2074 tests green.

Migrations are additive and non-fatal — a failure logs and startup continues.
After any schema change, check deploy logs for `Migration DDL failed`.

**Counting tables:** `Base.metadata` reports 35, and that is wrong. Six tables
(`em_*`, `practice_*`) exist only in raw DDL and are invisible to the ORM. The
real schema is **46 tables / 645 columns**. Count by building it —
`init_db()` against a throwaway SQLite file, then `inspect(engine)`.

---

## Layout

```
backend/
  main.py  config.py  database.py  schemas.py
  models/     charts · practicelab · assessment · auditor
  routers/    *_pkg/ packages, one module per concern
  services/   grading, allocation, scoring, exports, mutation
  tests/
frontend/src/
  api/        one module per backend area
  pages/      practicelab/ · assessment/ · auditor/ · top-level screens
  components/ hooks/ types/ theme.ts
scripts/      the two contract checkers, and the CMS code-set ingest
docs/         IT handover documents
```

Shared logic belongs in `services/`. `draw_for_person` in
`services/allocation.py` is drawn on by both the coder and auditor allocators —
prefer extending a shared function over copying it.

---

## Reference code sets are loaded by hand

`scripts/ingest_code_sets.py --write` loads ICD-10-CM, ICD-10-PCS, HCPCS
Level II and the MS-DRG CC/MCC list — about 186,000 rows. **Nothing calls it**,
deliberately: it downloads several megabytes, and hanging that off `init_db()`
would make every deploy slow and a CMS outage a failed startup.

Everything that reads it degrades to silence rather than erroring, so an
environment where it was never run looks like one where the features do not
exist. `GET /codes/status` says what is loaded. `--from-dir` reads files from
disk for environments with no route to cms.gov.

One consequence is not cosmetic: the auditor's PCS mutation draws its
replacement from the real tables. Without them, two-thirds of planted PCS
errors are strings that are not codes — which changes what auditors are scored
on, not just what they see.

Two CMS files are easy to take from the wrong place:

- **PCS descriptions come from the CODES file, not the tables file.** The
  tables say which codes exist, axis by axis; joining those seven titles gives
  a character-by-character breakdown rather than a procedure. Both are loaded —
  the axis titles are what name *which character* a planted error changed.
- **HCPCS descriptions wrap across several records** for one code, numbered in
  a sequence field. One record per code truncates them. The same file is the
  only source in the app that explains a **modifier**.

**CPT is absent and stays absent.** AMA copyright, licensed per user, and this
repository is public. CPT lines render bare and the answer-key checks decline
to judge five-digit numeric codes rather than pretend to have checked them.

Descriptions are wired into the screens where codes are **typed**: coder
PDx/SDx/PCS, the auditor's claim/revise/add rows, and both trainer key editors
(`AnswerKeyEditor`, `EMAnswerKeysView`) — plus the trainer freshness note.
`auditor/AuditKeys.tsx` is not wired yet. Analytics, results screens and the
PDF exports show codes without them.

On a coder screen a description is a study aid; on a **key** screen it is a
check, and a wrong key is worse than a wrong answer because it silently grades
everyone against it. Key screens come first when extending this, not last.

---

## Conventions that keep biting

**The master passphrase never goes in a URL.** It is the single shared
credential gating retire, delete, force-close and the question bank, and it is
currently passed as a query parameter in 13 places — query strings are written
to server, proxy and CDN logs, and `downloadAnswerKeyExport` puts it in a
`window.open` URL, which reaches browser history. Send it in a header or a body.

**Rates must ship their denominator.** A percentage whose base is unclear has
already caused one wrong-units bug. Label whether a figure averages or pools:
audit accuracy *averages* chart scores, component accuracy *pools* findings.

**`NA` is a real value and is not zero.** Nothing of that kind existed. Render
it as `NA`, never `0%`.

**Count in SQL, not Python.** Loading rows to `len()` them is fine at a dozen
and fatal at a thousand. Every list endpoint pages, and counts come from the
whole filtered set rather than the loaded page — counting loaded rows told a
trainer there were no closed batches whenever they fell past page one.

**No React hook below an early return.** `if (loading) return …` before a
`useMemo` means the first render runs fewer hooks than the next, which is React
error #310 and replaces the whole component with an error boundary. It cost two
live screens at once — the IP/OP answer key editor and the assessment Question
Signals tab, the latter taking two sibling tabs down with it. Neither the type
checker nor 2,600 tests noticed; only opening the screen did.
`tests/test_no_conditional_hooks.py` reads the source and fails on any of them.

**A recharts bar that never finishes its entry animation is never painted.**
Under v3 the geometry is computed and the bars simply do not appear: no error,
no warning, an empty plot with correct axes and a correct legend, which reads
as "everyone scored zero" rather than as a bug. It cost the auditor's Clean vs
Opportunity chart. `isAnimationActive={false}` is the fix. Nothing in the four
checks can see this — the build passes, the tests pass, the data is right — so
it is found only by looking at the chart. It was isolated by elimination
(hardcode the data, add a fill, remove the Cells, disable the animation), which
is the only way it will be found again.

**A session's life is the batch's life, and only the WRITE ends.** Practice
and audit tokens have no expiry column and never have, so the credential is
permanent. A clock is the obvious fix and the wrong one: tokens are handed out
days before the work, a batch runs for days rather than a sitting, and any
duration either fires mid-batch or is long enough to protect nothing. Closing
is already a deliberate trainer action meaning the work is done, so
`assert_batch_open` is the expiry. It gates submitting; reading a session and
its own feedback stays open afterwards, because a coder who cannot see how they
did has lost the point of the exercise and nothing is protected by hiding it
from them. The auditor module had this from the start; PracticeLab's four
checks were all trainer-side and the coder's own submit was ungated until
2026-08-24.

**A guard must be per FIELD, not per file.** "Does this file mention
`CodeSuggest`" passes as soon as one branch has it — which is how the E/M
diagnosis rows and both key editors were reported as wired while rendering
plain inputs. Anchor a test on the value being described, then delete it and
watch the test fail. Same for screens: enumerate them, do not summarise.

**This is a desktop application.** The user confirmed on 2026-08-21 that it is
never used on a phone or tablet, so responsive layout is not a defect class
here — do not spend effort on breakpoints, and do not raise findings against
them.

**Copy earns its place or goes.** The batch screen carried five notices, most
narrating the next screen or the mode the trainer had just chosen. Keep what a
user cannot see for themselves; cut walkthroughs of screens that explain
themselves, and never name the internal engine doing the work.

**Check for siblings before calling a UI bug fixed.** These three classes have
each recurred more than once: unpaginated lists that die at scale, counts
computed over the current page instead of the query, and copy that describes
behaviour the code stopped having.

**Verify by measuring, not by reading.** Several real bugs here — unreachable
mutation branches, two successive version-selection faults, a quota that ate a
whole allocation — were found by running a probe and printing the distribution,
and were invisible to both inspection and the test suite.

---

## Domain rules that the code does not explain

**Specialties are not interchangeable.** Each grades different elements. `E/M`
is the outlier — graded on the 2023 AMA medical-decision-making table rather
than code matching, with its own tables and scoring path. `POA` (present on
admission) is mandatory on inpatient diagnoses and meaningless elsewhere.
**DRG-impacting is inpatient-only**; revenue-impacting is the wider notion and
covers principal diagnosis, CC/MCC secondaries, PCS, CPT, modifier and units.

**Never hardcode a specialty's form.** Sections and fields are served by the
API from `routers/auditor_pkg/shared.py`. A screen that assumes IP-DRG shape
breaks the other nine.

**E/M levels move along a ladder.** New-patient office, established office and
ED are three separate ladders; critical care (99291/99292) sits outside them
all. A level error is a near miss along one ladder — 99213 for 99214 — or the
same level on the wrong ladder, which is the new-versus-established mistake.
`services/em_levels.py` holds the ladders and the classifier; both modules
import it rather than restating the rules.

**The direction of a level error is the finding.** Upcoding is what payers
audit for and what coders are trained to avoid; downcoding is revenue quietly
left on the table with nobody watching. Same error count, opposite problems.

**99285 vs 99291 is the hardest question in the ED** — whether the condition
qualifies as critical care at all — and it is the one planting the generator
may not invent. An answer key says which code is right, not whether the call
was close, so it is planted only where a trainer has set
`AnswerKey.cc_boundary = "borderline"`. The 99292 unit count is NOT where
coders go wrong; it follows from the time, and critical-care **time** is not
planted at all — an auditor validates the code, not the arithmetic.

**Anything asking "does this chart have a key" must know about
`em_answer_keys`.** It has no ORM model and no row in `answer_keys`, so a join
against `AnswerKey` reports zero for every E/M chart — which told a trainer who
had just entered five keys that nothing could be graded. `EM_KEY_SPECIALTIES`
and `chart_ids_with_keys()` live in `services/em_audit_key.py`, because the
coder side and the auditor side both need them and neither should import the
other.

**E/M and ED Profee are auditable, and their key is a different table.**
`em_answer_keys`, adapted by `services/em_audit_key.py` into the ordinary key
shape. Never ask a trainer for an ordinary key as well: one chart with two
truths disagrees the first time either is edited, silently, with the coder
graded against one and the auditor against the other.

**E/M is not uniform, so its form is resolved per CHART.** A preventive visit,
a consult, or a visit levelled by time is not graded on medical decision making
at all, and `applicable_weights` drops the MDM weights for them. The auditor
form, its completion check, its submit gate and the trainer key screen all use
`sections_for_chart()`. Keying on category is safe — it is a property of the
encounter, already plain from the code on the claim — but never key on whether
something was planted. A chart with **no key** keeps the full form: absence is
not evidence it is preventive.

**MDM is audited as three levels, never as the 26 element ticks.** COPA, Data
Review and Risk — single-valued, Revise-only, picked from a list served by
`form_spec`. The ticks are what the coaching module grades; an auditor
disagrees with a judgement.

**MDM is an ordinary planted finding, not a slice of the score.** A fixed
weight has to be paid whether or not the chart has anything to pay it with, and
a separately scored *detection* component would pay for flagging — which the
module refuses everywhere else. MDM reports its own percentage in
`review_attributes` beside POA and Modifier, outside the code-line denominator,
split COPA/Data/Risk. If E/M volume ever demands more, add a distinct **E/M
Reasoning Score** beside the Audit Score; do not carve one out of it.

**Planting reads the declared E/M category, never infers it.** `em_levels.py`
knows three ladders plus critical care; preventive, consults and the rest are
off-ladder, so planting abstains — which fails safe per chart but makes
**category predict cleanliness across a batch**. An auditor who learns
"preventive means clean" stops reading them, and the render-identically rule
does not catch it.

### The Auditor module

**Charts must render identically whether or not they carry errors.** A clean
chart drawn differently — an empty section, a collapsed panel, a different
tint — tells the auditor the answer before they look, and destroys the
restraint measurement the module exists for. Colour by *category* is fine
because it is fixed per section; colour by *content* is not.

**Clean vs opportunity is trainer vocabulary.** The auditor's own screens and
results never name it.

**"Found" means found AND corrected.** Flagging alone earns nothing — an
auditor who marks every line wrong knows nothing. `detected_not_corrected` is
reported separately and never scored: "found 4, corrected 2" and "found 2 of 4"
both come to 50% and are different coaching conversations.

**Hand-picked allocation takes only the clean count.** The authored/generated
split follows the charts the trainer picks, because a quota of three authored
cannot be met if one picked chart has a version. Guided is the mode where
numbers steer the draw. Hand-picked is also the only mode that may **pin a
specific key version per chart** (`manual_set_ids`); the other modes refuse it,
since a trainer who did not choose the charts cannot be choosing their
versions.

**`Quotas.manual = None` ≠ `0`.** `None` means "no opinion, so a chart with an
authored version uses it"; `0` means "pass authored versions over". Conflating
them silently discarded every trainer-authored error set in Automatic mode.

**Version rotation keys on the chart's own use count** — not the cycle number,
not the auditor. Keying on the auditor gives four auditors three different
versions in one sitting; keying on the cycle pins a chart to one version
forever when it does not appear every cycle.

**Reasoning errors report where they sat and whether they mattered.**
`by_mdm_field` splits COPA / Data Review / Risk; `by_mdm_level_impact` splits
"Moved E/M level" from "Reasoning only". Keep the second — the 2-of-3 rule
means one shifted element usually moves nothing, and without the split every
reasoning error reads as equally costly.

**Analytics says "Score", not "Accuracy"** — Audit Score, Clean Chart Score,
PCS Score, Query Score. IP leads with PCS Score rather than DRG accuracy.

---

## Tests: three traps specific to this suite

**Seeded randomness makes tests pass by luck.** The allocator seeds on
`batch_id:cycle:auditor`, and `batch_id` shifts whenever earlier tests create
more batches. A test asserting an exact split can pass for months and fail the
day someone adds a test above it. Assert the invariant that holds for every
draw, or construct the case so the split is forced. Two tests here have already
been rewritten for this.

**The test database is rebuilt from the models each run**, so it always has
columns production lacks — see the `create_all()` trap above. It is also
SQLite, not PostgreSQL: `NOW()` in raw DDL silently fails there, which once
left four assessment tables not existing at all under test.

**SQLite is more permissive than production**, so a green suite means less than
it looks. Two faults passed 2258 tests and appeared on the first real load:

- **VARCHAR lengths are not enforced by SQLite.** `String(60)` accepted a
  98-character value locally and was rejected outright by PostgreSQL. Use
  `Text` for anything holding prose that CMS or a user writes; a bigger number
  only moves the day it happens. Widening an existing column needs an
  `ALTER ... TYPE TEXT` in `_run_migrations()` — varchar→text is metadata-only
  in PostgreSQL, so it is cheap even on a populated table.
- **psycopg2 `executemany` is one round trip per row**, which
  `bulk_insert_mappings` issues. Invisible against a local file; against the
  database in Oregon the first load sat sixteen minutes without writing a row.
  Use multi-row `table.insert().values(chunk)`. If a bulk write hangs, look for
  `idle in transaction` + `wait_event = ClientRead` in `pg_stat_activity` —
  that pairing means the server is waiting on the client, so the cost is round
  trips rather than the query.

Any bulk write or new column wants **one real run against PostgreSQL** before
it is called done. `TEST_DATABASE_URL=postgresql://... pytest tests` now does
exactly that — one throwaway schema per test, and migration failures RAISE
rather than being swallowed the way they are on SQLite. Measured at ~90s per
test against a remote database, so point it at a local PostgreSQL; CI runs it
nightly against a service container.

---

## Git

Another agent works in this repository. **Stage named paths**, never
`git add -A`.

The repo is **public**: no credentials, no deploy-hook URLs, no database dumps.
`.gitignore` blocks `*.tar.gz`, `*.dump`, `*.sql.gz` and `*.bak` for that
reason; overriding needs a deliberate `git add -f`.

A push to `main` deploys to production automatically.
