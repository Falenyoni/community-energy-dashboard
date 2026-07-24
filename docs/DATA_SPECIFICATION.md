# Simulated Smart-Controller Data Specification

Formal field specification per proposal Section C.3 / Table 3, satisfying
Objective 1's deliverable. This is the **canonical schema** every data source
(simulated generator, manual CSV import, future approved API) must conform to
before ingestion — see `docs/ARCHITECTURE_DECISIONS.md` for how the pipeline
stays source-agnostic around this contract.

## Fields

| Field | Type | Unit / Format | Range / Rule | Notes |
|---|---|---|---|---|
| `reading_id` | string | UUID or `<device_id>_<timestamp>` | must be unique | required, primary key of a reading |
| `site_id` | string | anonymised label, e.g. `SITE-003` | — | no personal address/name; groups readings by household/community site |
| `device_id` | string | e.g. `SITE-003-CH2` | — | identifies the monitored load / controller channel instance |
| `controller_channel` | enum (text) | one of: `geyser`, `fridge`, `lighting`, `plugs`, `cooking`, `background` | must be one of the defined categories | used for device ranking/comparison |
| `timestamp` | datetime | ISO 8601, UTC | must be parseable; strictly increasing per `device_id` | interval/trend/peak calculations key off this |
| `voltage_v` | numeric | volts | 207–253 V (± 10% of 230V nominal SA supply) | outside range → `quality_flag = out_of_range` |
| `current_a` | numeric | amperes | ≥ 0; upper bound per device category (see below) | must be consistent with `power_kw` and `voltage_v` where power factor is simulated |
| `power_kw` | numeric | kilowatts | ≥ 0; upper bound per device category | primary value for energy calculation |
| `energy_kwh_interval` | numeric | kWh | ≥ 0; ≈ `power_kw × Δt` (Δt = 0.25h for 15-min intervals) | checked against manual calculation for accuracy validation |
| `cumulative_energy_kwh` | numeric | kWh | monotonically non-decreasing per `device_id` (unless reset) | optional but used for consistency checks |
| `switching_state` | enum (text) | one of: `on`, `off`, `standby`, `fault` | — | supports abnormal-use interpretation |
| `quality_flag` | enum (text) | one of: `valid`, `missing`, `duplicate`, `out_of_range`, `abnormal_event` | — | prevents poor data from silently distorting analytics |

## Typical power ranges per controller channel

Used to generate realistic simulated values and to bound range checks:

| Channel | Typical power range (kW) | Notes |
|---|---|---|
| `geyser` | 0 (off) – 3.0 | large step change when on; long on-durations are a common abnormal-use scenario |
| `fridge` | 0.05 – 0.3 | short, frequent cycling |
| `lighting` | 0.01 – 0.5 | depends on number of fixtures on the channel |
| `plugs` | 0.02 – 2.0 | most variable category; catches small appliances |
| `cooking` | 0 – 3.5 | short high-power bursts |
| `background` | 0.01 – 0.15 | standby/always-on loads; unusually high values flagged as abnormal |

## Data completeness

`η = valid readings received / expected readings for the selected interval`

Expected readings for a 30-day, 15-minute-interval dataset: 2,880 per
`device_id`. Missing-interval detection compares actual timestamps present
against this expected count.

## Deliberately injected scenarios (for testing, not real conditions)

The generator must inject known cases so the validation and analytics layers
can be tested against expected outputs, not just "clean" data:

- **Missing readings** — simulated communication gap (a run of absent
  intervals for one `device_id`).
- **Duplicate readings** — same `reading_id`/`device_id`+`timestamp` repeated,
  simulating a repeated import.
- **Out-of-range values** — voltage or power outside the bounds above.
- **Abnormal-use events** — e.g. a `geyser` channel with an unusually long
  `on` duration, a `fridge` with excessive cycling, a `plugs`/`background`
  channel staying `on` overnight at high draw.

## Schema diagram

See `docs/ARCHITECTURE_DECISIONS.md` repository structure and the proposal's
Figure 5 (Core relational data model) / Table 5 (Core database entities) for
how `reading` rows relate to `site`, `smart_controller_channel`,
`daily_summary`, `comparison_result` and `audit_log`. The database model
implementing this is the next step (SQLAlchemy models matching Table 5).
