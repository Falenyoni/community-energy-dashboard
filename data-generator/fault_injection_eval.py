"""
Large-scale fault-injection + hold-out evaluation for the paper's Results
section. Builds two independent 30-day datasets (A = calibration, B =
hold-out) on top of generate_rows()/apply_injections(), injects data-quality
faults (duplicates, out-of-range voltage, negative power, isolated missing
readings, one multi-channel communication gap) and abnormal-use events at
a larger, statistically meaningful scale, runs them through the REAL
validators (classify_reading, fill_short_gaps) and the REAL A8 functions
(daily_warning_threshold, night_warning_threshold, warning_severity,
classify_warning), and reports genuine measured numbers -- nothing here is
backfilled to match a target.

Usage:
    python fault_injection_eval.py
"""
import os
import random
import sys
from datetime import timedelta

sys.path.insert(0, os.path.dirname(__file__))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "backend"))

from generate import (  # noqa: E402
    CHANNELS,
    DAYS,
    INTERVALS_PER_DAY,
    SITE_COUNT,
    apply_injections,
    generate_rows,
)

from app.ingestion.validators import (  # noqa: E402
    classify_reading,
    fill_short_gaps,
)
from app.ingestion.schemas import RawReading  # noqa: E402
from app.analytics.calculations import (  # noqa: E402
    classify_warning,
    daily_warning_threshold,
    night_warning_threshold,
    warning_severity,
)
from datetime import datetime as _dt  # noqa: E402

GAP_HOURS = 4
GAP_INTERVALS = GAP_HOURS * 60 // 15  # 16
N_DUPLICATE = 200
N_OOR_VOLTAGE = 30
N_NEGATIVE_POWER = 10
N_ISOLATED_MISSING = 550
N_ABNORMAL_DAY_EVENTS = 20
N_ABNORMAL_NIGHT_EVENTS = 10


def build_dataset(seed: int, fault_seed: int):
    rows = generate_rows(seed)
    rows, _base_log = apply_injections(rows)
    rng = random.Random(fault_seed)

    valid_idx = [i for i, r in enumerate(rows) if r["quality_flag"] == "valid"]
    used = set()

    def sample(pool, n):
        chosen = rng.sample(pool, n)
        used.update(chosen)
        return chosen

    neg_idx = sample([i for i in valid_idx if i not in used], N_NEGATIVE_POWER)
    for i in neg_idx:
        rows[i]["power_kw"] = -abs(rows[i]["power_kw"]) - 0.1

    oor_idx = sample([i for i in valid_idx if i not in used], N_OOR_VOLTAGE)
    for i in oor_idx:
        rows[i]["voltage_v"] = rng.choice([180.0, 290.0])

    dup_src_idx = sample([i for i in valid_idx if i not in used], N_DUPLICATE)
    dup_rows = []
    for i in dup_src_idx:
        dup = dict(rows[i])
        dup["reading_id"] = dup["reading_id"] + "-DUP"
        dup_rows.append(dup)

    # Isolated missing readings: single-interval gaps, each with at least
    # one real reading on both sides and not adjacent to another dropped
    # reading (so they stay genuinely "isolated", short gaps).
    candidates = [i for i in valid_idx if i not in used]
    rng.shuffle(candidates)
    missing_idx = []
    dropped_keys = set()
    for i in candidates:
        if len(missing_idx) >= N_ISOLATED_MISSING:
            break
        r = rows[i]
        key = (r["device_id"], r["_dt"])
        prev_key = (r["device_id"], r["_dt"] - timedelta(minutes=15))
        next_key = (r["device_id"], r["_dt"] + timedelta(minutes=15))
        if prev_key in dropped_keys or next_key in dropped_keys:
            continue
        missing_idx.append(i)
        dropped_keys.add(key)
    used.update(missing_idx)

    # One 4-hour communication gap across all 6 channels of one site.
    gap_site_index = rng.randrange(SITE_COUNT)
    gap_day = rng.randrange(DAYS)
    gap_start = rng.randrange(INTERVALS_PER_DAY - GAP_INTERVALS)
    gap_idx = []
    for i, r in enumerate(rows):
        if i in used:
            continue
        if r["_site_index"] != gap_site_index or r["_day_index"] != gap_day:
            continue
        interval = _interval_of(r)
        if gap_start <= interval < gap_start + GAP_INTERVALS:
            gap_idx.append(i)
    used.update(gap_idx)

    drop_idx = set(missing_idx) | set(gap_idx)

    # Abnormal-use events: scale a whole day's (or just 00:00-05:00's)
    # power for one (site,channel,day) by a random factor so some are
    # clear positives (>=2x) and some are borderline (~1.1-1.3x), giving a
    # realistic mix instead of only easy cases.
    device_ids = sorted({r["device_id"] for r in rows})
    all_day_keys = [(d, day) for d in device_ids for day in range(DAYS)]
    rng.shuffle(all_day_keys)

    day_events = {}
    night_events = {}
    event_keys = iter(all_day_keys)
    for _ in range(N_ABNORMAL_DAY_EVENTS):
        device_id, day = next(event_keys)
        factor = rng.choice([1.15, 1.3, 1.8, 2.5, 3.5])
        day_events[(device_id, day)] = factor
    for _ in range(N_ABNORMAL_NIGHT_EVENTS):
        device_id, day = next(event_keys)
        factor = rng.choice([1.2, 1.5, 2.0, 3.0])
        night_events[(device_id, day)] = factor

    for r in rows:
        key = (r["device_id"], r["_day_index"])
        hour = r["_dt"].hour
        if key in day_events:
            r["power_kw"] = round(r["power_kw"] * day_events[key], 4)
            r["energy_kwh_interval"] = round(r["power_kw"] * 0.25, 5)
        if key in night_events and 0 <= hour < 5:
            r["power_kw"] = round(r["power_kw"] * night_events[key], 4)
            r["energy_kwh_interval"] = round(r["power_kw"] * 0.25, 5)

    kept = [r for i, r in enumerate(rows) if i not in drop_idx]
    kept.extend(dup_rows)

    ground_truth = {
        "negative_power": {(rows[i]["device_id"], rows[i]["_dt"]) for i in neg_idx},
        "oor_voltage": {(rows[i]["device_id"], rows[i]["_dt"]) for i in oor_idx},
        "duplicate": {(r["device_id"], r["_dt"]) for r in dup_rows},
        "isolated_missing": {(rows[i]["device_id"], rows[i]["_dt"]) for i in missing_idx},
        "gap_4h": {(rows[i]["device_id"], rows[i]["_dt"]) for i in gap_idx},
        "day_events": day_events,
        "night_events": night_events,
    }
    # True "clean" energy per device-day, from BEFORE fault injection
    # (for the monthly-energy-error measurement) -- computed off a fresh,
    # unfaulted generation with the same seed so the numbers line up.
    clean_rows = generate_rows(seed)
    clean_by_device = {}
    for r in clean_rows:
        clean_by_device.setdefault(r["device_id"], 0.0)
        clean_by_device[r["device_id"]] += r["energy_kwh_interval"]

    return kept, ground_truth, clean_by_device


