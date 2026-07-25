"""
CLI analytics computation: reads validated Reading rows and computes
DailySummary (per device/day) and ComparisonResult (per site/day) using the
pure formulas in app.analytics.calculations.

Usage:
    python -m app.analytics.compute

Full rebuild each run — existing DailySummary/ComparisonResult rows are
cleared and recomputed from current Reading data, rather than incrementally
upserted. Simpler to reason about, and always consistent with whatever has
been ingested so far.
"""

from collections import defaultdict
from datetime import date, datetime, time, timezone

from sqlalchemy.orm import Session

from app.analytics.calculations import (
    baseline_kwh,
    classify_status,
    daily_total_kwh,
    estimate_cost,
    peak_power_kw,
    peer_group_average_kwh,
    relative_ratio,
)
from app.database import SessionLocal
from app.models import ComparisonResult, DailySummary, Reading, SmartControllerChannel


def load_valid_readings(db: Session) -> list[Reading]:
    # Only "valid"-flagged readings feed analytics — duplicates/out-of-range/
    # missing rows would silently distort totals otherwise (Objective 2).
    return (
        db.query(Reading)
        .filter(Reading.quality_flag == "valid")
        .order_by(Reading.device_id, Reading.timestamp)
        .all()
    )


def compute_daily_summaries(db: Session, readings: list[Reading]) -> dict[tuple[str, date], float]:
    """
    Groups valid readings by (device_id, calendar day), writes one
    DailySummary row per group, and returns {(device_id, day): total_kwh}
    for reuse when building site-level daily totals below.
    """
    grouped: dict[tuple[str, date], list[Reading]] = defaultdict(list)
    for reading in readings:
        key = (reading.device_id, reading.timestamp.date())
        grouped[key].append(reading)

    device_day_totals: dict[tuple[str, date], float] = {}

    for (device_id, day), day_readings in grouped.items():
        # Numeric columns return Decimal, not float — convert at the DB
        # boundary so the pure calculation functions stay plain-float,
        # matching what their unit tests assume.
        energies = [
            float(r.energy_kwh_interval) for r in day_readings if r.energy_kwh_interval is not None
        ]
        powers = [float(r.power_kw) for r in day_readings if r.power_kw is not None]

        total_kwh = daily_total_kwh(energies)
        peak_kw = peak_power_kw(powers)
        cost = estimate_cost(total_kwh)

        device_day_totals[(device_id, day)] = total_kwh

        db.add(
            DailySummary(
                device_id=device_id,
                date=datetime.combine(day, time.min, tzinfo=timezone.utc),
                total_kwh=total_kwh,
                peak_power_kw=peak_kw,
                cost_estimate=cost,
            )
        )

    return device_day_totals


def compute_site_day_totals(
    db: Session, device_day_totals: dict[tuple[str, date], float]
) -> dict[tuple[str, date], float]:
    """Sums device-day totals up to site-day totals, using each device's site_id."""
    device_to_site = {
        channel.device_id: channel.site_id for channel in db.query(SmartControllerChannel).all()
    }

    site_day_totals: dict[tuple[str, date], float] = defaultdict(float)
    for (device_id, day), total in device_day_totals.items():
        site_id = device_to_site.get(device_id)
        if site_id is None:
            continue
        site_day_totals[(site_id, day)] += total

    return {key: round(value, 4) for key, value in site_day_totals.items()}


def compute_comparison_results(db: Session, site_day_totals: dict[tuple[str, date], float]) -> None:
    """
    For each site+day: baseline = mean of that same site's own prior days
    (self-comparison); peer group = mean of all other sites' totals for
    that same calendar day (community comparison). ratio/status are
    computed against the peer group, per the design decision documented in
    CODE_WALKTHROUGH.md.
    """
    by_site: dict[str, list[tuple[date, float]]] = defaultdict(list)
    by_day: dict[date, list[tuple[str, float]]] = defaultdict(list)
    for (site_id, day), total in site_day_totals.items():
        by_site[site_id].append((day, total))
        by_day[day].append((site_id, total))

    for site_id in by_site:
        by_site[site_id].sort(key=lambda item: item[0])

    for site_id, day_totals in by_site.items():
        for i, (day, total) in enumerate(day_totals):
            history = [t for _, t in day_totals[:i]]  # prior days only, not today
            baseline = baseline_kwh(history)

            peers = [t for other_site, t in by_day[day] if other_site != site_id]
            peer_avg = peer_group_average_kwh(peers)

            ratio = relative_ratio(total, peer_avg)
            status = classify_status(ratio)

            db.add(
                ComparisonResult(
                    site_id=site_id,
                    period=day.isoformat(),
                    baseline_kwh=baseline,
                    group_average_kwh=peer_avg,
                    ratio=ratio,
                    status_flag=status,
                )
            )


def run() -> None:
    db = SessionLocal()
    try:
        print("Clearing existing DailySummary/ComparisonResult rows for a full rebuild...")
        db.query(DailySummary).delete()
        db.query(ComparisonResult).delete()

        print("Loading valid readings...")
        readings = load_valid_readings(db)
        print(f"  {len(readings):,} valid readings loaded")

        print("Computing daily summaries (per device/day: total kWh, peak kW, cost)...")
        device_day_totals = compute_daily_summaries(db, readings)
        print(f"  {len(device_day_totals):,} device-day summaries")

        print("Computing site-day totals...")
        site_day_totals = compute_site_day_totals(db, device_day_totals)
        print(f"  {len(site_day_totals):,} site-day totals")

        print("Computing comparison results (baseline + peer-group + ratio)...")
        compute_comparison_results(db, site_day_totals)

        db.commit()
        print("Done.")
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


if __name__ == "__main__":
    run()
