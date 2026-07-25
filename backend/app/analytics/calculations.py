"""
Comparative analytics algorithms per proposal Section C.4 / Mathematical
Notations page.

Each function is a pure calculation: given known inputs, it produces a
deterministic output with no database access — this is what makes them
directly unit-testable against a hand-calculated reference case (see
backend/tests/test_analytics.py). Database orchestration (reading Reading
rows, writing DailySummary/ComparisonResult) lives in compute.py, kept
separate on purpose.

Data completeness (eta) is the sixth algorithm this module set counts
toward Objective 3's "at least six" requirement, but its canonical
implementation lives in app.ingestion.validators.completeness_ratio, since
it's computed at ingestion time, not here — re-implementing it here would
just be duplicate logic for the same formula.
"""

from __future__ import annotations

# R/kWh, flat Eskom Homepower-style rate. A configurable estimate, not
# official municipal/Eskom billing (see DATA_SPECIFICATION.md, Assumptions).
DEFAULT_TARIFF_RATE = 2.90


def estimate_cost(energy_kwh: float, tariff_rate: float = DEFAULT_TARIFF_RATE) -> float:
    """C = E x tariff."""
    return round(energy_kwh * tariff_rate, 2)


def daily_total_kwh(interval_energies_kwh: list[float]) -> float:
    """Sum of interval energy readings for one device over one day."""
    return round(sum(interval_energies_kwh), 4)


def peak_power_kw(power_readings_kw: list[float]) -> float:
    """Pmax: highest power_kw reading in a period."""
    return max(power_readings_kw) if power_readings_kw else 0.0


def baseline_kwh(historical_daily_totals_kwh: list[float]) -> float | None:
    """
    B: mean historical consumption for the same device/site over a
    comparable prior period. None if no history exists yet.
    """
    if not historical_daily_totals_kwh:
        return None
    return round(sum(historical_daily_totals_kwh) / len(historical_daily_totals_kwh), 4)


def peer_group_average_kwh(peer_daily_totals_kwh: list[float]) -> float | None:
    """G: mean consumption across anonymised peer sites for the same period."""
    if not peer_daily_totals_kwh:
        return None
    return round(sum(peer_daily_totals_kwh) / len(peer_daily_totals_kwh), 4)


def relative_ratio(value_kwh: float, benchmark_kwh: float | None) -> float | None:
    """R = value / benchmark. None if there's no (or a zero) benchmark to compare against."""
    if not benchmark_kwh:
        return None
    return round(value_kwh / benchmark_kwh, 3)


def classify_status(ratio: float | None, low: float = 0.9, high: float = 1.1) -> str:
    """
    Discretizes a ratio into a dashboard-friendly status band.
    "unknown" when there's no ratio yet (no benchmark available).
    """
    if ratio is None:
        return "unknown"
    if ratio <= low:
        return "below_average"
    if ratio >= high:
        return "above_average"
    return "typical"


def rank_devices(device_totals_kwh: dict[str, float]) -> list[tuple[str, float]]:
    """Device-level ranking: highest total kWh first."""
    return sorted(device_totals_kwh.items(), key=lambda item: item[1], reverse=True)


def percentile(values: list[float], pct: float) -> float:
    """Linear-interpolation percentile (pct in [0, 100]) — used for peak-threshold detection."""
    if not values:
        return 0.0
    ordered = sorted(values)
    if len(ordered) == 1:
        return ordered[0]
    k = (len(ordered) - 1) * (pct / 100)
    floor_index = int(k)
    ceil_index = min(floor_index + 1, len(ordered) - 1)
    if floor_index == ceil_index:
        return ordered[floor_index]
    fraction = k - floor_index
    return ordered[floor_index] + (ordered[ceil_index] - ordered[floor_index]) * fraction


def is_peak_reading(power_kw: float, threshold_kw: float) -> bool:
    """Peak flag: True if a reading's power meets/exceeds a configured threshold."""
    return power_kw >= threshold_kw