def _interval_of(row) -> int:
    dt = row["_dt"]
    return dt.hour * 4 + dt.minute // 15


def run_validation(rows):
    """Runs every row through the real classify_reading(), mirroring what
    fast_ingest.py does, and returns (counts, valid_readings_by_device,
    flagged_keys_by_type)."""
    seen_keys = set()
    counts = {}
    valid_by_device = {}
    flagged = {"duplicate": set(), "out_of_range": set(), "missing": set()}

    rows_sorted = sorted(rows, key=lambda r: (r["device_id"], r["timestamp"]))
    for r in rows_sorted:
        reading = RawReading(
            reading_id=r["reading_id"],
            site_id=r["site_id"],
            device_id=r["device_id"],
            controller_channel=r["controller_channel"],
            timestamp=_dt.fromisoformat(r["timestamp"].replace("Z", "+00:00")),
            voltage_v=r["voltage_v"],
            current_a=r["current_a"],
            power_kw=r["power_kw"],
            energy_kwh_interval=r["energy_kwh_interval"],
            cumulative_energy_kwh=r["cumulative_energy_kwh"],
            switching_state=r["switching_state"],
        )
        flag = classify_reading(reading, seen_keys)
        counts[flag] = counts.get(flag, 0) + 1
        if flag in flagged:
            flagged[flag].add((reading.device_id, reading.timestamp))
        if flag == "valid":
            valid_by_device.setdefault(reading.device_id, []).append(
                (reading.timestamp, reading.power_kw)
            )

    return counts, valid_by_device, flagged


