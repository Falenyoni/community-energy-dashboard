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
