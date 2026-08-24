# Running PracticeLab as a container

The repository root holds a `Dockerfile` that packages the entire application —
the API and the user interface — into a single image. This document is for the
team that will run it.

Everything below has been executed, not merely written down: the image builds
clean, starts, serves the application, and reports the facts quoted here.

---

## What the image is, and is not

**Inside:** Python 3.11.9, the fourteen backend packages, and the compiled
front end. Nothing else is required on the host.

**Not inside, deliberately:** the database and the chart images. Both are
external services and stay that way — a container is disposable and your data
is not. The image is stateless and can be replaced, scaled or rolled back
freely.

**Not inside either:** Node. The front end is compiled during the build, in a
stage that is discarded. The 172 MB of build tooling never reaches the server.

Built size is about **523 MB**. It runs as an unprivileged user, `uid 10001`,
and listens on **port 8000**.

---

## What you need first

| | |
|---|---|
| A container runtime | Docker, Podman, Kubernetes, OpenShift — anything that runs an OCI image |
| **PostgreSQL 15 or later** | Restore the supplied dump into it first. See `DATABASE_MIGRATION_RUNBOOK.md` |
| **S3-compatible object storage** | Holds the chart page images. See `DATA_STORAGE_MODEL.md` for the options |

The application will start without valid storage credentials and will look
entirely healthy — charts list, batches open, analytics compute — while every
chart image is broken. Configure storage before accepting the environment, and
verify by opening a chart, not by seeing one in a list.

---

## 1. Build

From the repository root:

```bash
docker build \
  --platform linux/amd64 \
  --build-arg BUILD_REF=$(git rev-parse --short HEAD) \
  -t practicelab:1.0 .
```

`--platform linux/amd64` matters if the image is built on an Apple Silicon Mac
and run on ordinary x86 servers; omit it when building on the target
architecture.

`BUILD_REF` is stamped into the image and reported by `/health`. It is what
makes "which version is running?" a question with an answer. Any string will
do — a commit hash, a release number — but set it to something meaningful.

---

## 2. Configure

Nine environment variables. **Six have no default and the application will
refuse to start without them**, which is intentional: a silent start on
half a configuration is worse than a clear failure.

| Variable | Required | Notes |
|---|---|---|
| `DATABASE_URL` | **yes** | `postgresql://user:pass@host:5432/practicelab`. The `postgres://` and `postgresql+asyncpg://` forms are also accepted and normalised |
| `MASTER_ADMIN_PASSPHRASE` | **yes** | The single shared credential gating retire, delete, force-close and the question bank. Treat as a secret |
| `STORAGE_ENDPOINT_URL` | **yes** | Object storage endpoint |
| `STORAGE_ACCESS_KEY` | **yes** | |
| `STORAGE_SECRET_KEY` | **yes** | |
| `STORAGE_BUCKET_NAME` | **yes** | |
| `STORAGE_PUBLIC_URL` | no | Required to be present but currently unread. Any value |
| `CORS_ORIGINS` | no | **Not needed in this deployment.** One container serves both halves, so the browser never makes a cross-origin request |
| `FRONTEND_URL` | no | Used only in generated links |

Keep them in a file rather than on the command line, so they stay out of shell
history and process listings:

```bash
docker run -d --name practicelab \
  -p 8000:8000 \
  --env-file /etc/practicelab/practicelab.env \
  --restart unless-stopped \
  practicelab:1.0
```

---

## 3. What happens on first start

The application runs its own schema migrations on **every** start, not only the
first. There is no separate migration step to schedule and no Alembic to
install.

Migrations are additive — they create tables and add columns, and never drop
or rewrite. An older image will therefore generally run against a newer schema,
which is what makes rollback safe.

They are also **non-fatal**: a migration that fails is logged and startup
continues. After any upgrade, check the logs for:

```
Migration DDL failed
```

On a correctly configured database this must not appear.

One ordering rule matters. If the `assessment_questions` table is empty at
startup, the application seeds sample questions. So **restore the database
first, then start the container.** Starting first and restoring afterwards
fails on duplicate keys. If that has already happened, drop and recreate the
database before restoring.

---

## 4. Verify

### The quick check

```bash
curl -s http://localhost:8000/health
```

```json
{"status":"ok","python":"3.11.9","database":"postgresql","build":"51ba232","serving_ui":true}
```

