"""
Generates a simulated smart-controller dataset per DATA_SPECIFICATION.md.

Usage:
    python generate.py [--output PATH] [--seed N]

Produces one CSV: 10 sites x 6 controller channels x 30 days of 15-minute
readings (~172,800 rows), with six deliberately injected scenarios at fixed,
documented locations — a missing-readings gap, a duplicate reading, an
out-of-range voltage, and three abnormal-use events — so the ingestion
pipeline (backend/app/ingestion/) can be tested against known expected
outputs rather than "does it look plausible."

Only uses the standard library — no pandas/numpy needed for this generation
logic (per-row simulation with running state per device suits a plain loop
better than vectorised array operations).
"""

import argparse
import csv
import os
import random
from datetime import datetime, timedelta, timezone

SITE_COUNT = 10
CHANNELS = ["geyser", "fridge", "lighting", "plugs", "cooking", "background"]
DAYS = 30
INTERVAL_MINUTES = 15
START = datetime(2026, 1, 1, tzinfo=timezone.utc)
INTERVALS_PER_DAY = 24 * 60 // INTERVAL_MINUTES  # 96

USAGE_PROFILES = ["low", "medium", "high"]
PROFILE_MULTIPLIER = {"low": 0.6, "medium": 1.0, "high": 1.5}

# Approximate power factor per channel, used to derive current from power/voltage.
POWER_FACTOR = {
    "geyser": 1.0,
    "fridge": 0.85,
    "lighting": 0.98,
    "plugs": 0.95,
    "cooking": 1.0,
    "background": 0.9,
}

WEEKEND_BOOST_CHANNELS = {"lighting", "plugs", "cooking"}


def geyser_power(dt, rng, multiplier):
    hour = dt.hour + dt.minute / 60
    if 5.5 <= hour <= 7.5 or 18.0 <= hour <= 20.0:
        return round(rng.uniform(2.0, 3.0) * multiplier, 3), "on"
    return 0.0, "off"