def evaluate_dataset(label: str, seed: int, fault_seed: int):
    print(f"\n=== Dataset {label} (seed={seed}, fault_seed={fault_seed}) ===")
    rows, ground_truth, clean_by_device = build_dataset(seed, fault_seed)
    total_injected_rows = len(rows)
    print(f"Total rows after injection: {total_injected_rows:,}")

    counts, valid_by_device, flagged = run_validation(rows)
    print("classify_reading() counts:", counts)

    # --- Table II: detection accuracy per fault type ---
    def hit_rate(name, truth_set, flagged_set):
        detected = len(truth_set & flagged_set)
        print(f"  {name}: injected={len(truth_set)} detected={detected}")
        return detected

    print("\nFault detection:")
    hit_rate("duplicate", ground_truth["duplicate"], flagged["duplicate"])
    hit_rate(
        "negative_power",
        ground_truth["negative_power"],
        flagged["out_of_range"],
    )
    hit_rate(
        "oor_voltage",
        ground_truth["oor_voltage"],
        flagged["out_of_range"],
    )

    # --- Gap handling: fill_short_gaps on the real valid-reading set ---
    imputed_count = 0
    imputed_keys = set()
    for device_id, readings in valid_by_device.items():
        for gap_row in fill_short_gaps(device_id, readings):
            imputed_count += 1
            imputed_keys.add((device_id, gap_row["timestamp"]))
    isolated_missing_imputed = len(ground_truth["isolated_missing"] & imputed_keys)
    gap4h_imputed = len(ground_truth["gap_4h"] & imputed_keys)
    print(f"\nGap handling: {imputed_count} readings imputed total")
    print(
        f"  of {len(ground_truth['isolated_missing'])} isolated missing, "
        f"{isolated_missing_imputed} were imputed"
    )
    print(
        f"  of {len(ground_truth['gap_4h'])} 4h-gap readings, "
        f"{gap4h_imputed} were imputed (should be 0 -- gap > 2 intervals)"
    )

    # --- Completeness ---
    # expected = valid + out_of_range + missing + the two dropped-row
    # categories (duplicates don't occupy a new expected slot; dropped
    # rows do).
    n_valid = counts.get("valid", 0)
    n_oor = counts.get("out_of_range", 0)
    n_missing_flagged = counts.get("missing", 0)
    expected_total = n_valid + n_oor + n_missing_flagged + len(ground_truth["isolated_missing"]) + len(
        ground_truth["gap_4h"]
    )
    completeness_excl_impute = round((n_valid + n_oor) / expected_total, 4)
    completeness_incl_impute = round(
        (n_valid + n_oor + imputed_count) / expected_total, 4
    )
    print(f"\nCompleteness (excluding imputed as valid): {completeness_excl_impute:.2%}")
    print(f"Completeness (including imputed as valid): {completeness_incl_impute:.2%}")

    # --- Monthly energy error: exclude-missing vs with-interpolation ---
    errors_excl = []
    errors_incl = []
    valid_energy_by_device = {}
    imputed_energy_by_device = {}
    for device_id, readings in valid_by_device.items():
        valid_energy_by_device[device_id] = sum(p * 0.25 for _, p in readings)
    for device_id, readings in valid_by_device.items():
        extra = sum(
            g["power_kw"] * 0.25
            for g in fill_short_gaps(device_id, readings)
        )
        imputed_energy_by_device[device_id] = extra

    for device_id, clean_kwh in clean_by_device.items():
        excl_kwh = valid_energy_by_device.get(device_id, 0.0)
        incl_kwh = excl_kwh + imputed_energy_by_device.get(device_id, 0.0)
        if clean_kwh > 0:
            errors_excl.append(abs(excl_kwh - clean_kwh) / clean_kwh)
            errors_incl.append(abs(incl_kwh - clean_kwh) / clean_kwh)

    mean_err_excl = sum(errors_excl) / len(errors_excl)
    max_err_excl = max(errors_excl)
    mean_err_incl = sum(errors_incl) / len(errors_incl)
    max_err_incl = max(errors_incl)
    print(
        f"\nMonthly energy error, excluded-missing: mean={mean_err_excl:.4%} max={max_err_excl:.4%}"
    )
    print(
        f"Monthly energy error, with interpolation: mean={mean_err_incl:.4%} max={max_err_incl:.4%}"
    )

    return {
        "rows": rows,
        "ground_truth": ground_truth,
        "valid_by_device": valid_by_device,
        "counts": counts,
    }


def compute_device_day_totals(rows):
    """device_id -> list of (day_index, total_kwh) for 'valid' rows only."""
    totals = {}
    for r in rows:
        if r["quality_flag"] != "valid":
            continue
        key = r["device_id"]
        totals.setdefault(key, {})
        totals[key].setdefault(r["_day_index"], 0.0)
        totals[key][r["_day_index"]] += r["energy_kwh_interval"]
    return {k: [v[d] for d in sorted(v)] for k, v in totals.items()}


