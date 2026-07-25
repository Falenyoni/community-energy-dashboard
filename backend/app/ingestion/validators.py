from datetime import datetime

from app.ingestion.schemas import RawReading

# Acceptable range for out_of_range detection, per DATA_SPECIFICATION.md
# (207-253V = +/-10% of 230V nominal SA supply).
VOLTAGE_RANGE_V = (207.0, 253.0)

# Sanity ceiling per channel for out_of_range detection — deliberately looser
# than the "typical" generation ranges in DATA_SPECIFICATION.md, since this
# is meant to catch clearly bad data (a fridge at 5kW), not flag every
# reading near the top of its normal operating range.
#
# Set above the highest value a "high" usage-profile site can legitimately
# reach in data-generator/generate.py (typical_max x 1.5 profile multiplier
# x 1.15 weekend boost, where applicable) — otherwise realistic high-usage
# readings get misclassified as data-quality errors. background is
# deliberately left tight: its ceiling is meant to still catch the
# generator's injected "abnormal overnight draw" scenario (0.3-0.5kW),
# which legitimate background usage (max ~0.225kW) never reaches.
CHANNEL_MAX_POWER_KW = {
    "geyser": 5.0,
    "fridge": 0.5,
    "lighting": 1.0,
    "plugs": 3.0,
    "cooking": 6.5,
    "background": 0.3,
}


def classify_reading(reading: RawReading, seen_keys: set[tuple[str, datetime]]) -> str:
    """
    Assigns a quality_flag to a single reading. Order matters: duplicate
    detection runs first since a duplicate row's values aren't meaningful
    to range-check.

    Note: this only classifies rows that ARE present. A wholly absent
    interval (no row at all) can't carry a per-row flag — that's what
    completeness_ratio()/expected_reading_count() below are for.
    """
    key = (reading.device_id, reading.timestamp)
    if key in seen_keys:
        return "duplicate"
    seen_keys.add(key)

    if reading.voltage_v is None or reading.power_kw is None:
        return "missing"

    if not (VOLTAGE_RANGE_V[0] <= reading.voltage_v <= VOLTAGE_RANGE_V[1]):
        return "out_of_range"

    max_power = CHANNEL_MAX_POWER_KW.get(reading.controller_channel)
    if reading.power_kw < 0 or (max_power is not None and reading.power_kw > max_power):
        return "out_of_range"

    return "valid"


def expected_reading_count(start: datetime, end: datetime, interval_minutes: int = 15) -> int:
    """
    Expected number of readings across [start, end] at a fixed interval.

    Caveat: when called with min/max timestamps observed in the actual data
    (as ingest.py does), this correctly accounts for gaps *within* the
    range, but can't detect missing intervals at the very start or end of
    the intended period, since there's no data point to reveal them.
    """
    total_minutes = (end - start).total_seconds() / 60
    return int(total_minutes // interval_minutes) + 1


def completeness_ratio(expected_count: int, actual_count: int) -> float:
    """eta = valid readings received / expected readings, per DATA_SPECIFICATION.md."""
    if expected_count <= 0:
        return 1.0
    return round(actual_count / expected_count, 4)
