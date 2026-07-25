# Code Walkthrough

Plain-language explanation of what each part of the codebase does and why,
written for presentation/defense — updated as new modules are added. Pairs
with `TECH_CONCEPTS_QA.md` (general concepts) and `DATA_SPECIFICATION.md`
(the field spec this code implements).

## The request/data flow, end to end

```
CSV file  →  ingest.py (CLI)  →  RawReading (validation)  →  classify_reading()
          →  SQLAlchemy models  →  Postgres  ←  FastAPI (app/main.py)  ←  React frontend
```

Two independent entry points share one data layer: the CLI ingestion script
and the FastAPI web server. Neither depends on the other running (see
`TECH_CONCEPTS_QA.md`).

## `backend/app/config.py` — Settings

A `pydantic_settings.BaseSettings` subclass. Reads `DATABASE_URL` and
`CORS_ORIGINS` from environment variables (or a `.env` file locally).
`get_settings()` is wrapped in `@lru_cache` so the file is only read once per
process, not on every request. Both `app/main.py` and `alembic/env.py` call
this same function — one source of truth for "what database are we talking
to," everywhere in the codebase.

**If asked**: "Why Pydantic Settings instead of `os.environ.get(...)`
everywhere?" — centralizes config in one typed place, validates it once at
startup instead of failing deep in some unrelated function later, and keeps
secrets out of code (they come from `.env`/the hosting platform's env vars,
never hardcoded).

## `backend/app/database.py` — engine, session, connectivity check

- `engine` — the SQLAlchemy object that actually knows how to talk to
  Postgres. `pool_pre_ping=True` means it tests a connection is still alive
  before handing it out, so a dropped connection (e.g. after the database
  was idle) doesn't surface as a confusing error later.
- `SessionLocal` — a factory for database sessions (a session ≈ one unit of
  work: some queries, maybe a commit).
- `get_db()` — a generator FastAPI uses as a "dependency": opens a session,
  hands it to a route function, and guarantees it's closed afterward even if
  the route raises an exception.
- `check_db_connection()` — runs a literal `SELECT 1`. This is what
  `/health/db` calls; it's the difference between "the server process is
  running" and "the server can actually reach the database."

## `backend/app/models.py` — the database schema, as Python

Six SQLAlchemy model classes, one per Table 5 entity: `User`, `Site`,
`SmartControllerChannel`, `Reading`, `DailySummary`, `ComparisonResult`,
`AuditLog`. Uses SQLAlchemy 2.0's typed style (`Mapped[]` /
`mapped_column()`) — see `TECH_CONCEPTS_QA.md` for why.

Three module-level tuples (`CONTROLLER_CHANNELS`, `SWITCHING_STATES`,
`QUALITY_FLAGS`) define the allowed enum values once, and get wired into
`CheckConstraint`s on `SmartControllerChannel` and `Reading`. This means the
allowed values (`geyser`/`fridge`/etc., `valid`/`missing`/etc.) are enforced
**by Postgres itself** — even a bug in application code that tried to insert
`controller_channel = "toaster"` would be rejected at the database level, not
just caught by application validation.

**If asked**: "Why enforce this in the database AND in Pydantic?" — Pydantic
(`ingestion/schemas.py`) catches bad data early with a readable error before
it ever reaches the database; the `CheckConstraint`s are a second,
independent safety net in case something ever writes to the database another
way (a future admin script, a bug, direct SQL). Defense in depth, not
redundancy for its own sake.

## `backend/alembic/` — turning `models.py` into real tables

Covered in full in `ALEMBIC_EXPLAINED.md`. One-line summary: Alembic diffs
`models.py` against the live database and generates/runs the SQL to make
them match, keeping a versioned history of every schema change.

## `backend/app/ingestion/schemas.py` — the canonical contract

`RawReading` is a Pydantic model listing exactly the fields from
`DATA_SPECIFICATION.md`. This is the single shape every data source must
conform to — whether it's the simulated generator, a manually exported real
CSV, or a future API integration. `quality_flag` is deliberately **excluded**
from this model: it's computed fresh by the validators, never trusted from
whatever produced the CSV (a real device export wouldn't self-report
"abnormal_event" anyway).

