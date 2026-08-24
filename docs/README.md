# Handover documents

Everything the team receiving this application needs, and nothing that only
made sense while it was being built.

## Read in this order

| # | Document | What it answers |
|---|---|---|
| 1 | [PROJECT_SUMMARY.md](PROJECT_SUMMARY.md) | What the application is for, how it is put together, how to run it locally |
| 2 | [DATABASE_MIGRATION_RUNBOOK.md](DATABASE_MIGRATION_RUNBOOK.md) | Moving it to your own infrastructure: dump and restore, environment variables, what happens on first boot, verification, the reference code sets, ongoing operations |
| 3 | [DATA_STORAGE_MODEL.md](DATA_STORAGE_MODEL.md) | Where the data actually lives — what is in PostgreSQL, what is in object storage, and how to size both |
| 4 | [CONTAINER_DEPLOYMENT.md](CONTAINER_DEPLOYMENT.md) | Running it as a container: building the image, the nine environment variables, what happens at startup, how to verify it actually works, and how to ship an update |

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
git checkout a323acc^ -- docs/figures/   # the eight diagrams, dropped from the repo
npm --prefix /tmp/docxbuild install docx  # build-time only, not an app dependency
python _schema_json_build.py            # rebuild figures/schema.json from the live schema
cd figures && NODE_PATH=/tmp/docxbuild/node_modules \
  node ../_schema_docx_build.js && node ../_spec_docx_build.js
mv *.docx .. && cd .. && rm -rf figures
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

## The live environment, as it actually is

| | URL |
|---|---|
| API | `https://chart-viewer-api-rxrd.onrender.com` |
| UI | `https://chart-viewer-ui.onrender.com` |

**The API host is not the name you would guess**, and earlier circulated
documents give `chart-viewer-api.onrender.com` — a host that now answers with
somebody else's HTML. Anyone testing against that URL will conclude the API is
broken when it is running perfectly. The frontend's own `VITE_API_URL` is the
authority if this table ever goes stale.

Confirm the deployment is actually working, rather than assuming from a green
build:

```bash
python3 scripts/smoke_deployed.py --base https://chart-viewer-api-rxrd.onrender.com
```

It uses only the standard library, so any Python 3 will run it — it does not
need the application's dependencies installed, and can be run from a laptop
that has never built this project.

That exercises one read per module and checks a code description resolves.
Add `--write --passphrase "<MASTER_ADMIN_PASSPHRASE>"` to make it perform a
real write and remove it again — **the half that matters**, because most of
this application degrades to silence rather than erroring, so reads can pass
against a database that cannot be written to. That is not hypothetical: it is
exactly how the entire E/M module was unwritable in production while every
read-only check passed.

**A run that could not perform the write fails.** If `--write` is asked for and
there is no chart to write against, or the chart lookup errors, the script
exits non-zero rather than reporting PASS. This is deliberate and was itself a
bug once: the script asked for a route that does not exist, read the 404 as an
empty environment, skipped the write silently and printed PASS — while nine
charts sat there. An alarm that goes green without checking is worse than no
alarm, so "could not check" is now a failure, not a skip.

## Also worth knowing

- `../CLAUDE.md` in the repository root is written for engineers picking the
  code up cold. It is blunter than these documents and covers the traps that
  have actually cost time.
- The API documents itself at `/docs` (OpenAPI) once it is running.
