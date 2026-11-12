from collections import defaultdict
from datetime import date as date_type
from datetime import timedelta

from fastapi import APIRouter, Depends
from sqlalchemy import extract, func
from sqlalchemy.orm import Session

from app.analytics.calculations import (
    classify_status,
    peer_group_average_kwh,
    rank_devices,
    relative_ratio,
)
from app.database import get_db
from app.models import ComparisonResult, DailySummary, Reading, Site, SmartControllerChannel

router = APIRouter(prefix="/analytics", tags=["analytics"])

# "Day" / "week" / "month" toggles on the dashboard are a trailing window
# ending at the latest available date, not calendar weeks/months -- the
# bundled dataset is one 30-ish-day run, so a rolling window is simpler and
# avoids calendar-boundary edge cases for a demo of this size.
PERIOD_WINDOW_DAYS = {"day": 1, "week": 7, "month": 30}


@router.get("/sites")
def list_sites(site_type: str | None = None, db: Session = Depends(get_db)):
    """
    Sites, for a site-selector control. Pass site_type to scope to one
    community (e.g. "household" for the simulated dataset, excluding the
    separate "household_real_meter" validation sites) -- omit it to list
    everything.
    """
    query = db.query(Site)
    if site_type is not None:
        query = query.filter(Site.site_type == site_type)
    rows = query.order_by(Site.site_id).all()
    return [
        {"site_id": row.site_id, "anonymised_label": row.anonymised_label, "site_type": row.site_type}
        for row in rows
    ]


@router.get("/ranking")
def device_ranking(site_id: str | None = None, period: str = "day", db: Session = Depends(get_db)):
    """Device-level ranking: total kWh over the selected window, highest first.

    Also reports each device's peak power (kW) — the highest instantaneous draw
    seen in any single day in that window — alongside total energy. Total kWh
    alone can't tell apart "low power, always on" from "high power, brief
    use"; peak_power_kw does.

    period is "day" (the latest day only, the previous default), "week" (last
    7 days) or "month" (last 30 days), a trailing window ending at the
    latest date with data -- see PERIOD_WINDOW_DAYS.

    Optionally scoped to one site via ?site_id=..., since the dashboard shows
    ranking per selected site rather than pooled across the whole community.
    """
    query = db.query(DailySummary.device_id, DailySummary.date, DailySummary.total_kwh, DailySummary.peak_power_kw)
    if site_id is not None:
        query = query.join(
            SmartControllerChannel, SmartControllerChannel.device_id == DailySummary.device_id
        ).filter(SmartControllerChannel.site_id == site_id)

    rows = query.all()
    if not rows:
        return []

    window_days = PERIOD_WINDOW_DAYS.get(period, 1)
    max_date = max(row.date for row in rows)
    cutoff = max_date - timedelta(days=window_days - 1)

    totals: dict[str, float] = {}
    peak_power: dict[str, float] = {}
    for device_id, date, total_kwh, peak_power_kw in rows:
        if date < cutoff:
            continue
        totals[device_id] = totals.get(device_id, 0.0) + float(total_kwh)
        if peak_power_kw is not None:
            peak_power[device_id] = max(peak_power.get(device_id, 0.0), float(peak_power_kw))

    ranked = rank_devices(totals)
    return [
        {
            "device_id": device_id,
            "total_kwh": round(total, 4),
            "peak_power_kw": round(peak_power[device_id], 4) if device_id in peak_power else None,
        }
        for device_id, total in ranked
    ]


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


@router.get("/interval/{site_id}")
def site_interval_readings(site_id: str, date: date_type, db: Session = Depends(get_db)):
    """
    Raw 15-minute readings for one site on one calendar day, per channel --
    the within-day load curve that DailySummary (one total per day) and the
    hourly heatmap (averaged across the whole dataset) both lose.
    """
    utc_timestamp = func.timezone("UTC", Reading.timestamp)
    rows = (
        db.query(
            utc_timestamp.label("ts"),
            SmartControllerChannel.controller_channel.label("channel"),
            Reading.power_kw,
        )
        .join(SmartControllerChannel, SmartControllerChannel.device_id == Reading.device_id)
        .filter(
            SmartControllerChannel.site_id == site_id,
            Reading.quality_flag == "valid",
            func.date(utc_timestamp) == date,
        )
        .order_by(utc_timestamp)
        .all()
    )

    by_time: dict[str, dict] = {}
    for row in rows:
        entry = by_time.setdefault(row.ts.strftime("%H:%M"), {"time": row.ts.strftime("%H:%M")})
        entry[row.channel] = round(float(row.power_kw), 4) if row.power_kw is not None else 0.0

    return sorted(by_time.values(), key=lambda e: e["time"])


@router.get("/comparison/{site_id}")
def site_comparison(site_id: str, period: str = "day", db: Session = Depends(get_db)):
    """
    Comparison results (baseline, peer average, ratio, status) for one site.

    period="day" (default) returns the persisted per-day ComparisonResult
    rows exactly as before. period="week"/"month" instead computes a single
    trailing-window comparison on the fly: each site's own DailySummary
    total_kwh is summed over the window, then the same peer-group-average /
    ratio / status formulas (app.analytics.calculations) are applied to
    those period totals instead of single-day totals. Not persisted --
    recomputed per request, since the window end a dashboard polls against
    changes continuously during a live simulation.
    """
    if period not in ("week", "month"):
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

    site_type = db.query(Site.site_type).filter(Site.site_id == site_id).scalar() or "household"
    peer_site_ids = [row.site_id for row in db.query(Site.site_id).filter(Site.site_type == site_type).all()]
    device_to_site = {
        row.device_id: row.site_id
        for row in db.query(SmartControllerChannel).filter(SmartControllerChannel.site_id.in_(peer_site_ids))
    }
    rows = (
        db.query(DailySummary.device_id, DailySummary.date, DailySummary.total_kwh)
        .filter(DailySummary.device_id.in_(device_to_site.keys()))
        .all()
    )
    if not rows:
        return []

    window_days = PERIOD_WINDOW_DAYS[period]
    max_date = max(row.date for row in rows)
    cutoff = max_date - timedelta(days=window_days - 1)

    site_totals: dict[str, float] = defaultdict(float)
    for device_id, date, total_kwh in rows:
        if date < cutoff:
            continue
        site_totals[device_to_site[device_id]] += float(total_kwh)

    this_total = site_totals.get(site_id)
    if this_total is None:
        return []

    peer_avg = peer_group_average_kwh([t for sid, t in site_totals.items() if sid != site_id])
    ratio = relative_ratio(this_total, peer_avg)

    return [
        {
            "period": f"{period} ending {max_date.date().isoformat()}",
            "baseline_kwh": None,
            "group_average_kwh": round(peer_avg, 4) if peer_avg is not None else None,
            "ratio": ratio,
            "status_flag": classify_status(ratio),
        }
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
