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
    return {"status": "ok"}
