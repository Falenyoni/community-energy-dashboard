# Real-data validation: London Smart Meter dataset

Date: 2026-11-02

## Why

The simulated generator (`data-generator/generate.py`) proves the pipeline is
internally consistent, but every household in it comes from the same three
usage-profile multipliers (0.6 / 1.0 / 1.5x). That can't show how the
pipeline, validation rules and comparative analytics behave against
genuinely independent, messy household data. This is a first pass at
validating against a public, open-licensed dataset instead of waiting on
more live CBi devices.

## Source

- **Dataset:** Low Carbon London smart meter trial (UK Power Networks),
  published via the London Datastore:
  https://data.london.gov.uk/dataset/smartmeter-energy-use-data-in-london-households
- **File used:** `Partitioned LCL Data.zip` (168 CSV chunks of ~1M rows
  each, ~795MB zipped / ~8.5GB unzipped total) — only one chunk
  (`LCL-June2015v2_0.csv`) was downloaded and used.
- **Licence:** released by UK Power Networks, redistributed under
  Creative Commons Attribution (CC-BY).
- **Shape:** `LCLid, stdorToU, DateTime, KWH/hh (per half hour)` — one row
  per household per half-hour, November 2011 - February 2014. No
  per-appliance breakdown, no voltage/current telemetry — just whole-house
  energy.

## Selection

From the one chunk used (30 households), 16 had a fully gap-free, non-null
run across the same calendar window: **2011-12-15 to 2012-01-14** (30 days,
matching the simulated dataset's 30-day shape). 10 of those 16 were picked
for parity with the simulated dataset's 10 sites:

`MAC000016, 18, 19, 20, 21, 24, 25, 26, 27, 28` -> `LDN-000016 ... LDN-000028`

## Schema change required

The existing `RawReading` schema assumes a smart-controller channel
(geyser/fridge/lighting/plugs/cooking/background) with voltage and current.
Whole-house meter data doesn't fit that:

- Added a 7th channel type, **`whole_house`**, to
  `CONTROLLER_CHANNELS` (`app/models.py`), the `ControllerChannel` literal
  (`app/ingestion/schemas.py`), and the DB check constraint (migration
  `6fba427fd828`).
- `voltage_v`/`current_a` are left `NULL` for these readings — not
  fabricated. `validators.classify_reading()` was adjusted so the
  voltage-range check only runs when a voltage is actually present; only a
  missing `power_kw` counts as a `"missing"` reading now. This is a
  genuinely more correct rule for a multi-source pipeline (a source that
  never measures voltage isn't the same as a source that failed to report
  it), not a special case bolted on for this dataset.
- A sanity ceiling of 25kW was set for `whole_house` in
  `CHANNEL_MAX_POWER_KW` — near a single-phase UK domestic main-fuse limit
  (~23kW at 230V/100A), since there's no generator profile to calibrate
  against.

## Conversion

`KWH/hh` (energy for the half-hour) converts directly: `power_kw = kwh * 2`,
`energy_kwh_interval = kwh`, `cumulative_energy_kwh` accumulated per
household. `switching_state` is a derived heuristic (`on` above 0.1kW,
`standby` above 0kW, `off` at 0kW) — there's no real switching telemetry in
this source, so this is an approximation, not a measurement.

## Findings

**Data quality:** 14,410 rows ingested, 14,400 valid, **10 duplicates**, 0
missing, 0 out-of-range. The 10 duplicates are not random — every single
household has exactly one duplicate row, all at the same timestamp
(`2011-12-15T00:00:00`), the first half-hour of the chosen window. That's a
systematic boundary artifact in how the source file compiles daily data, not
noise — a good example of a real-world data-quality issue a simulator
would never produce. The pipeline's existing duplicate detector caught all
10 correctly without any changes.

**Comparative scale:** real monthly totals ranged from **134.5 kWh to
839.0 kWh** across the 10 households — a 6.2x spread. The simulated
dataset's spread (low/medium/high profile tiers) is only ~2.5x
(730/1,210/1,820 kWh) by construction. Real households are far more
heterogeneous than three fixed multipliers can represent.

**Comparison methodology (same limitation as the simulated data, more
extreme here):** with no peer-group/usage-tier structure for real
households (there isn't one to assign), the whole-community-average
comparison produces ratios from **0.247 to 4.255**. The highest-use
household (`LDN-000024`, 839 kWh) shows as "above_average" by up to 4.26x
on some days purely because it's compared against a community average
dragged down by much smaller households — the same Schultz et al.
(2007)-style misleading-comparison effect already flagged for the
simulated data, but sharper here because real households vary more than
the simulator's profile tiers do.

**Pipeline compatibility:** no changes were needed to `ingest.py`,
`calculations.py`, or the daily-summary/comparison compute step — only the
schema/validator extension above. `app/ingestion/ingest.py`'s console
completeness printout assumes a 15-minute interval (the simulator's
cadence) and reports a misleading "50.0%" for this half-hourly source; the
actual completeness, checked independently before ingestion, is 100%
(1,440/1,440 expected half-hour slots per household). This is a minor,
cosmetic gap in that one print statement, not a correctness issue in the
stored data.

## Limitations

- Only one of 168 available chunks was used (10 of ~5,567 available
  households) — a convenience sample for a time-boxed check, not a
  representative one.
- No per-appliance breakdown, voltage, or current for these households —
  several dashboard features (device-level ranking within a site,
  per-channel heatmap) only mean something when a site has more than one
  channel; right now every real site has exactly one (`whole_house`).
- `switching_state` is a derived heuristic, not a measurement.
- UK household load shapes/tariffs do not represent South African
  households — this validates pipeline *mechanics* (ingestion, validation,
  storage, analytics), not South African usage patterns.
