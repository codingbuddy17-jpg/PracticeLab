# PracticeLab — Database Migration Runbook

For moving the application from its current hosting to an internal environment.
Written for the receiving infrastructure/DBA team.

---

## 1. The short answer to "send us the scripts and backup"

**There is no schema script to send.** This application has no `schema.sql` and
no Alembic. It creates its own schema on first boot:

```python
def init_db():
    Base.metadata.create_all(bind=engine)   # tables defined as ORM models
    _run_migrations()                        # 21 raw CREATE TABLE + ~100 ALTERs
```

So the schema *is* the application. Point the API at an empty PostgreSQL
database, set the environment variables, start it, and it builds everything.

**The backup is a normal `pg_dump`.** That part is conventional — see §4.

> **Do not** try to build the schema by hand from the ORM models. Six tables
> exist only in the raw migration DDL and are absent from the models
> (`em_answer_keys`, `em_grading_results`, `em_scoring_configs`,
> `practice_sessions`, `practice_chart_drafts`, `practice_results`).
> `create_all()` alone produces a database that looks right and is missing the
> entire E/M and practice-session subsystem.

---

## 2. What the application needs

| Component | Requirement |
|---|---|
| Database | PostgreSQL. Confirm the source version first — see §4.1 |
| API runtime | Python 3.11.9 (`backend/runtime.txt`) |
| Object storage | S3-compatible bucket — **see §6, this is not optional** |

### Environment variables (all required unless noted)

| Variable | Purpose |
|---|---|
| `DATABASE_URL` | PostgreSQL connection string |
| `STORAGE_ENDPOINT_URL` | S3-compatible endpoint |
| `STORAGE_ACCESS_KEY` | Storage access key |
| `STORAGE_SECRET_KEY` | Storage secret key |
| `STORAGE_BUCKET_NAME` | Bucket holding chart files |
| `STORAGE_PUBLIC_URL` | Public base URL for file access |
| `MASTER_ADMIN_PASSPHRASE` | Gates protected trainer actions. No default — the app will not start without it |
| `CORS_ORIGINS` | Comma-separated allowed frontend origins (default: localhost dev) |
| `FRONTEND_URL` | Optional, defaults to localhost dev |

`DATABASE_URL` accepts `postgres://`, `postgresql://` or `postgresql+asyncpg://`
— the app normalises the scheme itself.

---

## 3. Recommended migration path

**Restore a full dump into an empty database, then start the app.** Not the
other way round. The reason is in §5.

```
1. Provision empty PostgreSQL database
2. pg_dump from source              (§4)
3. pg_restore into the new database (§4)
4. Verify row counts                (§7)
5. Set environment variables, start the API
6. Check startup logs for migration warnings (§5)
7. Verify via /health and a real screen
```

---

## 4. Dump and restore

### 4.1 Confirm the source version first

```sql
SELECT version();
```

Restoring into an **older** major version than the source will fail. Match the
major version, or go newer.

### 4.2 Dump

Custom format, which restores faster and lets you restore selectively:

```bash
pg_dump \
  --format=custom \
  --no-owner \
  --no-privileges \
  --file=practicelab_$(date +%Y%m%d).dump \
  "postgresql://USER:PASSWORD@HOST:PORT/DBNAME"
```

- `--no-owner` / `--no-privileges` — the internal database will have different
  role names. Without these the restore emits errors for every object.
- Add `--verbose` if you want per-object progress.

A plain-SQL dump (`--format=plain --file=practicelab.sql`) is also fine and is
easier to read and review, but restores more slowly.

### 4.3 Restore

Into a genuinely empty database:

```bash
createdb practicelab

pg_restore \
  --no-owner \
  --no-privileges \
  --dbname="postgresql://USER:PASSWORD@HOST:PORT/practicelab" \
  practicelab_YYYYMMDD.dump
```

For a plain-SQL dump: `psql -d "postgresql://..." -f practicelab.sql`

Expect zero errors. Investigate any that appear rather than proceeding — a
partially restored database will still start the app, because the app's
migrations will happily create whatever is missing as empty tables.

---

## 5. What happens on first boot — read this before starting the API

`init_db()` runs on every application start, not just the first. Three
behaviours the team should understand:

### 5.1 Migrations are additive and non-fatal

Every migration step is wrapped so that a failure is **logged as a warning and
startup continues**:

```python
logger.warning("Migration DDL failed (non-fatal): %s | sql=%s", exc, sql[:200])
```

This is deliberate — a schema problem should not take the API down — but it
means **a partial failure is quiet**. After the first boot against the new
database, search the startup logs for:

```
Migration DDL failed
```

On a correctly restored database this should appear **zero** times. Anything
there needs investigating before the app is considered live.

### 5.2 There is no migration version table

Nothing records which migrations have run. Each one re-checks whether its
column or table already exists and skips if so. Consequences:

- Running the app repeatedly is safe and idempotent.
- Your DBA **cannot** ask "what schema version is this?" The honest answer is
  "whatever the currently deployed code builds."
- Rolling the application back to an older release does **not** roll the schema
  back. The schema only moves forward.

### 5.3 Sample data is seeded into an empty question bank

If `assessment_questions` is empty at boot, the app inserts sample assessment
questions. This is why the restore must come **before** the first boot:

- **Restore first, then boot** → table is populated, seed skips. Correct.
- **Boot first, then restore** → seeded rows already exist and the restore will
  hit unique-constraint violations on `question_id`. Avoid.

If the app has already been booted against the empty database, drop and
recreate the database before restoring rather than trying to reconcile.