def fridge_power(dt, rng, multiplier):
    # Compressor cycles roughly every 15 minutes regardless of time of day;
    # fridge is always monitored ("on" state) even during the low part of a cycle.
    compressor_running = (dt.minute // INTERVAL_MINUTES) % 2 == 0
    if compressor_running:
        return round(rng.uniform(0.15, 0.3) * multiplier, 3), "on"
    return round(rng.uniform(0.05, 0.08) * multiplier, 3), "on"


def lighting_power(dt, rng, multiplier):
    hour = dt.hour
    if 18 <= hour <= 23 or hour == 0:
        return round(rng.uniform(0.1, 0.5) * multiplier, 3), "on"
    if 6 <= hour <= 8:
        return round(rng.uniform(0.02, 0.15) * multiplier, 3), "on"
    return 0.0, "off"


def plugs_power(dt, rng, multiplier):
    hour = dt.hour
    base = rng.uniform(0.02, 0.3)
    if 17 <= hour <= 23:
        base += rng.uniform(0.2, 1.2)
    power = round(base * multiplier, 3)
    return power, ("on" if power > 0.03 else "standby")


def cooking_power(dt, rng, multiplier):
    hour = dt.hour + dt.minute / 60
    meal_windows = [(6.5, 7.5), (12.0, 13.5), (18.0, 19.5)]
    if any(start <= hour <= end for start, end in meal_windows):
        return round(rng.uniform(1.5, 3.5) * multiplier, 3), "on"
    return 0.0, "off"


def background_power(dt, rng, multiplier):
    return round(rng.uniform(0.01, 0.15) * multiplier, 3), "on"


CHANNEL_FUNCS = {
    "geyser": geyser_power,
    "fridge": fridge_power,
    "lighting": lighting_power,
    "plugs": plugs_power,
    "cooking": cooking_power,
    "background": background_power,
}


def derive_current(power_kw: float, voltage_v: float, channel: str) -> float:
    if power_kw <= 0:
        return 0.0
    return round((power_kw * 1000) / (voltage_v * POWER_FACTOR[channel]), 3)


def generate_rows(seed: int) -> list[dict]:
    rows = []
    for site_index in range(SITE_COUNT):
        site_id = f"HOUSE-{site_index + 1:03d}"
        profile = USAGE_PROFILES[site_index % len(USAGE_PROFILES)]
        base_multiplier = PROFILE_MULTIPLIER[profile]

        for channel in CHANNELS:
            device_id = f"{site_id}-{channel.upper()}"
            site_rng = random.Random(seed * 1000 + site_index * 10 + CHANNELS.index(channel))
            cumulative = 0.0

            for interval_index in range(DAYS * INTERVALS_PER_DAY):
                dt = START + timedelta(minutes=interval_index * INTERVAL_MINUTES)
                multiplier = base_multiplier
                if dt.weekday() >= 5 and channel in WEEKEND_BOOST_CHANNELS:
                    multiplier *= 1.15

                power_kw, switching_state = CHANNEL_FUNCS[channel](dt, site_rng, multiplier)
                voltage_v = round(site_rng.uniform(225, 235), 1)
                current_a = derive_current(power_kw, voltage_v, channel)
                energy_kwh_interval = round(power_kw * (INTERVAL_MINUTES / 60), 5)
                cumulative = round(cumulative + energy_kwh_interval, 4)

                rows.append(
                    {
                        "reading_id": f"{device_id}_{dt.strftime('%Y%m%dT%H%M')}",
                        "site_id": site_id,
                        "device_id": device_id,
                        "controller_channel": channel,
                        "timestamp": dt.strftime("%Y-%m-%dT%H:%M:%SZ"),
                        "voltage_v": voltage_v,
                        "current_a": current_a,
                        "power_kw": power_kw,
                        "energy_kwh_interval": energy_kwh_interval,
                        "cumulative_energy_kwh": cumulative,
                        "switching_state": switching_state,
                        "quality_flag": "valid",
                        "_site_index": site_index,
                        "_day_index": interval_index // INTERVALS_PER_DAY,
                        "_dt": dt,
                    }
                )
    return rows


def index_by(rows: list[dict]) -> dict:
    index = {}
    for i, row in enumerate(rows):
        key = (row["_site_index"], row["controller_channel"], row["_day_index"])
        index.setdefault(key, []).append(i)
    return index


def apply_injections(rows: list[dict]) -> tuple[list[dict], list[str]]:
    """
    Six fixed, documented scenarios — see DATA_SPECIFICATION.md's
    "Deliberately injected scenarios" section. Fixed locations (not random)
    so the expected effect on ingestion output is known and reproducible.
    """
    log = []
    idx = index_by(rows)

    # 1. Missing readings: HOUSE-001, lighting, day 10, 02:00-04:45 (a comms gap)
    target = idx.get((0, "lighting", 10), [])
    gap = [i for i in target if rows[i]["_dt"].hour in (2, 3, 4)]
    for i in gap:
        rows[i]["_drop"] = True
    log.append(f"Missing gap: HOUSE-001-LIGHTING, day 10, 02:00-04:45 ({len(gap)} intervals dropped)")

    # 2. Duplicate reading: HOUSE-002, fridge, day 5, 14:00 — repeated with a new reading_id
    target = idx.get((1, "fridge", 5), [])
    dup_source = next((i for i in target if rows[i]["_dt"].hour == 14 and rows[i]["_dt"].minute == 0), None)
    if dup_source is not None:
        dup_row = dict(rows[dup_source])
        dup_row["reading_id"] += "-DUP"
        rows.append(dup_row)
        log.append(f"Duplicate reading: {rows[dup_source]['device_id']} at {rows[dup_source]['timestamp']}")

    # 3. Out-of-range voltage: HOUSE-003, plugs, day 8, 09:30 -> 268V (outside 207-253V)
    target = idx.get((2, "plugs", 8), [])
    oor = next((i for i in target if rows[i]["_dt"].hour == 9 and rows[i]["_dt"].minute == 30), None)
    if oor is not None:
        rows[oor]["voltage_v"] = 268.0
        rows[oor]["current_a"] = derive_current(rows[oor]["power_kw"], 268.0, "plugs")
        rows[oor]["quality_flag"] = "out_of_range"
        log.append(f"Out-of-range voltage: {rows[oor]['device_id']} at {rows[oor]['timestamp']} -> 268V")

    # 4. Abnormal geyser runtime: HOUSE-004, day 12, 10:00-13:45 forced "on" (typical run is ~1-2h)
    target = idx.get((3, "geyser", 12), [])
    long_run = [i for i in target if rows[i]["_dt"].hour in (10, 11, 12, 13)]
    for i in long_run:
        voltage_v = rows[i]["voltage_v"]
        rows[i]["power_kw"] = round(random.Random(seed_for(i)).uniform(2.5, 3.0), 3)
        rows[i]["current_a"] = derive_current(rows[i]["power_kw"], voltage_v, "geyser")
        rows[i]["switching_state"] = "on"
        rows[i]["quality_flag"] = "abnormal_event"
    if long_run:
        log.append(f"Abnormal geyser runtime: HOUSE-004-GEYSER, day 12, 10:00-13:45 ({len(long_run)} intervals)")

    # 5. Abnormal fridge cycling: HOUSE-005, day 20 — toggling every interval instead of the normal ~2-cycle rhythm
    target = sorted(idx.get((4, "fridge", 20), []), key=lambda i: rows[i]["_dt"])
    for pos, i in enumerate(target):
        voltage_v = rows[i]["voltage_v"]
        rows[i]["power_kw"] = round(0.3 if pos % 2 == 0 else 0.02, 3)
        rows[i]["current_a"] = derive_current(rows[i]["power_kw"], voltage_v, "fridge")
        rows[i]["switching_state"] = "on" if pos % 2 == 0 else "standby"
        rows[i]["quality_flag"] = "abnormal_event"
    if target:
        log.append(f"Abnormal fridge cycling: HOUSE-005-FRIDGE, day 20 (rapid on/off every interval, {len(target)} intervals)")

    # 6. Abnormal background overnight draw: HOUSE-006, day 18, 00:00-04:45 (should be near-idle overnight)
    target = idx.get((5, "background", 18), [])
    overnight = [i for i in target if rows[i]["_dt"].hour < 5]
    for i in overnight:
        voltage_v = rows[i]["voltage_v"]
        rows[i]["power_kw"] = round(random.Random(seed_for(i)).uniform(0.3, 0.5), 3)
        rows[i]["current_a"] = derive_current(rows[i]["power_kw"], voltage_v, "background")
        rows[i]["quality_flag"] = "abnormal_event"
    if overnight:
        log.append(f"Abnormal background overnight draw: HOUSE-006-BACKGROUND, day 18, 00:00-04:45 ({len(overnight)} intervals)")

    rows = [row for row in rows if not row.get("_drop")]
    return rows, log


def seed_for(row_index: int) -> int:
    return 900_000 + row_index


FIELDNAMES = [
    "reading_id",
    "site_id",
    "device_id",
    "controller_channel",
    "timestamp",
    "voltage_v",
    "current_a",
    "power_kw",
    "energy_kwh_interval",
    "cumulative_energy_kwh",
    "switching_state",
    "quality_flag",
]


def write_csv(rows: list[dict], output_path: str) -> None:
    rows_sorted = sorted(rows, key=lambda r: (r["site_id"], r["device_id"], r["timestamp"]))
    os.makedirs(os.path.dirname(output_path), exist_ok=True)
    with open(output_path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=FIELDNAMES, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows_sorted)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--output",
        default=os.path.join("output", "simulated_readings.csv"),
        help="Output CSV path (default: output/simulated_readings.csv)",
    )
    parser.add_argument("--seed", type=int, default=42, help="Random seed for reproducibility")
    args = parser.parse_args()

    rows = generate_rows(args.seed)
    rows, injected_log = apply_injections(rows)
    write_csv(rows, args.output)

    print(f"Generated {len(rows)} rows across {SITE_COUNT} sites x {len(CHANNELS)} channels x {DAYS} days")
    print(f"Written to {args.output}\n")
    print("Injected scenarios:")
    for line in injected_log:
        print(f"  - {line}")


if __name__ == "__main__":
    main()