def compute_device_night_totals(rows):
    totals = {}
    for r in rows:
        if r["quality_flag"] != "valid":
            continue
        if not (0 <= r["_dt"].hour < 5):
            continue
        key = r["device_id"]
        totals.setdefault(key, {})
        totals[key].setdefault(r["_day_index"], 0.0)
        totals[key][r["_day_index"]] += r["energy_kwh_interval"]
    return {k: [v[d] for d in sorted(v)] for k, v in totals.items()}


def warning_eval(label, calib_rows, calib_truth, test_rows, test_truth, stage1_only):
    """
    Computes tau per device from calib_rows (Dataset A), then classifies
    every device-day (and device-night) in test_rows (Dataset B) as a
    positive-ground-truth case (an injected day/night event) or negative,
    and a predicted-warning case (severity >= 1.25, or stage1_only: any s > 1.0).
    Returns (precision, recall, tp, fp, fn, tn).
    """
    calib_daily = compute_device_day_totals(calib_rows)
    calib_night = compute_device_night_totals(calib_rows)

    tau_daily = {d: daily_warning_threshold(vals) for d, vals in calib_daily.items()}
    tau_night = {d: night_warning_threshold(vals) for d, vals in calib_night.items()}

    test_daily = {}
    for r in test_rows:
        if r["quality_flag"] != "valid":
            continue
        test_daily.setdefault(r["device_id"], {}).setdefault(r["_day_index"], 0.0)
        test_daily[r["device_id"]][r["_day_index"]] += r["energy_kwh_interval"]

    test_night = {}
    for r in test_rows:
        if r["quality_flag"] != "valid":
            continue
        if not (0 <= r["_dt"].hour < 5):
            continue
        test_night.setdefault(r["device_id"], {}).setdefault(r["_day_index"], 0.0)
        test_night[r["device_id"]][r["_day_index"]] += r["energy_kwh_interval"]

    positive_keys = set(test_truth["day_events"].keys()) | set(test_truth["night_events"].keys())

    tp = fp = fn = tn = 0
    for device_id, by_day in test_daily.items():
        tau_d = tau_daily.get(device_id)
        tau_n = tau_night.get(device_id)
        for day, total in by_day.items():
            is_positive = (device_id, day) in positive_keys
            predicted = False
            if tau_d:
                s = warning_severity(total, tau_d)
                if stage1_only:
                    predicted = predicted or s > 1.0
                else:
                    predicted = predicted or classify_warning(s) == "warning"
            night_total = test_night.get(device_id, {}).get(day)
            if night_total is not None and tau_n:
                s_n = warning_severity(night_total, tau_n)
                if stage1_only:
                    predicted = predicted or s_n > 1.0
                else:
                    predicted = predicted or classify_warning(s_n) == "warning"

            if is_positive and predicted:
                tp += 1
            elif is_positive and not predicted:
                fn += 1
            elif not is_positive and predicted:
                fp += 1
            else:
                tn += 1

    precision = tp / (tp + fp) if (tp + fp) else 0.0
    recall = tp / (tp + fn) if (tp + fn) else 0.0
    print(f"\n[{label}] stage1_only={stage1_only}: TP={tp} FP={fp} FN={fn} TN={tn}")
    print(f"[{label}] precision={precision:.3f} recall={recall:.3f}")
    return precision, recall, tp, fp, fn, tn


def main():
    result_a = evaluate_dataset("A (calibration)", seed=42, fault_seed=2026)
    result_b = evaluate_dataset("B (hold-out)", seed=777, fault_seed=9999)

    print("\n\n=== Warning performance: calibrated on A, evaluated on B ===")
    warning_eval(
        "stage 1 only (s>1.0 raised as warning)",
        result_a["rows"],
        result_a["ground_truth"],
        result_b["rows"],
        result_b["ground_truth"],
        stage1_only=True,
    )
    warning_eval(
        "two-stage (s>=1.25, plus night rule)",
        result_a["rows"],
        result_a["ground_truth"],
        result_b["rows"],
        result_b["ground_truth"],
        stage1_only=False,
    )

    print("\n\n=== Warning performance: evaluated on A itself (in-sample, for reference) ===")
    warning_eval(
        "stage 1 only, in-sample on A",
        result_a["rows"],
        result_a["ground_truth"],
        result_a["rows"],
        result_a["ground_truth"],
        stage1_only=True,
    )
    warning_eval(
        "two-stage, in-sample on A",
        result_a["rows"],
        result_a["ground_truth"],
        result_a["rows"],
        result_a["ground_truth"],
        stage1_only=False,
    )


if __name__ == "__main__":
    main()
