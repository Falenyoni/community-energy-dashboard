# -*- coding: utf-8 -*-
"""
Demo-only endpoints backing the dashboard's "Simulate" button: start/stop
the background community simulation in app.demo_sim and poll its progress.
Not part of the ingestion/analytics API surface proper -- this exists to
drive a live presentation, not for production client use.
"""

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app import demo_sim
from app.database import get_db
from app.models import Site

router = APIRouter(prefix="/demo", tags=["demo"])

# The bundled dataset is exactly 30 real days, 2026-01-01 through
# 2026-01-30 (see live_demo.py). Anything from this date onward is a day
# the simulator never wrote, safe to generate/overwrite; anything earlier
# is real data the paper/thesis already reports numbers from.
EARLIEST_SAFE_DATE = "2026-01-31"


class SimulateRequest(BaseModel):
    site_ids: list[str] | None = None  # defaults to every "household" site
    date: str = EARLIEST_SAFE_DATE
    interval_seconds: float = 0.3
    recompute_every: int = 32


@router.post("/start")
def start_simulation(body: SimulateRequest, db: Session = Depends(get_db)):
    if body.date < EARLIEST_SAFE_DATE:
        return {
            "started": False,
            "detail": (
                f"{body.date} is inside the bundled 30-day dataset -- simulating it would "
                f"overwrite real data your paper/thesis already reports numbers from. "
                f"Pick a date on or after {EARLIEST_SAFE_DATE}."
            ),
        }

    site_ids = body.site_ids
    if not site_ids:
        site_ids = [
            row.site_id
            for row in db.query(Site).filter(Site.site_type == "household").order_by(Site.site_id).all()
        ]

    try:
        demo_sim.start(
            site_ids=site_ids,
            day=body.date,
            interval_seconds=body.interval_seconds,
            recompute_every=body.recompute_every,
        )
    except RuntimeError as exc:
        return {"started": False, "detail": str(exc)}

    return {"started": True, "site_ids": site_ids, "date": body.date}


@router.get("/status")
def simulation_status():
    return demo_sim.get_status()


@router.post("/stop")
def stop_simulation():
    demo_sim.stop()
    return {"stopping": True}
