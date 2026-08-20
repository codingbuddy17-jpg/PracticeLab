from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from contextlib import asynccontextmanager
from database import init_db
from config import settings
from routers import codes, charts, upload, reports, feedback, practicelab, resources, assessment, auditor


@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()
    yield


app = FastAPI(title="PracticeLab API", lifespan=lifespan)

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
    }
