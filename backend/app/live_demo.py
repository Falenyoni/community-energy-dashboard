# -*- coding: utf-8 -*-
"""
Live demo: streams one simulated day's readings into the database at a
presentable pace, one 15-minute interval at a time, so an audience can watch
the single-day load curve (frontend "Single-day load curve" section) build
up in near-real-time rather than seeing a day's worth of data appear all at
once from a bulk CSV ingest.

Reuses the exact per-channel power functions from data-generator/generate.py
so the live-streamed shape matches the rest of the simulated dataset.

Writes to an existing site's NEW day (default: 2026-01-31, the day right
after the bundled 30-day dataset) rather than creating a new site — keeps
the "ten simulated households" count the evaluation/thesis numbers rely on
unchanged. Safe to re-run: clears any previous run's readings for the same
site/date first.

Usage:
    python -m app.live_demo [--site-id HOUSE-001] [--date 2026-01-31]
                             [--interval-seconds 0.5] [--seed 42]
                             [--compute-after]

--compute-after additionally runs `python -m app.analytics.compute` once the
day finishes, so the Daily consumption trend / KPI tiles (which read from
DailySummary, not raw readings) also pick up the new day. The single-day
load curve itself reads raw Reading rows directly and updates live without
this flag.
"""

import argparse
import os
import random
import subprocess
import sys
import time
from datetime import datetime, timedelta, timezone

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "data-generator"))
from generate import (  # noqa: E402
    CHANNELS,
    CHANNEL_FUNCS,
    INTERVAL_MINUTES,
    INTERVALS_PER_DAY,
    POWER_FACTOR,
    PROFILE_MULTIPLIER,
    USAGE_PROFILES,
    WEEKEND_BOOST_CHANNELS,
    derive_current,
)

from app.database import SessionLocal
from app.models import Reading, SmartControllerChannel

sys.path.pop(0)


def site_profile(site_id: str) -> str:
    # Same assignment rule as generate.py: USAGE_PROFILES[site_index % 3],
    # where site_index is 0-based from the "HOUSE-NNN" suffix.
    site_index = int(site_id.rsplit("-", 1)[-1]) - 1
    return USAGE_PROFILES[site_index % len(USAGE_PROFILES)]


def last_cumulative(db, device_id: str) -> float:
    row = (
        db.query(Reading.cumulative_energy_kwh)
        .filter(Reading.device_id == device_id)
        .order_by(Reading.timestamp.desc())
        .first()
    )
    return float(row[0]) if row and row[0] is not None else 0.0


def clear_existing(db, site_id: str, day_start: datetime, day_end: datetime) -> None:
    device_ids = [
        device_id
        for (device_id,) in db.query(SmartControllerChannel.device_id).filter(
            SmartControllerChannel.site_id == site_id
        )
    ]
    deleted = (
        db.query(Reading)
        .filter(Reading.device_id.in_(device_ids), Reading.timestamp >= day_start, Reading.timestamp < day_end)
        .delete(synchronize_session=False)
    )
    db.commit()
    if deleted:
        print(f"Cleared {deleted} readings from a previous run of this demo day.")


def run(site_id: str, day: str, interval_seconds: float, seed: int, compute_after: bool) -> None:
    profile = site_profile(site_id)
    base_multiplier = PROFILE_MULTIPLIER[profile]
    day_start = datetime.strptime(day, "%Y-%m-%d").replace(tzinfo=timezone.utc)
    day_end = day_start + timedelta(days=1)

    db = SessionLocal()
    channels = {
        row.controller_channel: row.device_id
        for row in db.query(SmartControllerChannel).filter(SmartControllerChannel.site_id == site_id)
        if row.controller_channel in CHANNELS
    }
    missing = [ch for ch in CHANNELS if ch not in channels]
    if missing:
        print(f"ERROR: {site_id} is missing channel(s) {missing} -- pick a site already in the dataset.")
        db.close()
        return

    clear_existing(db, site_id, day_start, day_end)
    cumulative = {ch: last_cumulative(db, device_id) for ch, device_id in channels.items()}
    rngs = {ch: random.Random(seed * 1000 + i) for i, ch in enumerate(CHANNELS)}

    print(f"Streaming {site_id} ({profile}-usage profile) for {day}, one 15-minute interval every "
          f"{interval_seconds}s ({INTERVALS_PER_DAY} intervals, ~{INTERVALS_PER_DAY * interval_seconds:.0f}s total).")
    print("Watch it on the dashboard: select this house, open 'Single-day load curve', pick this date.\n")

    for interval_index in range(INTERVALS_PER_DAY):
        dt = day_start + timedelta(minutes=interval_index * INTERVAL_MINUTES)
        total_power = 0.0

        for channel in CHANNELS:
            device_id = channels[channel]
            rng = rngs[channel]
            multiplier = base_multiplier
            if dt.weekday() >= 5 and channel in WEEKEND_BOOST_CHANNELS:
                multiplier *= 1.15

            power_kw, switching_state = CHANNEL_FUNCS[channel](dt, rng, multiplier)
            voltage_v = round(rng.uniform(225, 235), 1)
            current_a = derive_current(power_kw, voltage_v, channel)
            energy_kwh_interval = round(power_kw * (INTERVAL_MINUTES / 60), 5)
            cumulative[channel] = round(cumulative[channel] + energy_kwh_interval, 4)
            total_power += power_kw

            db.add(
                Reading(
                    reading_id=f"{device_id}_{dt.strftime('%Y%m%dT%H%M')}",
                    device_id=device_id,
                    timestamp=dt,
                    voltage_v=voltage_v,
                    current_a=current_a,
                    power_kw=power_kw,
                    energy_kwh_interval=energy_kwh_interval,
                    cumulative_energy_kwh=cumulative[channel],
                    switching_state=switching_state,
                    quality_flag="valid",
                )
            )

        db.commit()
        print(f"  {dt.strftime('%H:%M')}  total power {total_power:.3f} kW  "
              f"({interval_index + 1}/{INTERVALS_PER_DAY})")
        time.sleep(interval_seconds)

    db.close()
    print(f"\nDone -- {INTERVALS_PER_DAY} intervals streamed for {site_id} on {day}.")

    if compute_after:
        print("\nRecomputing DailySummary/ComparisonResult so the daily trend and KPI tiles pick this day up...")
        subprocess.run([sys.executable, "-m", "app.analytics.compute"], check=True)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--site-id", default="HOUSE-001", help="Existing site to stream a new day into")
    parser.add_argument("--date", default="2026-01-31", help="Calendar day to stream (YYYY-MM-DD)")
    parser.add_argument("--interval-seconds", type=float, default=0.5, help="Pause between each 15-minute step")
    parser.add_argument("--seed", type=int, default=42, help="Random seed")
    parser.add_argument(
        "--compute-after",
        action="store_true",
        help="Also rebuild DailySummary/ComparisonResult once the day finishes",
    )
    args = parser.parse_args()
    run(args.site_id, args.date, args.interval_seconds, args.seed, args.compute_after)


if __name__ == "__main__":
    main()
