"""
Batched CLI ingestion for smart-controller-style CSVs — same validation,
classification, and audit-log behaviour as `app.ingestion.ingest`, but
writes new Reading rows via `session.execute(insert(Reading), [...])` in
batches instead of one `db.add()` per row.

Why this exists: `ingest.py`'s per-row `db.add()` means SQLAlchemy issues
one INSERT round-trip per row at flush/commit time. Against a remote
database (e.g. Render's Virginia-hosted Postgres from South Africa), that
per-row network latency dominates — ~170k rows at even 100-150ms RTT each
adds up to hours. Batching hundreds of rows into a single multi-row INSERT
statement (SQLAlchemy 2.0's "insertmanyvalues" batching) cuts the number of
round-trips by ~2-3 orders of magnitude, without changing what gets
validated, classified, or written.

Usage:
    python -m app.ingestion.fast_ingest path/to/data.csv [--batch-size 2000]

Use this for pushing large files to a remote database. `ingest.py` remains
the reference/simple version for small files or local Postgres, where
round-trip latency isn't the bottleneck.
"""

import argparse
import csv
from datetime import datetime

from pydantic import ValidationError
from sqlalchemy import insert
from sqlalchemy.orm import Session

from app.database import SessionLocal
from app.ingestion.ingest import clean_row, get_or_create_channel, get_or_create_site
from app.ingestion.schemas import RawReading
from app.ingestion.validators import (
    classify_reading,
    completeness_ratio,
    expected_reading_count,
)
from app.models import AuditLog, Reading


def ingest_csv_fast(path: str, batch_size: int = 2000) -> None:
    db: Session = SessionLocal()
    seen_keys: set[tuple[str, datetime]] = set()
    counts: dict[str, int] = {}
    rejected: list[tuple[int, str]] = []
    device_timestamps: dict[str, list[datetime]] = {}
    pending_rows: list[dict] = []

    existing_reading_ids: set[str] = {row[0] for row in db.query(Reading.reading_id).all()}

    def flush_pending():
        if pending_rows:
            db.execute(insert(Reading), pending_rows)
            pending_rows.clear()

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

                if reading.reading_id not in existing_reading_ids:
                    existing_reading_ids.add(reading.reading_id)
                    pending_rows.append(
                        {
                            "reading_id": reading.reading_id,
                            "device_id": reading.device_id,
                            "timestamp": reading.timestamp,
                            "voltage_v": reading.voltage_v,
                            "current_a": reading.current_a,
                            "power_kw": reading.power_kw,
                            "energy_kwh_interval": reading.energy_kwh_interval,
                            "cumulative_energy_kwh": reading.cumulative_energy_kwh,
                            "switching_state": reading.switching_state,
                            "quality_flag": quality_flag,
                        }
                    )

                if len(pending_rows) >= batch_size:
                    flush_pending()
                    db.commit()
                    print(f"  ...processed {row_number:,} rows (committed batch)")

        flush_pending()
        db.commit()
    except Exception:
        db.rollback()
        raise

    total_rows = sum(counts.values()) + len(rejected)
    summary = (
        f"fast_ingest_csv:{path} rows={total_rows} valid={counts.get('valid', 0)} "
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
        description="Batched ingestion of a smart-controller-style CSV into the database."
    )
    parser.add_argument("csv_path", help="Path to the CSV file to ingest")
    parser.add_argument("--batch-size", type=int, default=2000, help="Rows per batched INSERT (default 2000)")
    args = parser.parse_args()
    ingest_csv_fast(args.csv_path, args.batch_size)


if __name__ == "__main__":
    main()
