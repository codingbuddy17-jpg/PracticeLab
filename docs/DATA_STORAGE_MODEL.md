# PracticeLab — Where the Data Lives

Companion to `DATABASE_MIGRATION_RUNBOOK.md`. This one answers a narrower
question: when a trainer uploads a chart or an answer-key spreadsheet, what is
actually stored, and where.

There are **two** stores, and they behave completely differently.

| | Object storage (S3-compatible) | PostgreSQL |
|---|---|---|
| Chart page images | ✅ the only copy | key + extracted text only |
| Original uploaded PDF | ❌ **not retained** | ❌ |
| Answer-key spreadsheets | ❌ **not retained** | parsed values only |
| Question-bank spreadsheets | ❌ **not retained** | parsed rows only |
| Everything else | ❌ | ✅ |

The headline for the migration: **chart images must be migrated separately from
the database, and no uploaded spreadsheet needs migrating at all** — because
none of them were ever kept.

---

## 1. Charts

### What happens on upload

A trainer uploads a PDF, image or Word document. The application does **not**
store that file. It converts it:

```
upload.pdf  →  process_file()  →  page 1 PNG, page 2 PNG, page 3 PNG …
```

- **PDFs** are rendered page-by-page to PNG at 1.7× scale
- **Images** (png/jpg/tiff/bmp/webp) are converted to PNG
- **Word documents** are rendered to page images
- Anything else is rejected

Each resulting page is uploaded to object storage. The original file is
discarded once conversion completes.

> **This is worth stating plainly to the team:** there is no archive of source
> PDFs anywhere in the system. The page images in object storage **are** the
> charts. Losing that bucket means losing every chart, and no database backup
> will bring them back.

### Storage key format

```
charts/{chart_id}/{page_order:04d}_{original_filename}.png
```

Example: `charts/142/0000_Discharge Summary.pdf.png`

Note the key contains the **numeric `chart_id`**, not the human chart number
(`IP001`). Two consequences:

- A straight bucket copy that preserves keys needs no database changes.
- Renaming a chart in the UI does not move any files.

### What PostgreSQL holds

`chart_files` — one row per page:

| Column | Contents |
|---|---|
| `storage_key` | Path into the bucket (above) |
| `page_order` | Page sequence |
| `page_text` | Text extracted at upload, used for in-chart search |
| `original_filename`, `total_pages`, `uploaded_by` | Metadata |

`charts` — one row per chart: number, alias, specialty, category, difficulty,
status, rationale, view count, uploader.

### How pages reach the browser

**The API proxies every image. The browser never contacts the storage bucket.**

```
browser  →  GET /charts/142/page/0  →  API  →  fetches from bucket  →  streams bytes back
```

`proxy_chart_page` in `routers/charts.py` calls `get_object()` server-side and
returns a `StreamingResponse`. The browser only ever sees an API URL.

This has real consequences for the internal deployment:

| | |
|---|---|
| Does the front end query storage? | **No.** It requests an API path like any other endpoint |
| Does the browser hold storage credentials? | **No.** They exist only in the backend's environment |
| Must the bucket be reachable from user browsers? | **No.** Only from the backend |
| Does the bucket need CORS configured? | **No** |
| Can the bucket be fully private / internal-network-only? | **Yes** |

> A `get_presigned_url()` helper exists in `services/storage.py` and is
> imported, but **is never called**. Presigned URLs are not in use. If you read
> that function and assume browsers fetch directly from the bucket, you will
> configure network access that is not needed.

Responses carry `Cache-Control: private, max-age=3600`, so a browser re-uses a
page image for an hour without asking again.

---

## 2. Answer keys and other spreadsheet inputs

### The short version

**No uploaded spreadsheet is stored anywhere.** Not in the database, not in
object storage. Every Excel upload path reads the bytes, parses them, writes
the parsed values to PostgreSQL, and discards the file.

Verified across all three upload paths — IP/OP answer keys, E/M answer keys,
and the assessment question bank. None of them touch object storage.

### What that means practically

- **For migration:** there is nothing to migrate. Once the database is
  restored, every key is present.
- **For the trainers:** the spreadsheet they uploaded is not recoverable from
  the application. If they want the original file, they keep their own copy.
  The app can *regenerate* an equivalent spreadsheet from stored data — the
  answer-key export produces one row per chart in the upload layout — but it is
  a fresh export, not the file they sent.
- **For audit:** there is no record of the file itself, only its effects.

### Where the parsed values land

**IP/OP answer keys** → `answer_keys`, one row per chart:

| Column | Type | Contents |
|---|---|---|
| `pdx_code`, `pdx_poa` | text | Principal diagnosis and POA |
| `sdx` | JSON | `[{code, poa, ccmcc}, …]` |
| `pcs` | JSON | `[{code}, …]` (inpatient procedures) |
| `cpt` | JSON | `[{code, modifier, pointers, units}, …]` |
| `facility_level`, `profee_level` | text | ED Single Path only |

**E/M answer keys** → `em_answer_keys`, one row per chart: 47 columns
covering the MDM element counts (COPA, Data Review, Risk), the derived levels,
the E/M code and modifier, the encounter category, critical-care minutes, plus
`dx_codes` and `procedure_cpts` as JSON.

**Assessment questions** → `assessment_questions`, one row per question: text,
four options, correct answer, specialty, topic, difficulty, status.

### A note on the JSON columns

19 columns across the schema are typed `JSON`. On PostgreSQL these are real
JSON columns; on SQLite (local development only) they are TEXT and the driver
deserialises them. This matters for anyone writing SQL directly against the
database in the internal environment: `answer_keys.cpt` is queryable with
PostgreSQL JSON operators, and its shape is documented above rather than being
enforced by the schema.

---

