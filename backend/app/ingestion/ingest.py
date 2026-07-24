"""
CLI ingestion for smart-controller-style CSVs.

Usage:
    python -m app.ingestion.ingest path/to/data.csv

Works identically whether the CSV came from the simulated generator, a
manual export, or (in future) an approved API dump saved to disk — that's
the whole point of the schema/validators split (see ARCHITECTURE_DECISIONS.md).
"""

import argparse
import csv
from datetime import datetime

from pydantic import ValidationError
from sqlalchemy.orm import Session

from app.database import SessionLocal
from app.ingestion.schemas import RawReading
from app.ingestion.validators import (
    classify_reading,
    completeness_ratio,
    expected_reading_count,
)
from app.models import AuditLog, Reading, Site, SmartControllerChannel


def clean_row(row: dict) -> dict:
    """CSV empty cells arrive as '' — coerce to None so Optional[float] fields validate."""
    return {key: (value if value not in ("", None) else None) for key, value in row.items()}


def get_or_create_site(db: Session, site_id: str) -> Site:
    site = db.get(Site, site_id)
    if site is None:
        site = Site(site_id=site_id, anonymised_label=site_id, site_type="household")
        db.add(site)
        db.flush()
    return site


def get_or_create_channel(
    db: Session, device_id: str, site_id: str, controller_channel: str, switching_state: str
) -> SmartControllerChannel:
    channel = db.get(SmartControllerChannel, device_id)
    if channel is None:
        channel = SmartControllerChannel(
            device_id=device_id,
            site_id=site_id,
            controller_channel=controller_channel,
            switching_state=switching_state,
        )
        db.add(channel)
        db.flush()
    else:
        channel.switching_state = switching_state
    return channel


def ingest_csv(path: str) -> None:
    db = SessionLocal()
    seen_keys: set[tuple[str, datetime]] = set()
    counts: dict[str, int] = {}
    rejected: list[tuple[int, str]] = []
    device_timestamps: dict[str, list[datetime]] = {}

    try:
        with open(path, newline="", encoding="utf-8") as f:
            reader = csv.DictReader(f)
            for row_number, row in enumerate(reader, start=2):  # header is line 1
                try:
                    reading = RawReading.model_validate(clean_row(row))
                except ValidationError as exc:
                    rejected.append((row_number, str(exc).splitlines()[0]))
                    continue

                quality_flag = classify_reading(reading, seen_keys)
                counts[quality_flag] = counts.get(quality_flag, 0) + 1
                # A duplicate repeats an already-counted time slot rather than
                # filling a new one, so it must not inflate the completeness count.
                if quality_flag != "duplicate":
                    device_timestamps.setdefault(reading.device_id, []).append(reading.timestamp)

                get_or_create_site(db, reading.site_id)
                get_or_create_channel(
                    db,
                    reading.device_id,
                    reading.site_id,
                    reading.controller_channel,
                    reading.switching_state,
                )

                if db.get(Reading, reading.reading_id) is None:
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

        db.commit()
    except Exception:
        db.rollback()
        raise

    total_rows = sum(counts.values()) + len(rejected)
    summary = (
        f"ingest_csv:{path} rows={total_rows} valid={counts.get('valid', 0)} "
        f"missing={counts.get('missing', 0)} duplicate={counts.get('duplicate', 0)} "
        f"out_of_range={counts.get('out_of_range', 0)} rejected={len(rejected)}"
    )
    db.add(AuditLog(action=summary))
    db.commit()
    db.close()

    print(summary)

    if rejected:
        print(f"\n{len(rejected)} row(s) rejected (malformed, not written to the database):")
        for row_number, error in rejected[:10]:
            print(f"  line {row_number}: {error}")
        if len(rejected) > 10:
            print(f"  ... and {len(rejected) - 10} more")

    print("\nData completeness per device (eta = actual / expected readings):")
    for device_id, timestamps in sorted(device_timestamps.items()):
        expected = expected_reading_count(min(timestamps), max(timestamps))
        actual = len(timestamps)
        eta = completeness_ratio(expected, actual)
        print(f"  {device_id}: {actual}/{expected} ({eta:.1%})")


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Ingest a smart-controller-style CSV into the database."
    )
    parser.add_argument("csv_path", help="Path to the CSV file to ingest")
    args = parser.parse_args()
    ingest_csv(args.csv_path)


if __name__ == "__main__":
    main()
