from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.analytics.calculations import rank_devices
from app.database import get_db
from app.models import ComparisonResult, DailySummary

router = APIRouter(prefix="/analytics", tags=["analytics"])


@router.get("/ranking")
def device_ranking(db: Session = Depends(get_db)):
    """Device-level ranking: total kWh summed across all recorded days, highest first."""
    rows = db.query(DailySummary.device_id, DailySummary.total_kwh).all()
    totals: dict[str, float] = {}
    for device_id, total_kwh in rows:
        totals[device_id] = totals.get(device_id, 0.0) + float(total_kwh)
    ranked = rank_devices(totals)
    return [{"device_id": device_id, "total_kwh": round(total, 4)} for device_id, total in ranked]


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
