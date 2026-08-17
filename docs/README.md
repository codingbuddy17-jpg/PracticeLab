# Handover documents

Everything the team receiving this application needs, and nothing that only
made sense while it was being built.

## Read in this order

| # | Document | What it answers |
|---|---|---|
| 1 | [PROJECT_SUMMARY.md](PROJECT_SUMMARY.md) | What the application is for, how it is put together, how to run it locally |
| 2 | [DATABASE_MIGRATION_RUNBOOK.md](DATABASE_MIGRATION_RUNBOOK.md) | Moving it to your own infrastructure: dump and restore, environment variables, what happens on first boot, verification, the reference code sets, ongoing operations |
| 3 | [DATA_STORAGE_MODEL.md](DATA_STORAGE_MODEL.md) | Where the data actually lives — what is in PostgreSQL, what is in object storage, and how to size both |

The runbook is the operational one. If you read only part of anything, read
**§5 (what happens on first boot)** and **§8 (the reference code sets)** — those
two describe things that will not announce themselves if you skip them.

## The Word versions

| File | Same content as |
|---|---|
| `PracticeLab_Data_Architecture_and_Migration.docx` | the summary and runbook, formatted for circulation |
| `PracticeLab_Database_Schema_Reference.docx` | every table and column, with a one-line description each |

**These are generated, not written.** Edit the Markdown or the builders below,
never the `.docx` — a hand edit is lost on the next build.

## Regenerating them

**Read this first: the build inputs are not in the working tree.** The
`figures/` directory — the eight diagrams, `schema.json`, and the hand-written
`tabledocs.json` — was deliberately removed to keep this folder to the
documents themselves. It is still in git history, and a rebuild needs it back:

```bash
cd <repo root>
git checkout "$(git rev-list -1 HEAD -- docs/figures)^" -- docs/figures
```

Then:

```bash
cd docs
python _schema_json_build.py          # refresh figures/schema.json
cd figures && node ../_schema_docx_build.js && node ../_spec_docx_build.js
mv *.docx ..
```

Note that only `schema.json` and three of the eight diagrams can be rebuilt
from source; the rest exist solely in history, so restore rather than
recreate them.

`_schema_json_build.py` builds the schema the way the application does —
`create_all()` plus the raw migration DDL against a throwaway SQLite file — then
introspects it. That matters: six tables exist only in raw DDL and are invisible
to the ORM models, so introspecting the models alone silently omits them.

Counts in the documents are derived from `schema.json`, not typed. They were
typed once and were wrong within a month, twice.

| File | Role |
|---|---|
| `_schema_json_build.py` | regenerates `figures/schema.json` from the live schema |
| `_schema_figures_build.py` | regenerates three of the ERDs as SVG |
| `_schema_docx_build.js` | builds the schema reference `.docx` |
| `_spec_docx_build.js` | builds the architecture and migration `.docx` |

`tabledocs.json` — the one-line description of each table — is hand-written and
is the one input worth editing by hand. It lives in the restored `figures/`
directory.

The two `.js` builders need one npm package. Install it only if you are
actually rebuilding the documents, and delete it again afterwards:

```bash
cd docs && npm install docx      # then rebuild as above
rm -rf docs/node_modules
```

It is deliberately not kept in the folder: ten megabytes of dependencies for a
document you may never need to regenerate is clutter, and it is not committed,
so a fresh clone will not have it either.

## Also worth knowing

- `../CLAUDE.md` in the repository root is written for engineers picking the
  code up cold. It is blunter than these documents and covers the traps that
  have actually cost time.
- The API documents itself at `/docs` (OpenAPI) once it is running.
