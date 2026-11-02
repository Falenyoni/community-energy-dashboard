"""
Live ingestion adapter for real CBi Astute (Tuya) devices, via Tuya's Cloud
API — polling, using `tinytuya.Cloud`, authenticated with just the project's
Access ID/Secret (no end-user app login needed at all).

This replaced an earlier attempt built on `tuya-iot-py-sdk`'s message queue
(TuyaOpenMQ), which needed a full Smart Life account login via
TuyaOpenAPI.connect() - that login consistently failed with a 1106
"permission deny" that couldn't be resolved from the client side (ruled out:
wrong Access ID/Secret, wrong password, missing Cloud Service subscriptions -
see docs/CBI_ASTUTE_INTEGRATION.md for the full trail). `tinytuya.Cloud`
calls the same underlying REST API but never attempts that login at all, and
it worked immediately.

Known limitation, deliberately not solved here: this counts against the
30,000 API calls/month free-tier quota, same as any REST polling - the
quota math in docs/CBI_ASTUTE_INTEGRATION.md (why polling doesn't scale to
10 households) still applies. This is fine for one device today; the
message-queue push approach remains the target for the real multi-household
deployment, once its login problem is actually resolved (or a different
scaling approach is chosen).

Usage:
    python -m app.ingestion.tuya_source            # poll once
    python -m app.ingestion.tuya_source --loop 900  # poll every 900s
"""

import argparse
import time
from datetime import datetime, timezone

import tinytuya
from sqlalchemy.orm import Session

from app.config import get_settings
from app.database import SessionLocal
from app.ingestion.ingest import get_or_create_channel, get_or_create_site
from app.ingestion.schemas import RawReading
from app.ingestion.validators import classify_reading
from app.models import Reading, new_id

settings = get_settings()

# Region code for tinytuya's Cloud class - "eu" is Central Europe
# (openapi.tuyaeu.com), which is where this account's data actually lives,
# confirmed empirically (see docs/CBI_ASTUTE_INTEGRATION.md).
TUYA_REGION = "eu"

# Per-device metadata Tuya has no concept of - see the same note in the
# previous version of this file. Placeholder for the one device in testing;
# needs to become a real table once there's more than a handful of
# households.
DEVICE_REGISTRY: dict[str, dict[str, str]] = {
    "bfeebc57c438062c7bcxox": {"site_id": "site-bongani-test", "controller_channel": "plugs"},
}

# DP codes and scale factors - CONFIRMED against this exact product's real
# mapping via `python -m tinytuya wizard` (not guessed): scale N means
# "divide the raw integer by 10^N to get the real value".
DP_VOLTAGE = "cur_voltage"          # unit V,  scale 1 -> raw / 10
DP_CURRENT = "cur_current"          # unit mA, scale 0 -> raw as-is, then /1000 for amps
DP_POWER = "cur_power"              # unit W,  scale 1 -> raw / 10
DP_CUMULATIVE_ENERGY = "add_ele"    # scale 3 -> raw / 1000 (kWh)
DP_SWITCH = "switch_1"

# In-memory cache so a --loop run doesn't re-query the database on every
# single poll just to find the previous cumulative value - populated lazily
# from the database (see _get_last_cumulative_kwh) the first time each
# device is seen in a given process, so a fresh one-shot run still computes
# a correct delta against whatever was last stored, not just against other
# polls in the same process.
_last_cumulative_kwh: dict[str, float] = {}
_seen_keys: set[tuple[str, datetime]] = set()


def _get_last_cumulative_kwh(db: Session, device_id: str) -> float | None:
    last = (
        db.query(Reading)
        .filter(Reading.device_id == device_id, Reading.cumulative_energy_kwh.isnot(None))
        .order_by(Reading.timestamp.desc())
        .first()
    )
    return float(last.cumulative_energy_kwh) if last is not None else None


