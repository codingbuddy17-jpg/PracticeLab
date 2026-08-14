# PracticeLab — Project Summary

An orientation document for anyone new to this codebase: what the application
does, how it is put together, and how to run it.

Companion documents:

| Document | Answers |
|---|---|
| `DATABASE_MIGRATION_RUNBOOK.md` | How to move the database and start the app elsewhere |
| `DATA_STORAGE_MODEL.md` | What is stored, and in which of the two stores |
| `PracticeLab_Database_Schema_Reference.docx` | Every table and column |
| `../CLAUDE.md` | Engineering conventions and the traps that have caused outages |

---

## 1. What the application is for

A training and assessment platform for **medical coders**. Coders read clinical
charts and assign standardised codes — diagnoses (ICD-10-CM), inpatient
procedures (ICD-10-PCS), outpatient procedures (CPT). Accuracy matters
commercially, because those codes drive reimbursement, so employers train and
measure coders continuously.

The platform supports four activities:

**Chart Library** — trainers upload clinical charts as PDFs. Pages are
extracted to images and served to coders in a viewer. Each chart gets a
sequential number prefixed by its specialty (`IP001`, `SURG014`).

**PracticeLab** — the coder workflow. A trainer creates a *batch*, adds coders,
and runs an *allocation* that deals charts out. Each coder gets a single-use
access code, codes their charts in the browser, and is graded automatically
against an answer key.

**Assessment** — multiple-choice knowledge testing, independent of charts.
Trainers build a question bank, generate papers with a chosen specialty and
difficulty mix, and issue timed sessions.

**Auditor** — the inverse of PracticeLab, and the newest module. Charts arrive
*already coded*, with errors deliberately introduced. The auditor's job is to
find them and correct them — the real-world work of an auditing coder. Roughly
a third of charts are deliberately left clean, because an auditor who flags
problems everywhere is as wrong as one who finds nothing.

### Specialties

Ten, and they behave differently — an inpatient DRG chart is graded on
different elements from an emergency-department facility chart:

`IP-DRG` · `ED Facility` · `ED Profee` · `ED Single Path` · `SDS` · `Surgery` ·
`Edits` · `Denials` · `Ancillary` · `E/M`

`E/M` is the outlier: it is graded on the 2023 AMA *medical decision making*
table rather than on code matching, and has its own tables and scoring path.

---

## 2. Architecture

```
   Browser  ─────────────►  chart-viewer-ui      (static site, React/Vite)
                                   │
                                   │  HTTPS/JSON
                                   ▼
                            chart-viewer-api     (FastAPI, Python 3.11)
                                   │
                    ┌──────────────┴──────────────┐
                    ▼                             ▼
             PostgreSQL 15                 S3-compatible storage
             everything except             chart page images
             chart images                  (Cloudflare R2)
```

Both stores matter. **Chart page images exist only in object storage** — the
database holds a key pointing at them. A database-only migration produces an
application that looks completely healthy and shows a broken image for every
chart. `DATA_STORAGE_MODEL.md` covers this.

**No user accounts.** There is no login system. Trainers reach `/trainer` by
knowing the URL; destructive actions require a shared admin passphrase. Coders
and auditors are admitted by single-use access codes issued per session
(`ABCD1234`, `AUD` prefix for auditors). This is a deliberate simplification
for a training tool inside a trusted network — it is not a security boundary,
and is worth revisiting if the platform is ever exposed more widely.

### Repository layout

```
backend/            FastAPI application
  main.py             app + router registration
  database.py         engine, session, schema creation and migrations
  models/             SQLAlchemy models: charts · practicelab · assessment · auditor
  routers/            HTTP layer, one *_pkg package per module
  services/           the actual logic: grading, allocation, scoring, exports
  tests/              ~2100 tests
frontend/src/
  api/                one module per backend area
  pages/              screens, grouped practicelab/ · assessment/ · auditor/
  components/         shared UI
scripts/            contract checkers run before pushing
docs/               this file and the migration documents
render.yaml         deployment definition
```