Read all five fields:

- `python` — must be **3.11.x**. Anything else means the image was not built
  from this Dockerfile.
- `database` — must be **postgresql**. If it says `sqlite`, `DATABASE_URL` did
  not reach the container and the application is running on a throwaway file.
  It will appear to work and will lose everything on restart.
- `build` — the `BUILD_REF` you set. This is how you confirm the version you
  intended is the version running.
- `serving_ui` — `true` means this process is serving the interface as well as
  the API.

`/health` reads configuration, not the database. It stays green while the
database is unreachable, so it is a liveness check and not a readiness one.
The image's built-in `HEALTHCHECK` polls this endpoint.

### The real check

`/health` proves the process is up. It does not prove the application works.
Use the supplied smoke script, which exercises the deployed service:

```bash
python3 scripts/smoke_deployed.py --base http://localhost:8000 \
  --write --passphrase 'YOUR_PASSPHRASE'
```

It uses only the Python standard library, so it runs on a locked-down host
with nothing installed.

**Use `--write`.** This application degrades to silence rather than erroring,
so read-only checks pass against a database that cannot be written to. That is
not hypothetical — it is exactly how an entire module was unwritable in the
hosted environment while every read-only check reported healthy. The write
check stores one record and removes it again. A run that is asked for `--write`
and cannot perform one now fails rather than skipping.

### What a misconfigured start actually looks like

Worth seeing once, because none of it is an error message. A container started
without a real `DATABASE_URL` and against an environment where the code sets
were never loaded reports this:

```
  ok   running the pinned Python (3.11)
  FAIL talking to PostgreSQL — database reports sqlite
  ok   charts
  ok   practicelab batches
  ok   auditor batches
  FAIL J18.9 has a description — got 200 {'descriptions': {}, ...}

12 checks, 2 failed
```

Every read path passes. The application is up, serving, and answering — and it
is writing to a temporary file that vanishes on restart, while every code
description silently renders as blank. Neither shows up as an error anywhere in
the interface. This is what the script is for.

### Then look at it

Open the address in a browser and confirm the interface loads, then **open a
chart and confirm the page image renders**. A chart appearing in a list proves
the database; only a rendered page proves the object storage.

---

## 5. Updating

This is the routine for a new version:

```bash
docker build --platform linux/amd64 \
  --build-arg BUILD_REF=$(git rev-parse --short HEAD) \
  -t practicelab:1.1 .
docker stop practicelab && docker rm practicelab
docker run -d --name practicelab -p 8000:8000 \
  --env-file /etc/practicelab/practicelab.env \
  --restart unless-stopped practicelab:1.1
curl -s http://localhost:8000/health      # confirm `build` is the new one
```

No database step. Schema changes travel with the image and apply themselves at
startup.

**Rolling back** is running the previous tag. Because migrations only add,
the older application normally runs against the newer schema — but validate it
rather than assuming, and keep the previous image tag until the new one has
been accepted.

---

## Notes for a platform team

**Base image.** If your policy requires an approved base, change the two `FROM`
lines. The rest of the file is unaffected. The build stage needs Node 20 and
the runtime stage needs Python 3.11 — the Python version is not negotiable;
the code is tested only on 3.9 and 3.11 and has been broken by 3.14.

**Non-root.** Already the case, `uid 10001`. No capabilities are required and
the filesystem can be mounted read-only apart from `/tmp`.

**Replicas.** The container holds no session state, so it scales horizontally.
Every replica runs the startup migrations; they are idempotent and guarded, so
this is safe, though staggering starts avoids noise in the logs.

**Reverse proxy.** Nothing special is required. The application serves the
interface and the API from one origin, so there is no path rewriting to
configure — proxy everything to port 8000.

**Reference code sets.** ICD-10-CM, ICD-10-PCS and HCPCS descriptions are
loaded by hand, once, with `scripts/ingest_code_sets.py --write` — about
186,000 rows fetched from cms.gov. Nothing calls it automatically, so that a
CMS outage cannot become a failed deployment. Everything that reads it degrades
to silence, so an environment where it was never run looks identical to one
where the feature does not exist. `GET /codes/status` reports what is loaded,
and `--from-dir` reads the files from disk where there is no route to cms.gov.
