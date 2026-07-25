from collections import defaultdict

from fastapi import APIRouter, Depends
from sqlalchemy import extract, func
from sqlalchemy.orm import Session

from app.analytics.calculations import rank_devices
from app.database import get_db
from app.models import ComparisonResult, DailySummary, Reading, Site, SmartControllerChannel

router = APIRouter(prefix="/analytics", tags=["analytics"])


@router.get("/sites")
def list_sites(db: Session = Depends(get_db)):
    """All sites, for a site-selector control."""
    rows = db.query(Site).order_by(Site.site_id).all()
    return [
        {"site_id": row.site_id, "anonymised_label": row.anonymised_label, "site_type": row.site_type}
        for row in rows
    ]


@router.get("/ranking")
def device_ranking(site_id: str | None = None, db: Session = Depends(get_db)):
    """Device-level ranking: total kWh summed across all recorded days, highest first.

    Optionally scoped to one site via ?site_id=..., since the dashboard shows
    ranking per selected site rather than pooled across the whole community.
    """
    query = db.query(DailySummary.device_id, DailySummary.total_kwh)
    if site_id is not None:
        query = query.join(
            SmartControllerChannel, SmartControllerChannel.device_id == DailySummary.device_id
        ).filter(SmartControllerChannel.site_id == site_id)

    totals: dict[str, float] = {}
    for device_id, total_kwh in query.all():
        totals[device_id] = totals.get(device_id, 0.0) + float(total_kwh)
    ranked = rank_devices(totals)
    return [{"device_id": device_id, "total_kwh": round(total, 4)} for device_id, total in ranked]


@router.get("/site-summary/{site_id}")
def site_daily_summary(site_id: str, db: Session = Depends(get_db)):
    """Per-day total kWh, peak kW and cost, summed across all of a site's devices."""
    rows = (
        db.query(DailySummary)
        .join(SmartControllerChannel, SmartControllerChannel.device_id == DailySummary.device_id)
        .filter(SmartControllerChannel.site_id == site_id)
        .order_by(DailySummary.date)
        .all()
    )

    by_day: dict[str, dict] = {}
    for row in rows:
        day = row.date.date().isoformat()
        entry = by_day.setdefault(day, {"date": day, "total_kwh": 0.0, "peak_power_kw": 0.0, "cost_estimate": 0.0})
        entry["total_kwh"] += float(row.total_kwh)
        entry["cost_estimate"] += float(row.cost_estimate or 0)
        entry["peak_power_kw"] = max(entry["peak_power_kw"], float(row.peak_power_kw or 0))

    return [
        {**entry, "total_kwh": round(entry["total_kwh"], 4), "cost_estimate": round(entry["cost_estimate"], 2)}
        for entry in sorted(by_day.values(), key=lambda e: e["date"])
    ]


@router.get("/heatmap/{site_id}")
def hourly_heatmap(site_id: str, db: Session = Depends(get_db)):
    """
    Average power (kW) by day and hour-of-day for a site, across all its
    devices — the grid the hourly-usage-pattern heatmap renders. Computed
    directly from valid Reading rows (DailySummary only stores daily
    totals, not an hourly breakdown).
    """
    # Explicitly convert to UTC before extracting date/hour -- func.date()
    # and extract() otherwise use the DB session's timezone setting, which
    # differs between a local Postgres install (defaults to system
    # timezone) and Render's (defaults to UTC), shifting readings across
    # day/hour boundaries depending on which database is active.
    utc_timestamp = func.timezone("UTC", Reading.timestamp)
    rows = (
        db.query(
            func.date(utc_timestamp).label("day"),
            extract("hour", utc_timestamp).label("hour"),
            func.avg(Reading.power_kw).label("avg_power_kw"),
        )
        .join(SmartControllerChannel, SmartControllerChannel.device_id == Reading.device_id)
        .filter(SmartControllerChannel.site_id == site_id, Reading.quality_flag == "valid")
        .group_by("day", "hour")
        .order_by("day", "hour")
        .all()
    )
    return [
        {"date": row.day.isoformat(), "hour": int(row.hour), "avg_power_kw": round(float(row.avg_power_kw), 4)}
        for row in rows
    ]


@router.get("/comparison/{site_id}")
def site_comparison(site_id: str, db: Session = Depends(get_db)):
    """Comparison results (baseline, peer average, ratio, status) for one site, by day."""
    rows = (
        db.query(ComparisonResult)
        .filter(ComparisonResult.site_id == site_id)
        .order_by(ComparisonResult.period)
        .all()
    )
    return [
        {
            "period": row.period,
            "baseline_kwh": float(row.baseline_kwh) if row.baseline_kwh is not None else None,
            "group_average_kwh": float(row.group_average_kwh) if row.group_average_kwh is not None else None,
            "ratio": float(row.ratio) if row.ratio is not None else None,
            "status_flag": row.status_flag,
        }
        for row in rows
    ]


@router.get("/daily-summary/{device_id}")
def device_daily_summary(device_id: str, db: Session = Depends(get_db)):
    """Per-day total kWh, peak kW and estimated cost for one device."""
    rows = (
        db.query(DailySummary)
        .filter(DailySummary.device_id == device_id)
        .order_by(DailySummary.date)
        .all()
    )
    return [
        {
            "date": row.date.date().isoformat(),
            "total_kwh": float(row.total_kwh),
            "peak_power_kw": float(row.peak_power_kw) if row.peak_power_kw is not None else None,
            "cost_estimate": float(row.cost_estimate) if row.cost_estimate is not None else None,
        }
        for row in rows
    ]