Business logic belongs in `services/` and is deliberately kept free of HTTP
concerns, which is what makes it directly testable. Routers validate, call a
service, and shape a response.

---

## 3. Key concepts

**Answer key** — the correct coding for a chart, uploaded by a trainer from a
spreadsheet. A chart with no answer key can be read but cannot be graded, and
is excluded from graded batches automatically.

**Batch** — a cohort of coders working a pool of charts. Filters (specialty,
category, difficulty) define the pool.

**Allocation cycle** — one run of the dealer over a batch. A batch can be
allocated repeatedly; each cycle issues fresh charts and fresh access codes.
Charts are dealt least-seen-first *per person*, so nobody repeats a chart while
anything unseen remains, and one coder exhausting the pool never blocks
another.

**Session** — one person's sitting, addressed by their access code. Work is
saved as they go; submission scores it and is final.

**Scoring** — configurable weights per element (principal diagnosis, secondary
diagnoses, procedures) varying by specialty. Inpatient charts additionally
check whether coding errors would have changed the **DRG**, the grouping that
determines payment — an error that changes the DRG matters far more than one
that does not.

**Introduced errors** (Auditor only) — generated from a weighted mix modelled
on real audit findings, so what an auditor practises against resembles what
they will meet. Trainers can also author specific errors by hand for a chart.

---

## 4. Running it locally

Requires Python 3.11 (3.9 also works locally), Node 18+, and nothing else —
local development uses SQLite and needs no database server.

**Backend:**

```bash
cd backend
python -m venv ../.venv && ../.venv/bin/pip install -r requirements.txt
cp .env.example .env          # defaults are fine for local work
../.venv/bin/uvicorn main:app --reload
```

The API starts on `http://localhost:8000`, creates its own schema on first
boot, and seeds sample assessment questions into an empty question bank.
Interactive API documentation is served at `http://localhost:8000/docs`.

**Frontend:**

```bash
cd frontend
npm install
npm run dev
```

Opens on `http://localhost:5173`, and needs no configuration: Vite proxies
`/api` to `http://localhost:8000` and strips the prefix
(`frontend/vite.config.ts`). Start the backend first or every request 404s.

Note the backend has **no** `/api` prefix of its own — routes are mounted at
the root (`/charts`, `/auditor/batches`). `/api` exists only as the local proxy
path and as the client's fallback when `VITE_API_URL` is unset. In production
`VITE_API_URL` is the bare API origin, with no `/api` suffix.

**Tests:**

```bash
cd backend && PYTHONPATH="$PWD:$PWD/tests" ../.venv/bin/python -m pytest tests -q
```

Two further checks guard against whole classes of breakage that unit tests miss
— a frontend calling a route that no longer exists, and specialty dropdowns
drifting out of step with the backend enum:

```bash
.venv/bin/python scripts/check_api_contracts.py
.venv/bin/python scripts/check_specialty_sync.py
```

---

## 5. Deployment

Hosted on Render, defined by `render.yaml`: a static site, a web service and a
managed PostgreSQL instance.

**A push to `main` deploys to production automatically.** There is no staging
environment. Treat `main` as live.

The API runs its schema migrations on every boot, so a deploy that adds a
column applies it during startup. Migrations are **additive only** — nothing is
ever dropped or renamed — which is what makes rolling the application back
safe. After any deploy that changed the schema, check the logs for
`Migration DDL failed`.

---

## 6. If you are picking this up cold

Read in this order:

1. This document.
2. `../CLAUDE.md` — the conventions, and the traps that have caused real
   outages. Short, and the `create_all()` section is the one that has cost the
   most.
3. `DATABASE_MIGRATION_RUNBOOK.md` — if you are moving or hosting it.
4. `backend/services/` — the logic worth understanding is here, not in the
   routers.

The test suite is the most reliable description of intended behaviour. Where a
test name reads like a sentence about the product rather than about the code,
that is deliberate.
