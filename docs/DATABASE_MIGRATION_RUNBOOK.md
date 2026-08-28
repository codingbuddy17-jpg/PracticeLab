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
    _run_migrations()                        # 21 raw CREATE TABLE + 92 ALTERs
    report_schema_drift()                    # logs any column the models expect
                                             # and the database does not have
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

**Directory format** (`--format=directory --jobs=4 --file=DIRNAME`) is the third
option and is what the backups committed to `docs/` in this repository use. It
writes a directory of per-table files rather than one file, which is why those
backups arrive as a `.tar.gz` — see §4.3.

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

#### Restoring the `.tar.gz` backups from `docs/`

The backups placed in this repository's `docs/` folder are **directory-format**
dumps that have been tarred. They are not plain SQL: `psql -f` will not read
them, and that is the most common first mistake. Extract, then `pg_restore`
against the extracted **directory**:

```bash
tar -xzf 2026-08-14T14_26Z.dir.tar.gz
```

That produces a timestamped directory containing a `chartviewer/` directory of
`.dat` files and a `toc.dat`. Point `pg_restore` at that inner directory:

```bash
createdb practicelab

pg_restore \
  --no-owner \
  --no-privileges \
  --clean --if-exists \
  --dbname="postgresql://USER:PASSWORD@HOST:PORT/practicelab" \
  "2026-08-14T14:26Z/chartviewer"
```

Notes on that command:

- The directory name contains **colons**, so it must be quoted. An unquoted
  path fails in a way that looks like a missing file.
- `--clean --if-exists` drops existing objects first, so the restore is
  repeatable. Omit both when restoring into a database you have just created —
  they are only needed when overwriting.
- Add `--jobs=4` to restore tables in parallel. This is the main reason to use
  directory format; it is not available for plain-SQL dumps.
- To inspect a dump without restoring it: `pg_restore --list "DIR/chartviewer"`.

**What the dump does not contain.** The admin passphrase and the storage
credentials live in environment variables, never in the database (§2). A
restored database on its own will not start the application — set the
environment variables too, or the API boots and fails every file request.

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

### 6.1 The current provider: Cloudflare R2

The bucket is **Cloudflare R2**, which speaks the S3 API. The application uses
`boto3` — the standard AWS SDK — pointed at R2's endpoint rather than AWS:

```python
boto3.client(
    "s3",
    endpoint_url=settings.STORAGE_ENDPOINT_URL,
    aws_access_key_id=settings.STORAGE_ACCESS_KEY,
    aws_secret_access_key=settings.STORAGE_SECRET_KEY,
    config=Config(signature_version="s3v4"),
)
```

Because it is plain S3, the receiving team can point this at **any**
S3-compatible target — AWS S3, MinIO, Ceph, an internal object store — by
changing three environment variables. No code change.

### 6.2 What to collect from the Cloudflare account

| Needed | Where it comes from | Maps to |
|---|---|---|
| Account ID | Cloudflare dashboard → R2 | Part of `STORAGE_ENDPOINT_URL` |
| R2 API token (Access Key ID + Secret) | R2 → Manage API Tokens → Create | `STORAGE_ACCESS_KEY` / `STORAGE_SECRET_KEY` |
| Bucket name | R2 → Buckets | `STORAGE_BUCKET_NAME` |

The endpoint takes the form:

```
https://<ACCOUNT_ID>.r2.cloudflarestorage.com
```

**The secret is shown once, at creation.** If nobody has it, it cannot be
recovered — create a new API token. That is safe: tokens are independent, and
issuing a new one does not affect the objects in the bucket.

Token permissions needed: **read and write** on the bucket. The application
uploads on chart upload, reads on chart view, and deletes on chart removal.

### 6.3 Two routes for the move

**Route A — keep Cloudflare, re-point the new backend at it.** Fastest, and no
data movement. The internal environment must be able to reach
`*.r2.cloudflarestorage.com` outbound. Keeps a dependency on an external
provider, which your security team may or may not accept.

