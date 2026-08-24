# PracticeLab — one image containing both halves of the application.
#
# On Render the API and the UI are two services. Internally they are one
# container: the frontend is compiled during the build and served by the same
# process that serves the API, so the receiving team installs nothing, builds
# nothing, and runs one thing.
#
#   docker build -t practicelab:1 --build-arg BUILD_REF=$(git rev-parse --short HEAD) .
#   docker run -p 8000:8000 --env-file practicelab.env practicelab:1
#
# What this image is NOT: it holds no database and no chart images. Both are
# external and stay that way — a container is disposable and your data is not.

# ── Stage 1: compile the frontend ────────────────────────────────────────────
# Node exists only here. It is not in the final image, so the 172MB of build
# tooling never reaches the server that runs this.
FROM node:20-slim AS frontend

WORKDIR /build
# Copied first and separately: this layer is rebuilt only when the dependency
# list changes, not on every source edit.
COPY frontend/package*.json ./
RUN npm ci --no-audit --no-fund

COPY frontend/ ./
# No VITE_API_URL: the app falls back to /api, which the backend rewrites. One
# origin, so there is no CORS to configure and no host name compiled into the
# bundle — the same image runs at any internal address.
RUN npm run build

# ── Stage 2: the application ─────────────────────────────────────────────────
# The interpreter is part of the artifact rather than part of the host. This is
# the pin that actually holds: runtime.txt was ignored once and production
# built on 3.14 while the suite ran on 3.9, and nothing said so.
FROM python:3.11.9-slim AS app

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1 \
    FRONTEND_DIST=/app/static

WORKDIR /app

COPY backend/requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt

COPY backend/ ./
COPY --from=frontend /build/dist /app/static

# Recorded at build time and reported by /health, so "which version is running"
# is a question with an answer rather than an inference from behaviour.
ARG BUILD_REF=unknown
ENV BUILD_REF=${BUILD_REF}

# Not root. Many internal platforms refuse an image that runs as root, and
# there is no reason for this one to.
RUN useradd --create-home --uid 10001 practicelab \
    && chown -R practicelab:practicelab /app
USER practicelab

EXPOSE 8000

# Stdlib only, so it adds nothing to the image. Reports unhealthy while the
# process is up but not yet serving, which is what a rolling deploy needs.
HEALTHCHECK --interval=30s --timeout=5s --start-period=40s --retries=3 \
    CMD python -c "import urllib.request,sys; sys.exit(0 if urllib.request.urlopen('http://127.0.0.1:8000/health',timeout=4).status==200 else 1)"

CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]
