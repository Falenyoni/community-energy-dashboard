from datetime import datetime, timedelta

from app.ingestion.schemas import RawReading

# Acceptable range for out_of_range detection, per DATA_SPECIFICATION.md
# (207-253V = +/-10% of 230V nominal SA supply).
VOLTAGE_RANGE_V = (207.0, 253.0)

# Assumed power factor per channel, used only by the R6 V*I*PF agreement
# check. Must match data-generator/generate.py's POWER_FACTOR dict exactly
# -- that's the value the simulator used to derive current_a from power_kw
# in the first place, so R6 has to check against the same constant or it
# would flag a large share of genuinely correct simulated readings.
# whole_house is deliberately absent: a whole-house meter mixes many
# appliances at once, so no single assumed PF applies, and these readings
# never carry current_a/voltage_v anyway (R6 is a no-op for them, same as R4).
CHANNEL_POWER_FACTOR = {
    "geyser": 1.0,
    "fridge": 0.85,
    "lighting": 0.98,
    "plugs": 0.95,
    "cooking": 1.0,
    "background": 0.9,
}
R6_TOLERANCE = 0.05

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
    # whole_house: real meter readings for an entire UK household (no
    # per-appliance split), not a simulated controller channel. Ceiling set
    # near a single-phase domestic main-fuse limit (~23kW at 230V/100A)
    # rather than tuned against simulated usage, since there's no generator
    # profile to calibrate it against.
    "whole_house": 25.0,
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

    if reading.power_kw is None:
        return "missing"

    # R2: timestamp must fall on a 15-min grid slot (00/15/30/45, zero
    # seconds). A half-hourly source (e.g. Low Carbon London) still passes,
    # since :00 and :30 are both multiples of 15 -- this checks grid
    # *alignment*, not a fixed sampling cadence.
    if (
        reading.timestamp.second != 0
        or reading.timestamp.microsecond != 0
        or reading.timestamp.minute % 15 != 0
    ):
        return "out_of_range"

    # voltage_v is only captured by smart-controller channels — a real
    # whole-house meter reading has no voltage telemetry at all (not a
    # missing value, just a field this source never provides), so the
    # range check only applies when a voltage is actually present.
    if reading.voltage_v is not None and not (
        VOLTAGE_RANGE_V[0] <= reading.voltage_v <= VOLTAGE_RANGE_V[1]
    ):
        return "out_of_range"

    max_power = CHANNEL_MAX_POWER_KW.get(reading.controller_channel)
    if reading.power_kw < 0 or (max_power is not None and reading.power_kw > max_power):
        return "out_of_range"

    # R6: only evaluable when a source reports current_a as well as
    # voltage_v, and only for channels with an assumed power factor
    # (whole_house has neither telemetry nor a single assumed PF).
    expected_pf = CHANNEL_POWER_FACTOR.get(reading.controller_channel)
    if (
        expected_pf is not None
        and reading.voltage_v is not None
        and reading.current_a is not None
        and reading.voltage_v > 0
        and reading.current_a > 0
    ):
        apparent_kw = reading.voltage_v * reading.current_a / 1000
        if apparent_kw > 0:
            implied_pf = reading.power_kw / apparent_kw
            deviation = abs(implied_pf - expected_pf) / expected_pf
            if deviation > R6_TOLERANCE:
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


def _modal_interval_minutes(timestamps: list[datetime]) -> int:
    """
    Infers the source's native sampling interval from the most common gap
    between consecutive sorted timestamps (15 min for the simulator, 30 min
    for e.g. Low Carbon London) -- gap-filling has to walk the grid the
    source actually uses, not assume one fixed cadence for every source.
    """
    if len(timestamps) < 2:
        return 15
    ordered = sorted(timestamps)
    gaps: dict[int, int] = {}
    for prev, curr in zip(ordered, ordered[1:]):
        minutes = round((curr - prev).total_seconds() / 60)
        if minutes > 0:
            gaps[minutes] = gaps.get(minutes, 0) + 1
    if not gaps:
        return 15
    return max(gaps, key=lambda m: gaps[m])


def fill_short_gaps(
    device_id: str,
    valid_readings: list[tuple[datetime, float]],
) -> list[dict]:
    """
    Stage-1 gap handling: for one device's sorted (timestamp, power_kw)
    valid readings, linearly interpolates power_kw across gaps of up to two
    missing intervals and returns the new synthetic rows to insert
    (quality_flag="imputed"). Gaps longer than two intervals are left
    alone -- they stay absent, counted as missing by completeness_ratio(),
    rather than the pipeline inventing a multi-hour run of consumption.

    reading_id/voltage_v/current_a/cumulative_energy_kwh are intentionally
    not set here (None/derived by the caller) -- interpolation only
    estimates power_kw and the energy it implies, not telemetry the pipeline
    never measured for that slot.
    """
    if len(valid_readings) < 2:
        return []

    ordered = sorted(valid_readings, key=lambda r: r[0])
    interval = _modal_interval_minutes([ts for ts, _ in ordered])
    step = timedelta(minutes=interval)
    max_gap_intervals = 2

    new_rows: list[dict] = []
    for (ts_before, p_before), (ts_after, p_after) in zip(ordered, ordered[1:]):
        gap_minutes = (ts_after - ts_before).total_seconds() / 60
        n_missing = round(gap_minutes / interval) - 1
        if n_missing <= 0 or n_missing > max_gap_intervals:
            continue
        for i in range(1, n_missing + 1):
            ts = ts_before + step * i
            fraction = i / (n_missing + 1)
            power_kw = round(p_before + (p_after - p_before) * fraction, 4)
            new_rows.append(
                {
                    "device_id": device_id,
                    "timestamp": ts,
                    "power_kw": power_kw,
                    "energy_kwh_interval": round(power_kw * (interval / 60), 5),
                    "quality_flag": "imputed",
                }
            )
    return new_rows