**Route B — copy the bucket to internal storage.** With `rclone` (which
supports R2 and most S3-compatible targets natively):

```bash
rclone sync r2:SOURCE_BUCKET internal:TARGET_BUCKET --progress
```

Or with the AWS CLI, configured against R2's endpoint:

```bash
aws s3 sync s3://SOURCE_BUCKET s3://TARGET_BUCKET \
  --endpoint-url https://<ACCOUNT_ID>.r2.cloudflarestorage.com
```

**Preserve the object keys exactly.** They are stored in
`chart_files.storage_key` and are how the database finds each image. A copy
that re-prefixes or renames keys silently breaks every chart.

### 6.4 One trap in the environment variables

`STORAGE_PUBLIC_URL` is **required** — the application will not start without
it — but no application code reads it. It is a leftover.

Set it to anything non-empty (the bucket URL is the sensible choice) and do not
spend time working out what it should point at. Flagged here because a team
debugging a startup failure will otherwise go looking for the meaning of a
variable that has none.

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
UNION ALL SELECT 'audit_batches', COUNT(*) FROM audit_batches
UNION ALL SELECT 'audit_assignments', COUNT(*) FROM audit_assignments
UNION ALL SELECT 'audit_results', COUNT(*) FROM audit_results
UNION ALL SELECT 'audit_key_sets', COUNT(*) FROM audit_key_sets
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

## 8. Reference code sets — a manual step nothing will remind you about

The application carries the CMS code sets: **ICD-10-CM, ICD-10-PCS and HCPCS
Level II**, plus the CC/MCC severity list from the MS-DRG Definitions Manual.
They are loaded by a **standalone script that nothing calls automatically**:

```bash
DATABASE_URL="postgresql://..." python scripts/ingest_code_sets.py            # report only
DATABASE_URL="postgresql://..." python scripts/ingest_code_sets.py --write    # load it
```

Roughly 186,000 rows, about two minutes. It needs `DATABASE_URL` and creates
its own tables, so it can be run before the API has ever booted.

**Read this part.** If the script is never run, the application does not fail
and nothing in the logs says anything is missing. Every feature that depends on
it degrades to silence, so it simply looks as though these features do not
exist:

| Without the load | What the user sees |
|---|---|
| Code descriptions under every code box | Nothing — the code alone |
| Type-ahead code completion | No suggestions ever appear |
| Answer-key upload flagging codes that do not exist | No warning |
| Answer-key upload checking CC/MCC labels | No warning |
| Auditor error generator constrained to real PCS codes | Two-thirds of planted PCS errors are strings that are not codes |

That last row is the one with teeth: it changes what auditors are scored on,
not just what they see.

`GET /codes/status` reports what is loaded and when. It is the quickest way to
answer "has anyone run this here?".

### 8.1 No outbound route to cms.gov?

Expected in an internal environment. Download the files elsewhere, put them in
a directory, and point the script at it:

```bash
DATABASE_URL="postgresql://..." python scripts/ingest_code_sets.py --from-dir /path/to/cms/files --write
```

It matches files by name, so keep the names CMS ships them under. The four
sources are the ICD-10-CM code descriptions, the ICD-10-PCS code tables, the
alphanumeric HCPCS file, and the MS-DRG Definitions Manual (for `appendix_C`).
Each is independent — a missing one is skipped with a message, and the rest
still load.

### 8.2 Where to run it — not on the API service

It peaks at about **380 MB of memory**. A Render Starter instance has 512 MB,
and the API is already using some of it, so running this from a shell on the
API service risks killing the web service. Two safe options:

1. **From a workstation, against the external database URL.** Clone the repo,
   set `DATABASE_URL` to the *external* connection string from the Render
   dashboard (not the internal one), and run it. Nothing else needs to be
   configured — the script only touches the code tables.
2. **As its own scheduled job** with its own memory allowance (§8.4).

Either way it is safe against a live database: it replaces one code set at a
time inside a transaction, and the application keeps serving throughout.

