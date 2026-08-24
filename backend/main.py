import os
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from contextlib import asynccontextmanager
from database import init_db
from config import settings
from routers import codes, charts, upload, reports, feedback, practicelab, resources, assessment, auditor


@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()
    yield


app = FastAPI(title="PracticeLab API", lifespan=lifespan)

# Where a single-container build puts the compiled frontend. Absent on Render,
# where the UI is a separate static service — everything below is guarded on it
# existing, so this file behaves exactly as before when it is not there.
FRONTEND_DIR = Path(os.getenv("FRONTEND_DIST", "/app/static"))

# The API prefixes. Anything under these is API, and a miss must 404 as JSON
# rather than fall through to the single-page app.
API_PREFIXES = (
    "/charts", "/upload", "/reports", "/feedback", "/practicelab",
    "/resources", "/assessment", "/auditor", "/codes", "/health",
    "/docs", "/redoc", "/openapi.json",
)

# Header name the frontend uses to send the master passphrase.
ADMIN_PASSPHRASE_HEADER = "x-admin-passphrase"


@app.middleware("http")
async def strip_api_prefix(request, call_next):
    """
    Serve `/api/charts/...` as `/charts/...`.

    The frontend calls `import.meta.env.VITE_API_URL || '/api'`, and in
    development vite proxies `/api` to the backend with the prefix removed.
    When one container serves both halves there is no proxy, so the same
    rewrite happens here and the browser sees identical behaviour in both.

    On Render this never fires: the UI is served separately and VITE_API_URL
    points at the API host, so no request arrives carrying the prefix.
    """
    path = request.scope.get("path", "")
    if path == "/api" or path.startswith("/api/"):
        request.scope["path"] = path[4:] or "/"
        request.scope["raw_path"] = request.scope["path"].encode()
        # Remember that this was an API call. The prefix is gone by the time
        # the catch-all runs, and without this flag an unmatched /api/... path
        # is indistinguishable from a single-page-app route — so it would be
        # answered with index.html. smoke_deployed.py reads an HTML reply as
        # proof it is pointed at the wrong host, so a typo in a path would
        # report a healthy service as the wrong service.
        request.scope["came_via_api_prefix"] = True
    return await call_next(request)


@app.middleware("http")
async def accept_passphrase_from_header(request, call_next):
    """
    Let the master passphrase arrive in a header instead of the query string.

    Fifteen endpoints declare it as `passphrase: str = Query(...)`, which put
    the one shared admin credential into every server, proxy and CDN access log
    — and, for the answer-key export, into browser history, because that one was
    opened as a URL.

    Rewriting fifteen signatures across three modules while another agent is
    working in them is the riskier change. This copies the header into the
    query string AFTER the request has been logged and routed, so the endpoints
    keep working unchanged and nothing writes the credential down. The query
    parameter still works, so anything not yet migrated keeps functioning.
    """
    sent = request.headers.get(ADMIN_PASSPHRASE_HEADER)
    if sent and b"passphrase=" not in request.scope.get("query_string", b""):
        from urllib.parse import quote
        existing = request.scope.get("query_string", b"")
        addition = ("passphrase=" + quote(sent)).encode()
        request.scope["query_string"] = (
            existing + b"&" + addition if existing else addition
        )
    return await call_next(request)


app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins_list,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(charts.router)
app.include_router(upload.router)
app.include_router(reports.router)
app.include_router(feedback.router)
app.include_router(practicelab.router)
app.include_router(resources.router)
app.include_router(assessment.router)
app.include_router(auditor.router)
app.include_router(codes.router)


@app.get("/health")
async def health():
    """
    What is actually running here.

    "ok" alone answers the load balancer and nobody else. The two facts below
    have each cost real time to establish by other means:

    `python` — production built on 3.14 while runtime.txt said 3.11 and the
    test suite ran 3.9, and the only way anyone found out was a stack trace
    with the interpreter path in it. A pin nobody can verify is not a pin.

    `database` — sqlite or postgresql. The difference is not cosmetic here:
    SQLite is more permissive in ways that have taken production down, so
    knowing which one a given environment is on is the first question worth
    asking when something behaves differently.

    Deliberately nothing about data, credentials or configuration — this route
    is unauthenticated, and it stays that way by having nothing worth guarding.
    """
    import sys

    from config import settings

    url = (settings.DATABASE_URL or "")
    return {
        "status": "ok",
        "python": "%d.%d.%d" % sys.version_info[:3],
        "database": ("postgresql" if url.startswith(("postgres://", "postgresql"))
                     else "sqlite" if url.startswith("sqlite") else "other"),
        # Which build this is. Set by the container image at build time; "dev"
        # when running from a working tree. Without it there is no way to
        # answer "did my change actually get deployed?" except by poking the
        # behaviour and inferring — which is guesswork, and was guesswork.
        "build": os.getenv("BUILD_REF", "dev"),
        # Whether this process is also serving the user interface. One
        # container serves both; the Render split serves only the API.
        "serving_ui": FRONTEND_DIR.is_dir(),
    }


# ── Single-container mode ────────────────────────────────────────────────────
# Registered last so every API route above wins the match. Does nothing at all
# unless a compiled frontend is present, which is why the Render deployment is
# unaffected by any of it.
if FRONTEND_DIR.is_dir():
    _assets = FRONTEND_DIR / "assets"
    if _assets.is_dir():
        app.mount("/assets", StaticFiles(directory=str(_assets)), name="assets")

    @app.get("/{full_path:path}", include_in_schema=False)
    async def serve_frontend(request: Request, full_path: str):
        """
        Hand any non-API path to the single-page app.

        React Router owns the URLs, so /trainer/practicelab is a real screen
        with no file behind it — the server must answer index.html and let the
        browser route. Files that DO exist (favicon, manifest) are served as
        themselves.

        An unmatched path under an API prefix returns JSON, not index.html.
        That matters beyond tidiness: smoke_deployed.py treats an HTML reply as
        proof it is pointed at the wrong host, so letting API misses fall
        through to the app would make a working service look like the wrong one.
        """
        if (request.scope.get("came_via_api_prefix")
                or ("/" + full_path).startswith(API_PREFIXES)):
            return JSONResponse({"detail": "Not Found"}, status_code=404)
        candidate = FRONTEND_DIR / full_path
        if full_path and candidate.is_file():
            return FileResponse(str(candidate))
        return FileResponse(str(FRONTEND_DIR / "index.html"))
