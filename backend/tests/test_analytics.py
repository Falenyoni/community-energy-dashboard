"""
Verifies each analytics formula against a hand-calculated reference case —
the "unit-tested verification result against a known reference case"
deliverable from Objective 3.
"""

import pytest

from app.analytics.calculations import (
    baseline_kwh,
    classify_status,
    classify_warning,
    daily_total_kwh,
    daily_warning_threshold,
    estimate_cost,
    is_peak_reading,
    night_warning_threshold,
    peak_power_kw,
    peer_group_average_kwh,
    percentile,
    rank_devices,
    relative_ratio,
    warning_severity,
)


def test_estimate_cost_matches_manual_calculation():
    # Manual calc: 15 kWh x R2.90/kWh = R43.50
    assert estimate_cost(15.0) == 43.50


def test_estimate_cost_custom_tariff():
    assert estimate_cost(10.0, tariff_rate=2.00) == 20.00


def test_daily_total_kwh_sums_intervals():
    # Four 15-min intervals of 0.05 kWh each = 0.20 kWh total
    assert daily_total_kwh([0.05, 0.05, 0.05, 0.05]) == 0.20


def test_peak_power_kw_returns_max():
    assert peak_power_kw([0.1, 2.8, 0.3, 1.9]) == 2.8


def test_peak_power_kw_empty_list():
    assert peak_power_kw([]) == 0.0


def test_baseline_kwh_is_mean_of_history():
    # Manual calc: (10 + 12 + 14) / 3 = 12.0
    assert baseline_kwh([10.0, 12.0, 14.0]) == 12.0


def test_baseline_kwh_no_history_returns_none():
    assert baseline_kwh([]) is None


def test_peer_group_average_kwh():
    # Manual calc: (8 + 10 + 12 + 10) / 4 = 10.0
    assert peer_group_average_kwh([8.0, 10.0, 12.0, 10.0]) == 10.0


def test_relative_ratio_above_benchmark():
    assert relative_ratio(15.0, 10.0) == 1.5


def test_relative_ratio_no_benchmark_returns_none():
    assert relative_ratio(15.0, None) is None
    assert relative_ratio(15.0, 0) is None


def test_classify_status_thresholds():
    assert classify_status(1.5) == "above_average"
    assert classify_status(0.5) == "below_average"
    assert classify_status(1.0) == "typical"
    assert classify_status(None) == "unknown"


def test_rank_devices_orders_descending():
    totals = {"fridge": 5.0, "geyser": 20.0, "lighting": 2.0}
    assert rank_devices(totals) == [("geyser", 20.0), ("fridge", 5.0), ("lighting", 2.0)]


def test_percentile_matches_manual_calculation():
    # Manual calc for [1..10], 90th percentile:
    # k = (10-1) * 0.9 = 8.1 -> between index 8 (value 9) and 9 (value 10), fraction 0.1
    # = 9 + (10-9) * 0.1 = 9.1
    values = [1, 2, 3, 4, 5, 6, 7, 8, 9, 10]
    assert percentile(values, 90) == pytest.approx(9.1)


def test_is_peak_reading_threshold():
    assert is_peak_reading(3.0, threshold_kw=2.5) is True
    assert is_peak_reading(2.0, threshold_kw=2.5) is False


def test_daily_warning_threshold_matches_manual_calculation():
    # Seven days at 5.0 kWh, one spike at 20.0 kWh: Q1=Q3=median=5.0, IQR=0,
    # so tau = max(5.0 + 1.5*0, 1.15*5.0) = 5.75
    daily_totals = [5.0, 5.0, 5.0, 5.0, 5.0, 5.0, 5.0, 20.0]
    assert daily_warning_threshold(daily_totals) == pytest.approx(5.75)


def test_night_warning_threshold_applies_floor():
    # Seven nights at 0.3 kWh, one at 2.0 kWh: Q1=Q3=median=0.3, IQR=0, so
    # tau = max(0.3, 2*0.3, 0.3 + 1.0) = 1.3 (the +1.0 kWh floor wins)
    night_totals = [0.3, 0.3, 0.3, 0.3, 0.3, 0.3, 0.3, 2.0]
    assert night_warning_threshold(night_totals) == pytest.approx(1.3)


def test_warning_severity_matches_manual_calculation():
    # Manual calc: 20.0 / 5.75 = 3.478...
    assert warning_severity(20.0, 5.75) == pytest.approx(3.478, abs=0.001)


def test_warning_severity_zero_threshold_returns_zero():
    assert warning_severity(10.0, 0.0) == 0.0


def test_classify_warning_bands():
    assert classify_warning(3.478) == "warning"
    assert classify_warning(1.25) == "warning"
    assert classify_warning(1.1) == "notice"
    assert classify_warning(1.0) == "in_line"
    assert classify_warning(0.5) == "in_line"
