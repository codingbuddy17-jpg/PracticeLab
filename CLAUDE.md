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
`database.py`.** A new table does not. This took `/auditor/batches` down with
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

Descriptions are wired into the **entry** screens only — coder PDx/SDx/PCS and
the auditor's claim, revise and add rows — plus the trainer freshness note.
Analytics, results screens and the PDF exports show codes without them.

---

## Conventions that keep biting

**Rates must ship their denominator.** A percentage whose base is unclear has
already caused one wrong-units bug. Label whether a figure averages or pools:
audit accuracy *averages* chart scores, component accuracy *pools* findings.

**`NA` is a real value and is not zero.** Nothing of that kind existed. Render
it as `NA`, never `0%`.

**Count in SQL, not Python.** Loading rows to `len()` them is fine at a dozen
and fatal at a thousand. Every list endpoint pages, and counts come from the
whole filtered set rather than the loaded page — counting loaded rows told a
trainer there were no closed batches whenever they fell past page one.

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
coders go wrong; it follows from the time.

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
numbers steer the draw.

**`Quotas.manual = None` ≠ `0`.** `None` means "no opinion, so a chart with an
authored version uses it"; `0` means "pass authored versions over". Conflating
them silently discarded every trainer-authored error set in Automatic mode.

**Version rotation keys on the chart's own use count** — not the cycle number,
not the auditor. Keying on the auditor gives four auditors three different
versions in one sitting; keying on the cycle pins a chart to one version
forever when it does not appear every cycle.

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
it is called done.

---

## Git

Another agent works in this repository. **Stage named paths**, never
`git add -A`.

The repo is **public**: no credentials, no deploy-hook URLs, no database dumps.
`.gitignore` blocks `*.tar.gz`, `*.dump`, `*.sql.gz` and `*.bak` for that
reason; overriding needs a deliberate `git add -f`.

A push to `main` deploys to production automatically.
