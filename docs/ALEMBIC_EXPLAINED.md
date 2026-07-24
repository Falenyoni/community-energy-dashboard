# What is Alembic?

Plain-language explainer for the tool wired up in `backend/alembic/` and used
to create the database tables. Written so you can explain this in your
presentation without needing to look anything up.

## The problem it solves

Your database schema (`backend/app/models.py`) changes over time — you add a
table, add a column, rename a field. Somehow that change has to actually
happen *inside* Postgres itself: Python classes don't create tables just by
existing, something has to run `CREATE TABLE ...` (or `ALTER TABLE ...`) SQL
against the real database.

You could write that SQL by hand every time. Alembic's job is to generate and
run it for you, and — more importantly — to keep a **version history** of
every schema change, the same way Git keeps a version history of your code.

## Where it fits

Alembic is a companion tool to **SQLAlchemy** (both maintained by the same
author, Mike Bayer). SQLAlchemy is the ORM — it lets you describe database
tables as Python classes (`backend/app/models.py`: `Site`, `Reading`, etc.).
Alembic reads those same class definitions and figures out what SQL is needed
to make a real database match them.

```
models.py (Python classes)  →  Alembic compares this to the live database
                             →  generates a "migration" (a versioned Python
                                file containing the SQL diff)
                             →  you run it, database now matches models.py
```

## Key concepts

- **Migration / revision**: one versioned step of schema change, stored as a
  Python file in `backend/alembic/versions/`. Each one has an `upgrade()`
  function (apply this change) and a `downgrade()` function (undo it).
- **Revision history**: migrations are chained — each new one points at the
  previous one (`down_revision`), forming a linked list. This is what makes
  it "version control for your schema."
- **`alembic_version` table**: Alembic creates this one extra table in your
  actual Postgres database. It stores a single row: the ID of whichever
  migration was applied last. That's how `alembic current` knows what state
  the database is in, and how `alembic upgrade head` knows which migrations
  it still needs to run.
- **Autogenerate**: Alembic can inspect the live database, compare it against
  your `models.py`, and write the migration file for you — you don't
  hand-write the `CREATE TABLE` SQL. This is what `--autogenerate` does. It's
  a diffing tool, not magic — always worth reading the generated file before
  applying it, since autogenerate can miss some kinds of changes (e.g. it
  won't detect a column rename; it'll see that as "drop one column, add a
  different one").

## The commands you ran, explained

```powershell
alembic revision --autogenerate -m "initial schema"
```
Alembic connects to the database (empty, at that point), compares it to
`Base.metadata` in `models.py`, sees six tables that exist in Python but not
in Postgres, and writes a new file in `alembic/versions/` containing the
`op.create_table(...)` calls to create all six.

```powershell
alembic upgrade head
```
"Head" means "the latest known migration." This actually connects to Postgres
and runs the SQL from that generated file — this is the step that created
your real tables. It then writes that migration's ID into the `alembic_version`
table so Alembic knows it's been applied.

```powershell
alembic current
```
Reads the `alembic_version` table and prints which migration the database is
currently at — a sanity check that the upgrade actually took effect.

## Why this matters for the project

- **Reproducibility**: anyone (a supervisor, a marker, future-you on a new
  laptop) can clone the repo, point `DATABASE_URL` at an empty database, run
  `alembic upgrade head`, and get the exact same schema — no manual SQL, no
  "did I remember every column" risk.
- **Auditability**: the `alembic/versions/` folder is a literal history of
  every schema change and when it happened, which supports the "documented,
  schema-enforced database tables" language in Objective 2.
- **Safety net**: if a future schema change breaks something, `downgrade()`
  gives you a defined way back, rather than manually reverse-engineering what
  to undo.

## Configuration in this project

Two files, working together:

**`backend/alembic.ini`** — static settings: `script_location = alembic` (where
`env.py`/`versions/` live), `prepend_sys_path = .` (so `env.py` can
`import app...`), plus logging config. Deliberately has **no**
`sqlalchemy.url` line — a default `alembic init` scaffold puts the database
URL here directly, which would mean a real password living in a plain,
likely-committed `.ini` file.

**`backend/alembic/env.py`** — a real Python script Alembic executes on every
command. The two lines that matter:

```python
settings = get_settings()
config.set_main_option("sqlalchemy.url", settings.database_url)

target_metadata = Base.metadata
```

- `get_settings()` is the *same* function `app/main.py` uses — it reads
  `DATABASE_URL` from whichever `backend/.env` is active. Alembic and the API
  always point at the same database, from one source of truth; switching
  `.env` moves both without separate config.
- `target_metadata = Base.metadata` is the literal `Base` class the ORM
  models (`Site`, `Reading`, etc. in `models.py`) inherit from — it's what
  `--autogenerate` diffs the live database against. Add a model or column,
  and the next autogenerate run picks it up with no other config change.

## What happens when the schema changes later

Whenever `models.py` changes (new table, new column, etc.), the pattern
repeats: `alembic revision --autogenerate -m "description of the change"`,
read the generated file, then `alembic upgrade head`. Each of those is a new
file in `versions/`, chained onto the last one.