def poll_once(cloud: tinytuya.Cloud) -> None:
    db = SessionLocal()
    try:
        for device_id, registry_entry in DEVICE_REGISTRY.items():
            response = cloud.getstatus(device_id)
            if not response.get("success"):
                print(f"  {device_id}: poll failed - {response}")
                continue

            status_by_code = {item["code"]: item["value"] for item in response["result"]}

            voltage_raw = status_by_code.get(DP_VOLTAGE)
            current_raw = status_by_code.get(DP_CURRENT)
            power_raw = status_by_code.get(DP_POWER)
            cumulative_raw = status_by_code.get(DP_CUMULATIVE_ENERGY)
            switch_raw = status_by_code.get(DP_SWITCH)

            voltage_v = voltage_raw / 10 if voltage_raw is not None else None
            current_a = current_raw / 1000 if current_raw is not None else None
            power_kw = power_raw / 10 / 1000 if power_raw is not None else None
            cumulative_energy_kwh = cumulative_raw / 1000 if cumulative_raw is not None else None
            switching_state = "on" if switch_raw else "off" if switch_raw is not None else "off"

            energy_kwh_interval = None
            if cumulative_energy_kwh is not None:
                if device_id not in _last_cumulative_kwh:
                    seeded = _get_last_cumulative_kwh(db, device_id)
                    if seeded is not None:
                        _last_cumulative_kwh[device_id] = seeded
                previous = _last_cumulative_kwh.get(device_id)
                if previous is not None:
                    energy_kwh_interval = max(cumulative_energy_kwh - previous, 0.0)
                _last_cumulative_kwh[device_id] = cumulative_energy_kwh

            reading = RawReading(
                reading_id=new_id(),
                site_id=registry_entry["site_id"],
                device_id=device_id,
                controller_channel=registry_entry["controller_channel"],
                timestamp=datetime.now(timezone.utc),
                voltage_v=voltage_v,
                current_a=current_a,
                power_kw=power_kw,
                energy_kwh_interval=energy_kwh_interval,
                cumulative_energy_kwh=cumulative_energy_kwh,
                switching_state=switching_state,
            )

            _ingest_one(db, reading)
            print(
                f"  {device_id}: V={voltage_v} A={current_a} kW={power_kw} "
                f"cum_kWh={cumulative_energy_kwh} state={switching_state}"
            )

        db.commit()
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


def _ingest_one(db: Session, reading: RawReading) -> None:
    """Single-reading version of ingest_csv's per-row body - see the CSV path
    (app/ingestion/ingest.py) for the batch equivalent this mirrors."""
    quality_flag = classify_reading(reading, _seen_keys)

    get_or_create_site(db, reading.site_id, data_source="real")
    get_or_create_channel(
        db,
        reading.device_id,
        reading.site_id,
        reading.controller_channel,
        reading.switching_state,
    )

    db.add(
        Reading(
            reading_id=reading.reading_id,
            device_id=reading.device_id,
            timestamp=reading.timestamp,
            voltage_v=reading.voltage_v,
            current_a=reading.current_a,
            power_kw=reading.power_kw,
            energy_kwh_interval=reading.energy_kwh_interval,
            cumulative_energy_kwh=reading.cumulative_energy_kwh,
            switching_state=reading.switching_state,
            quality_flag=quality_flag,
        )
    )


def run() -> None:
    parser = argparse.ArgumentParser(description="Poll real Tuya devices into the database.")
    parser.add_argument(
        "--loop", type=int, default=0,
        help="Poll repeatedly every N seconds instead of once and exiting.",
    )
    args = parser.parse_args()

    cloud = tinytuya.Cloud(
        apiRegion=TUYA_REGION,
        apiKey=settings.tuya_access_id,
        apiSecret=settings.tuya_access_secret,
    )

    if args.loop > 0:
        print(f"Polling every {args.loop}s. Ctrl+C to stop.")
        while True:
            poll_once(cloud)
            time.sleep(args.loop)
    else:
        poll_once(cloud)


if __name__ == "__main__":
    run()