**If asked**: "What happens if a CSV has an extra column, or is missing
one?" — extra columns are silently ignored (Pydantic v2 default); a missing
*required* column (anything without `= None`) makes that row fail validation
and get rejected with a readable error, without crashing the whole import.

## `backend/app/ingestion/validators.py` — the actual quality rules

- `classify_reading()` — assigns one `quality_flag` to a single parsed
  reading, in order: duplicate check first (same `device_id` + `timestamp`
  seen already in this run), then missing (voltage or power is null), then
  out-of-range (voltage outside 207-253V, or power outside a per-channel
  ceiling), else `valid`.
- `expected_reading_count()` — given a time span and an interval (15 min
  default), how many readings *should* exist. Used with the actual count to
  compute completeness.
- `completeness_ratio()` — implements η from `DATA_SPECIFICATION.md`:
  actual ÷ expected.

**If asked**: "How do you detect a reading that's completely missing, if
there's no row for it?" — you can't flag a row that doesn't exist; instead,
completeness is computed at the device level by comparing how many readings
exist across a time span against how many *should* exist for that span at a
fixed interval. A single missing value inside an existing row (blank cell)
is different — that's the `missing` quality_flag on a row that IS present.

## `backend/app/ingestion/ingest.py` — the CLI pipeline

Run as `python -m app.ingestion.ingest path/to/file.csv`. Step by step:

1. Opens the CSV with `csv.DictReader` (each row becomes a dict).
2. `clean_row()` converts empty-string cells to `None`, since CSVs have no
   native concept of "null" — otherwise Pydantic would try to parse `""` as
   a float and fail.
3. Parses each row into a `RawReading`. If validation fails (bad type,
   missing required field), the row is recorded in `rejected` and the loop
   **continues** rather than crashing — this is what makes "zero unhandled
   errors" true even against a messy file.
4. `classify_reading()` assigns the quality flag.
5. `get_or_create_site()` / `get_or_create_channel()` — if this is the first
   reading seen for a given site/device, create the parent row; otherwise
   reuse it. This means you don't need to pre-populate sites/channels
   separately — ingesting readings is enough.
6. Checks whether this exact `reading_id` already exists before inserting —
   makes re-running the same file on the same data safe (won't error on a
   primary-key clash), while a *duplicate* with a *different* `reading_id`
   at the same timestamp still gets inserted and flagged, so analytics can
   filter it out later rather than losing the evidence it happened.
7. After the loop: one commit, then a single `AuditLog` row summarizing the
   whole run (counts by flag, rejected count) — the audit trail objective 2
   asks for.
8. Prints a human-readable summary, including the per-device completeness
   check.

**If asked live to explain a specific number in the output**: "`valid=7`" is
a count of rows that passed every check; "`rows=10`" is total rows read
including rejects; the per-device completeness lines are computed
independently of the flag counts, from the actual timestamps observed for
that device.

**If asked**: "Why load `existing_reading_ids` into memory up front instead
of checking the database per row?" — this is the classic **N+1 query
problem**: checking "does this reading already exist?" one row at a time
means one network round-trip per row. Against a remote database, at
~172,800 rows, that's 172,800 round-trips just to answer a question that
one query up front (`SELECT reading_id FROM readings`) answers for the
whole file at once — checking set membership afterward is then pure
in-memory work (fast, no I/O). The original version of this script did the
per-row check and would have taken well over an hour on the full dataset;
this was caught and fixed before running it at scale, not after waiting.
`get_or_create_site`/`get_or_create_channel` don't have this problem because
there are only ~10 sites and ~60 devices total, and SQLAlchemy's session
identity map caches each one after its first lookup within a run — but
every `reading_id` is unique, so there's nothing to cache, which is exactly
why that check needed a different approach.

## `backend/app/routers/stats.py` — first analytics-style endpoint

`GET /stats/reading-count` — a single `COUNT(*)` query over the `readings`
table. Small on purpose: it's the first entry in what will become the
analytics router (Objective 3's baseline/peak/ranking/cost endpoints follow
the same `routers/` pattern), and it exists right now specifically to give
live visual feedback in the frontend while a large ingestion is running,
rather than staring at a silent terminal.

