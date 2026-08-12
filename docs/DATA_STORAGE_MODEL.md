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

Files are **not** public. The API generates a **presigned URL** per request,
valid for one hour by default. So:

- Bucket ACLs can stay private
- A leaked URL expires
- The bucket must be reachable from the API, not from the user's browser
  directly

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