## 2.4 Choosing a storage backend for the internal environment

### What the application actually requires

Before comparing products, this is the whole requirement. The application
performs exactly **three** storage operations:

| Operation | When |
|---|---|
| `put_object` | A chart is uploaded — one call per page |
| `get_object` | A chart page is viewed |
| `delete_object` | A chart is removed |

That is all. No listing, no multipart uploads, no versioning, no lifecycle
rules, no ACLs, no bucket policies, no tagging, no presigned URLs (the helper
exists but is never called). It stores blobs under keys and reads them back.

**This is the least demanding thing an application can ask of object storage**,
and it means the choice is governed by what your organisation already runs
rather than by any capability the app needs.

### The three tiers of migration effort

**Tier 1 — change three environment variables, no code change.** Anything that
speaks the S3 API. The client is constructed with a configurable
`endpoint_url`, so it is already pointed at a non-AWS S3 service today.

| Option | Typical enterprise context |
|---|---|
| **AWS S3** | Already on AWS; the reference implementation |
| **MinIO** | Self-hosted, runs in the org's own datacentre or Kubernetes. The common answer when data must not leave the building |
| **Ceph RADOS Gateway** | Org already runs Ceph for block/object storage |
| **Dell ECS, NetApp StorageGRID, Pure FlashBlade, Hitachi HCP** | On-premises enterprise object storage appliances, all with S3 front ends |
| **Google Cloud Storage** | Via its S3-compatible XML API with HMAC keys — works, but is the least-travelled path of these |
| **Wasabi, Backblaze B2** | Lower-cost S3-compatible clouds; usually a cost decision rather than a policy one |

For all of these the change is:

```
STORAGE_ENDPOINT_URL   → the new service's endpoint
STORAGE_ACCESS_KEY     → new access key
STORAGE_SECRET_KEY     → new secret
STORAGE_BUCKET_NAME    → new bucket (if renamed)
```

**Tier 2 — replace three functions, roughly thirty lines.** Backends that do
not speak S3. In practice this means one:

| Option | Why it comes up |
|---|---|
| **Azure Blob Storage** | The single most likely alternative in a Microsoft-centric organisation. It has no native S3 API |

`services/storage.py` contains `upload_bytes`, `get_object` usage and
`delete_object` behind a thin wrapper. Swapping the body of those for the
Azure SDK (`azure-storage-blob`) is a contained change — the rest of the
application only ever calls those wrappers and never touches boto3 directly,
with one exception noted below.

**Tier 3 — same three functions, plus think about durability.** A mounted file
share (NFS, SMB) or the server's own disk. Simplest to implement — write to a
path, read from a path — but the storage is then only as safe as that volume's
backup, and horizontal scaling of the API requires shared storage rather than
local disk. Reasonable for a single-server internal deployment; a step
backwards from object storage otherwise.

### Where the change would be made

**`backend/services/storage.py`, and nowhere else.** Every storage call in the
application goes through it:

| Function | Used by |
|---|---|
| `upload_bytes(key, data, content_type)` | Chart upload |
| `open_object(key)` | Chart page view — returns `(body, content_type)` |
| `delete_object(key)` | Chart removal |

`boto3` is imported in that one file. A Tier 2 or Tier 3 move rewrites the
bodies of those three functions and touches nothing else.

`get_presigned_url()` also lives there and is never called — see 2.1. A backend
swap can ignore it, or delete it.

### The recommendation

If the organisation has **any** existing object storage — Ceph, MinIO,
StorageGRID, ECS, an AWS account — use it. It is a Tier 1 move: three
variables, no code, no testing burden beyond the smoke test.

Reach for Azure Blob only if the organisation is Azure-standardised and object
storage elsewhere would be an exception to policy. The work is small but it is
real code, and code needs testing that configuration does not.

Avoid the file-share option unless the deployment is genuinely single-server
and expected to stay that way.

### What does not change, whichever is chosen

- The database is untouched. `chart_files.storage_key` holds the same keys
- The browser still never contacts storage (see 2.1) — the API proxies
- No CORS configuration is needed on the new backend
- The bucket needs to be reachable only from the backend, so it can sit
  entirely inside the internal network

---

## 3. What this means for the migration

### Migrate these

1. **PostgreSQL** — everything except chart page images (`pg_dump`, see the
   runbook)
2. **The object storage bucket** — or re-point at the existing one

### Do not look for these — they do not exist

- Original chart PDFs
- Uploaded answer-key spreadsheets
- Uploaded question-bank spreadsheets
- Generated coder workbooks (the offline Excel workflow was removed; coders
  work in the browser)
- Anything belonging to the Auditor module. It was added after this document
  was first written and introduces **no new storage surface**: the pre-coded
  claim each auditor sees, the errors introduced into it, and every finding
  they record are JSON columns on `audit_assignments`, `audit_chart_drafts` and
  `audit_results`. Auditors read the same chart images through the same
  presigned URLs as coders. Nothing about the two-store split above changes.

### Order matters

Restore the database **before** the first application boot (see the runbook,
§5.3). The storage bucket can be copied at any point — the application only
reads from it when someone opens a chart.

### The failure mode to watch for

A database-only migration produces an application that looks entirely healthy:
charts list, batches open, results display, analytics compute. Every chart is a
broken image. **Verify by opening a chart and confirming the page renders**, not
by confirming the chart appears in a list.

---

## 4. Sizing

To estimate the bucket:

```sql
SELECT COUNT(*) AS page_count FROM chart_files;
```

Every row is one PNG. Typical rendered chart pages run a few hundred KB each,
so multiply for a rough figure — or query the bucket directly for the exact
size, which is more reliable than an estimate.

The PostgreSQL side is small by comparison: text, codes and JSON, with no
binary content of any kind.
