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
| Frontend | React 18 · TypeScript · Vite · `lucide-react` icons |
| Backend | FastAPI · Python 3.11 (prod, `backend/runtime.txt`) · SQLAlchemy 2.0, **sync** |
| Database | PostgreSQL (Render). Tests and local dev use SQLite |
| Storage | S3-compatible (Cloudflare R2) for chart page images |
| Hosting | Render, `render.yaml`. **Auto-deploy is ON** — a push to `main` deploys |

**Do not introduce new dependencies, frameworks or patterns** without asking.
This codebase is being migrated to an internal environment by a team that did
not write it, and every added tool is something they must adopt. That includes
CSS libraries, state managers, ORMs and test frameworks.

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
real schema is **41 tables / 596 columns**. Count by building it —
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
scripts/      the two contract checkers
docs/         IT handover documents
```

Shared logic belongs in `services/`. `draw_for_person` in
`services/allocation.py` is drawn on by both the coder and auditor allocators —
prefer extending a shared function over copying it.

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

## Git

Another agent works in this repository. **Stage named paths**, never
`git add -A`.

The repo is **public**: no credentials, no deploy-hook URLs, no database dumps.
`.gitignore` blocks `*.tar.gz`, `*.dump`, `*.sql.gz` and `*.bak` for that
reason; overriding needs a deliberate `git add -f`.

A push to `main` deploys to production automatically.