`app/main.py` wires it in with `app.include_router(stats.router)` — this is
the pattern every future router (ingestion upload endpoint, analytics
endpoints) will follow: define an `APIRouter` in its own file under
`routers/`, include it once in `main.py`. Keeps `main.py` itself from
growing into one large file as more endpoints are added.

The frontend (`App.jsx`) polls this endpoint every 3 seconds via
`setInterval` in its own `useEffect`, independent of the API/DB health
checks — so the count keeps climbing on screen during a long-running
ingestion without needing a manual "Re-check" click.

## `data-generator/generate.py` — the simulated dataset

Produces the CSV that gets fed into the ingestion pipeline above. Standard
library only (no pandas/numpy) — the per-device running state (cumulative
energy, per-channel randomness) fits a plain loop more naturally than
vectorised array operations would.

Structure:

1. **Per-channel power functions** (`geyser_power`, `fridge_power`, etc.) —
   each encodes a plausible daily pattern: geyser cycles morning/evening
   only, fridge cycles constantly regardless of time, lighting peaks in the
   evening, cooking bursts at meal times, background is a near-constant low
   baseline. Each site also has a `low`/`medium`/`high` usage profile
   (a multiplier applied uniformly across its channels) so peer comparison
   later has real variation to compare against, not near-identical sites.
2. **`derive_current()`** — computes `current_a` from `power_kw` and
   `voltage_v` using an assumed power factor per channel (`P = V x I x PF`,
   rearranged for `I`), so the three electrical values stay internally
   consistent rather than being independently randomised.
3. **`apply_injections()`** — six *fixed*, documented scenarios (not
   randomly placed each run): a missing-readings gap, a duplicate reading,
   an out-of-range voltage, and three abnormal-use events (long geyser
   runtime, rapid fridge cycling, high overnight background draw). Fixed
   locations mean the expected effect on ingestion output is knowable in
   advance and reproducible — this is what "controlled validation" (Section
   C.5) means in practice: you can state before running ingestion that
   exactly one row should come out `duplicate`, exactly one `out_of_range`,
   and so on, then confirm the pipeline actually produces that.

**If asked**: "Why fixed injection locations instead of randomizing them
each run?" — reproducibility. A randomly-placed bug either shows up or it
doesn't on a given run, which is a weak demo. A fixed, named scenario
("SITE-003-PLUGS, day 8, 09:30, voltage forced to 268V") is something you
can state as an expected outcome *before* running ingestion and then point
at the exact matching row in the output — that's what makes it evidence
rather than a coincidence.

**If asked**: "How do you know the simulated values are realistic?" — the
per-channel power ranges come from `DATA_SPECIFICATION.md`'s typical-range
table, and the time-of-day logic (geyser morning/evening peaks, cooking at
meal times, lighting in the evening) mirrors documented household load-shape
research cited in the proposal's literature review (Toussaint 2020; Ritchie,
Engelbrecht & Booysen 2022), not arbitrary numbers.

**Verified result** (a good one to cite directly in your defense): running
the full 172,800-row generated dataset through ingestion initially produced
`out_of_range=2058` — far more than the two intentionally-injected anomalies.
Root cause: `generate.py` scales power by a site's usage profile (up to 1.5x
for "high" usage) and a weekend boost (up to another 1.15x for some
channels), but `validators.py`'s power ceilings were set from the base
typical ranges without accounting for that scaling — so realistic high-usage
readings were being misclassified as bad data. Recalculating each channel's
true legitimate maximum (typical x 1.5 x 1.15 where applicable) and raising
the ceilings accordingly brought the count to exactly **21** — precisely
`1` (the injected out-of-range voltage) `+ 20` (the injected abnormal
overnight background draw), with every other row correctly `valid`. This is
the kind of discrepancy that only shows up at realistic dataset scale, not
in a small hand-written test file — which is itself worth mentioning if
asked why both a tiny fixture and a full-scale run were used to validate
the pipeline.
