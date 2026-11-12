# -*- coding: utf-8 -*-
"""
Background community simulation for the live demo "Simulate" button: streams
one simulated day's readings for a chosen set of sites at a presentable pace,
one 15-minute interval at a time, and periodically re-runs the full analytics
recompute (app.analytics.compute.run) so DailySummary/ComparisonResult, and
therefore the dashboard's KPI tiles, community-comparison percentages, and
the admin ranking table, visibly update while it runs.

Runs in a background thread so it doesn't block the API from serving other
requests while a day streams in. Only one simulation can run at a time.

A single site_id list covers both "household" and "community" demo framing
at once: pass just one site to simulate a single household (same effect as
live_demo.py, which remains separately available for that), or the whole
household site list to simulate the community and watch peer comparisons
shift as each site's data lands.

compute.run() does a full rebuild of DailySummary/ComparisonResult across
the whole database every time it's called (~4s against the bundled dataset
size), so it is only called every `recompute_every` intervals, not on every
single one -- calling it every interval would make the backend fall behind
its own pacing.
"""

import os
import random
import sys
import threading
import time
from datetime import datetime, timedelta, timezone

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "data-generator"))
from generate import (  # noqa: E402
    CHANNELS,
    CHANNEL_FUNCS,
    INTERVAL_MINUTES,
    INTERVALS_PER_DAY,
    PROFILE_MULTIPLIER,
    USAGE_PROFILES,
    WEEKEND_BOOST_CHANNELS,
    derive_current,
)

from app.analytics import compute as analytics_compute
from app.database import SessionLocal
from app.models import Reading, SmartControllerChannel

sys.path.pop(0)

_lock = threading.Lock()
_stop_event = threading.Event()
_state = {
    "running": False,
    "date": None,
    "site_ids": [],
    "interval_index": 0,
    "total_intervals": INTERVALS_PER_DAY,
    "recompute_count": 0,
    "last_recomputed_at_interval": None,
    "error": None,
}


def get_status() -> dict:
    with _lock:
        return dict(_state)


def site_profile(site_id: str) -> str:
    # Same assignment rule as generate.py / live_demo.py: USAGE_PROFILES[site_index % 3].
    try:
        site_index = int(site_id.rsplit("-", 1)[-1]) - 1
    except ValueError:
        site_index = 0
    return USAGE_PROFILES[site_index % len(USAGE_PROFILES)]


def _last_cumulative(db, device_id: str) -> float:
    row = (
        db.query(Reading.cumulative_energy_kwh)
        .filter(Reading.device_id == device_id)
        .order_by(Reading.timestamp.desc())
        .first()
    )
    return float(row[0]) if row and row[0] is not None else 0.0


def _clear_existing(db, device_ids: list[str], day_start: datetime, day_end: datetime) -> None:
    db.query(Reading).filter(
        Reading.device_id.in_(device_ids), Reading.timestamp >= day_start, Reading.timestamp < day_end
    ).delete(synchronize_session=False)
    db.commit()


def _run(site_ids: list[str], day: str, interval_seconds: float, recompute_every: int, seed: int) -> None:
    db = SessionLocal()
    try:
        day_start = datetime.strptime(day, "%Y-%m-%d").replace(tzinfo=timezone.utc)
        day_end = day_start + timedelta(days=1)

        site_channels: dict[str, dict[str, str]] = {}
        for site_id in site_ids:
            channels = {
                row.controller_channel: row.device_id
                for row in db.query(SmartControllerChannel).filter(SmartControllerChannel.site_id == site_id)
                if row.controller_channel in CHANNELS
            }
            missing = [ch for ch in CHANNELS if ch not in channels]
            if missing:
                raise ValueError(f"{site_id} is missing channel(s) {missing}")
            site_channels[site_id] = channels

        all_device_ids = [d for channels in site_channels.values() for d in channels.values()]
        _clear_existing(db, all_device_ids, day_start, day_end)

        cumulative = {
            site_id: {ch: _last_cumulative(db, device_id) for ch, device_id in channels.items()}
            for site_id, channels in site_channels.items()
        }
        rngs = {
            site_id: {ch: random.Random(seed * 1000 + i + (hash(site_id) % 10_000)) for i, ch in enumerate(CHANNELS)}
            for site_id in site_ids
        }

        with _lock:
            _state.update(
                running=True,
                date=day,
                site_ids=site_ids,
                interval_index=0,
                total_intervals=INTERVALS_PER_DAY,
                recompute_count=0,
                last_recomputed_at_interval=None,
                error=None,
            )

        for interval_index in range(INTERVALS_PER_DAY):
            if _stop_event.is_set():
                break
            dt = day_start + timedelta(minutes=interval_index * INTERVAL_MINUTES)

            for site_id in site_ids:
                base_multiplier = PROFILE_MULTIPLIER[site_profile(site_id)]
                for channel, device_id in site_channels[site_id].items():
                    rng = rngs[site_id][channel]
                    multiplier = base_multiplier
                    if dt.weekday() >= 5 and channel in WEEKEND_BOOST_CHANNELS:
                        multiplier *= 1.15

                    power_kw, switching_state = CHANNEL_FUNCS[channel](dt, rng, multiplier)
                    voltage_v = round(rng.uniform(225, 235), 1)
                    current_a = derive_current(power_kw, voltage_v, channel)
                    energy_kwh_interval = round(power_kw * (INTERVAL_MINUTES / 60), 5)
                    cumulative[site_id][channel] = round(cumulative[site_id][channel] + energy_kwh_interval, 4)

                    db.add(
                        Reading(
                            reading_id=f"{device_id}_{dt.strftime('%Y%m%dT%H%M')}",
                            device_id=device_id,
                            timestamp=dt,
                            voltage_v=voltage_v,
                            current_a=current_a,
                            power_kw=power_kw,
                            energy_kwh_interval=energy_kwh_interval,
                            cumulative_energy_kwh=cumulative[site_id][channel],
                            switching_state=switching_state,
                            quality_flag="valid",
                        )
                    )
            db.commit()

            with _lock:
                _state["interval_index"] = interval_index + 1

            is_last = interval_index + 1 == INTERVALS_PER_DAY
            if recompute_every and ((interval_index + 1) % recompute_every == 0 or is_last):
                analytics_compute.run()
                with _lock:
                    _state["recompute_count"] += 1
                    _state["last_recomputed_at_interval"] = interval_index + 1

            if not is_last:
                time.sleep(interval_seconds)

    except Exception as exc:  # noqa: BLE001 -- surfaced to the status endpoint, not swallowed
        with _lock:
            _state["error"] = str(exc)
    finally:
        db.close()
        with _lock:
            _state["running"] = False


def start(
    site_ids: list[str],
    day: str = "2026-01-31",
    interval_seconds: float = 0.3,
    recompute_every: int = 32,
    seed: int = 42,
) -> None:
    with _lock:
        if _state["running"]:
            raise RuntimeError("A simulation is already running.")
    _stop_event.clear()
    thread = threading.Thread(
        target=_run, args=(site_ids, day, interval_seconds, recompute_every, seed), daemon=True
    )
    thread.start()


def stop() -> None:
    _stop_event.set()
