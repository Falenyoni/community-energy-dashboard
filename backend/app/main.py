from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware

from app.config import get_settings
from app.database import check_db_connection

settings = get_settings()

app = FastAPI(
    title="Community Energy Monitoring Dashboard API",
    description="Ingestion, validation and comparative analytics for simulated smart circuit controller data.",
    version="0.1.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins_list,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/health")
def health():
    return {"status": "ok"}


@app.get("/health/db")
def health_db():
    try:
        check_db_connection()
    except Exception as exc:
        raise HTTPException(status_code=503, detail=f"Database unreachable: {exc}")
    return {"status": "ok", "database": "connected"}