---

## 6. The database is not the whole application

**Chart PDFs and page images are not stored in PostgreSQL.** The database holds
only storage keys pointing into S3-compatible object storage.

A database-only migration produces a working application in which **every chart
is a broken link**. You need one of:

1. **Re-point** the new environment at the existing bucket (fastest; keeps a
   dependency on the current storage provider), or
2. **Copy the bucket** to internal storage and update the `STORAGE_*` variables
   (e.g. `aws s3 sync`, `rclone`, or the provider's own tooling).

Storage keys follow the pattern `charts/{chart_id}/...`, so a straight bucket
copy preserving keys requires no database changes.

`DATA_STORAGE_MODEL.md` covers this in full: what a chart upload actually
becomes, why no uploaded spreadsheet needs migrating, and how to size the
bucket.

---

## 7. Verification

### 7.1 Row counts — run against source and target, compare

```sql
SELECT 'charts', COUNT(*) FROM charts
UNION ALL SELECT 'chart_files', COUNT(*) FROM chart_files
UNION ALL SELECT 'answer_keys', COUNT(*) FROM answer_keys
UNION ALL SELECT 'em_answer_keys', COUNT(*) FROM em_answer_keys
UNION ALL SELECT 'batches', COUNT(*) FROM batches
UNION ALL SELECT 'batch_charts', COUNT(*) FROM batch_charts
UNION ALL SELECT 'grading_results', COUNT(*) FROM grading_results
UNION ALL SELECT 'practice_sessions', COUNT(*) FROM practice_sessions
UNION ALL SELECT 'practice_results', COUNT(*) FROM practice_results
UNION ALL SELECT 'assessment_questions', COUNT(*) FROM assessment_questions
UNION ALL SELECT 'assessment_sessions', COUNT(*) FROM assessment_sessions
UNION ALL SELECT 'assessment_results', COUNT(*) FROM assessment_results
ORDER BY 1;
```

### 7.2 Sequences

A `pg_restore` of a custom-format dump normally restores sequence positions
correctly. Verify rather than assume — the symptom of getting this wrong is a
duplicate-key error on the first insert after go-live.

Check for any sequence sitting below its table's maximum id:

```sql
SELECT
  s.relname            AS sequence_name,
  t.relname            AS table_name,
  last_value
FROM pg_class s
JOIN pg_depend d  ON d.objid = s.oid
JOIN pg_class t   ON t.oid = d.refobjid
JOIN pg_sequences ps ON ps.sequencename = s.relname
WHERE s.relkind = 'S'
ORDER BY t.relname;
```

Compare each `last_value` against `SELECT MAX(id) FROM <table>`. To repair one:

```sql
SELECT setval(
  pg_get_serial_sequence('charts', 'id'),
  (SELECT COALESCE(MAX(id), 1) FROM charts)
);
```

Repeat per affected table. Note that six tables were originally created with
`INTEGER PRIMARY KEY` rather than `SERIAL` and had sequences attached later by
migration (`practice_sessions`, `practice_chart_drafts`, `practice_results` and
their dependants) — these are the most likely to need attention.

### 7.3 Application health

```bash
curl -s https://YOUR-INTERNAL-API/health
# {"status":"ok"}
```

`/health` confirms the process is up. It does **not** touch the database — use
this instead for a real read:

```bash
curl -s "https://YOUR-INTERNAL-API/charts/search?page_size=1"
```

### 7.4 End-to-end smoke test

1. Chart Library — search a chart, open it, confirm the **file renders** (this
   is the storage check from §6, and the one most likely to fail)
2. PracticeLab — open an existing batch, confirm results and scores display
3. Assessment — open Analytics, confirm figures match the source environment

---

## 8. Table inventory

32 tables. Grouped by subsystem:

**Chart Library** — `charts`, `chart_files`, `chart_sequences`, `chart_feedback`,
`audit_logs`, `coding_resources`

**PracticeLab** — `batches`, `batch_coders`, `batch_charts`,
`batch_allocation_cycles`, `submissions`, `grading_results`, `grading_feedback`,
`ed_rubric_details`, `answer_keys`, `scoring_configs`, `self_practice_submissions`,
`self_practice_results`

**PracticeLab E/M** — `em_answer_keys`, `em_grading_results`, `em_scoring_configs`

**PracticeLab sessions** — `practice_sessions`, `practice_chart_drafts`,
`practice_results`

**Assessment** — `assessment_questions`, `assessment_configs`,
`generated_assessments`, `generated_assessment_students`, `assessment_sessions`,
`assessment_responses`, `assessment_results`, `assessment_audit_log`

---

## 9. Ongoing operations

- **Backups.** Nothing in the application performs them. Schedule
  `pg_dump` (daily is typical) plus a bucket backup for the chart files.
- **Deployments.** Each release runs `init_db()` again. Additive migrations
  apply automatically; check the logs for `Migration DDL failed` after any
  deploy that changed the schema.
- **Rollback.** Application rollback does not roll the schema back. Because
  migrations only add, an older application release generally runs against a
  newer schema — but this is not guaranteed and should be tested rather than
  relied on.

---

## 10. Open items for the receiving team

1. Confirm the PostgreSQL major version to provision (§4.1).
2. Decide storage: re-point at the existing bucket, or copy it (§6).
3. Confirm who holds `MASTER_ADMIN_PASSPHRASE` and how it is rotated.
4. Set `CORS_ORIGINS` to the internal frontend origin — a mismatch here
   produces a frontend that loads and then fails every request.
5. Agree the backup schedule and retention.