### 8.3 Running it from the trainer workspace

The trainer workspace includes **Code Set Maintenance**. Enter the master
passphrase and click **Run CMS Ingest** to start the same script from the
application. The request starts a background process and the page polls for the
job status and recent log lines.

Use this during testing, or when an administrator wants to refresh the tables
without opening a server shell. It still runs in the web service process, so a
dedicated scheduled job remains cleaner for production if the hosting plan has
tight memory limits.

### 8.4 Scheduling it instead of remembering it

The source URLs are **derived from the current date**, not hardcoded, so the
same command run in any future quarter fetches that quarter's files. That
makes it schedulable as-is — nothing needs editing each year.

On Render, that is a **Cron Job** service pointed at this repo with the command
`DATABASE_URL="..." python scripts/ingest_code_sets.py --write`, sharing the
database. Quarterly, a few days into January, April, July and October — CMS
publishes on the first and a few days' margin avoids a race. Internally, the
same command on cron, systemd timer, or whatever the organisation uses for
scheduled work.

A failed run is not an outage: the previous edition stays loaded, because each
code set is only deleted at the moment its replacement is ready to insert.

### 8.5 When to run it again

- **ICD-10-CM and ICD-10-PCS** — annually, effective 1 October.
- **HCPCS Level II** — quarterly.
- **MS-DRG manual** — annually, and it is usually published *after* the code
  set, so the script will tell you when the severity list is a year behind the
  codes.

Re-running replaces each code set wholesale rather than merging, because codes
are deleted between editions as well as added — merging would leave retired
codes looking current. It is safe to run against a live database.

**CPT is not included and cannot be.** CPT is AMA copyright and licensed per
user. CPT lines render their code without a description, and the answer-key
checks deliberately do not judge five-digit numeric codes rather than pretend
to have checked them. If your organisation holds an AMA licence, that is a
separate decision and a separate data source.

---

## 9. Table inventory

**46 tables, 645 columns.** Grouped by subsystem:

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

**Auditor** — `audit_batches`, `audit_batch_auditors`, `audit_allocation_cycles`,
`audit_assignments`, `audit_sessions`, `audit_chart_drafts`, `audit_results`,
`audit_key_sets`, `audit_scoring_configs`

**Reference code sets** — `code_descriptions`, `pcs_code_axes`,
`code_set_versions`, `cc_exclusions`, `drg_weights`

> The five reference tables hold CMS data, not application data: what each
> code means, which PCS codes exist, and which edition is loaded. They are
> populated by `scripts/ingest_code_sets.py` (§8) and by nothing else, so a
> restore that omits them costs a two-minute reload rather than any user data.
> Today the script populates `code_descriptions`, `pcs_code_axes`, and
> `code_set_versions`. `cc_exclusions` and `drg_weights` are schema placeholders
> for later DRG-reference work and are not populated yet.

> The Auditor subsystem was added after the first version of this document.
> Its nine tables are ORM-backed, so `create_all()` builds them — but the
> columns added to them afterwards are not, which is the trap described in
> §5.1. Note that `audit_logs` (singular subsystem, listed under Chart Library)
> is unrelated to the Auditor module despite the name; it is the chart audit
> trail and predates it.

---

## 10. Ongoing operations

- **Reference code sets.** Re-run `scripts/ingest_code_sets.py --write` when
  CMS republishes — or schedule it, §8.4.

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

## 11. Open items for the receiving team

1. Confirm the PostgreSQL major version to provision (§4.1).
2. Decide storage: re-point at the existing bucket, or copy it (§6).
3. Confirm who holds `MASTER_ADMIN_PASSPHRASE` and how it is rotated.
4. Set `CORS_ORIGINS` to the internal frontend origin — a mismatch here
   produces a frontend that loads and then fails every request.
5. Agree the backup schedule and retention.
6. Run the code-set ingest once after the first deploy (§8.2), and either
   schedule it quarterly (§8.4) or decide who owns re-running it.
