# Technical Concepts Q&A

Running collection of "why does this work this way" questions asked while
building this project, answered for future reference — interview prep and
presentation defense included. Newest entries at the bottom of each section.

## SQLAlchemy / ORM

### Is there a specific way to define SQLAlchemy model classes?

Yes — the convention used in `backend/app/models.py` is SQLAlchemy 2.0's
current recommended style: `DeclarativeBase` + `Mapped[]` type annotations +
`mapped_column()`:
```python
class Site(Base):
    __tablename__ = "sites"
    site_id: Mapped[str] = mapped_column(String, primary_key=True)
```
This replaced the older `declarative_base()` + plain `Column()` style still
common in pre-2023 tutorials. Not the *only* valid way, but the current
idiomatic one, and it gives type-checking on model fields for free.

### Can model classes be split into separate files?

Yes, and it's common practice once a project grows past a handful of models.
The one hard rule: every model must share the **same `Base`** class, because
Alembic's `target_metadata = Base.metadata` (see `alembic/env.py`) only sees
tables registered on that one `Base` — a model on a different `Base` instance
would be silently invisible to autogenerate.

Typical pattern:
```
app/models/
  __init__.py      # defines Base, imports + re-exports everything below
  site.py          # Site
  channel.py       # SmartControllerChannel
  reading.py       # Reading, DailySummary
  analytics.py     # ComparisonResult
  audit.py         # User, AuditLog
```
`__init__.py` importing every file (even just to re-export) is what
guarantees all tables get registered on `Base` before anything reads
`Base.metadata` — this is the main gotcha of splitting: a model file that's
never imported anywhere never registers its table.

This project currently keeps all 6 models in one `models.py` (small enough
that splitting isn't worth the import-order bookkeeping yet) — worth
revisiting once adding models regularly makes one file unwieldy.

### Is SQLAlchemy/Alembic the only ORM/migration option in Python?

No — several alternatives exist, each with different trade-offs:

**ORMs:**
| ORM | Notes |
|---|---|
| **SQLAlchemy** (used here) | Most mature and flexible; framework-agnostic; steeper API surface. Industry-standard choice for Flask/FastAPI projects. |
| **Django ORM** | Built into Django, tightly coupled to it — can't easily use it outside a Django project. Has its own built-in migrations system (no separate Alembic-equivalent needed). |
| **SQLModel** | Built by the same author as FastAPI (Sebastián Ramírez). Combines a Pydantic model and a SQLAlchemy model into *one* class definition, removing the duplication between "API validation schema" and "database model." Designed specifically to pair with FastAPI — worth knowing as the most natural alternative for this exact stack. Uses Alembic for migrations too (it's built on SQLAlchemy under the hood). |
| **Tortoise ORM** | Async-native from the ground up, API deliberately similar to Django's ORM. Popular in async FastAPI projects. Uses **Aerich** for migrations, not Alembic. |
| **Peewee** | Small, simple, good for lightweight scripts/small apps; less common in production API backends. |

**Migration tools:**
| Tool | Pairs with |
|---|---|
| **Alembic** (used here) | SQLAlchemy / SQLModel |
| Django migrations | Django ORM only |
| Aerich | Tortoise ORM |
| yoyo-migrations | Framework-agnostic, raw SQL based |

Why SQLAlchemy + Alembic for this project specifically: it's the most
widely-used, most documented combination for FastAPI, has synchronous support
(simpler to reason about than async ORM code for a first backend project),
and Alembic's autogenerate + versioned migration history directly supports
the "schema-enforced database tables" language in Objective 2.

### Does the FastAPI server need to be running to use the CLI ingestion script?

No. `backend/app/ingestion/ingest.py` connects to Postgres **directly**
through `app/database.py`'s SQLAlchemy engine — it has no dependency on
`uvicorn` or any HTTP endpoint. It's a second, independent entry point into
the same codebase: the FastAPI app (`app/main.py`) and the CLI script both
import the same `app/database.py` (connection/session) and `app/models.py`
(table definitions), but neither one depends on the other being started.
Same principle as Alembic in the question above — one shared data layer,
multiple independent things that can use it (a web server, a CLI script, a
migration tool). The only shared requirement is a reachable database at
whatever `DATABASE_URL` is set in `backend/.env`.

### Why didn't the frontend's live row count move while ingestion was clearly running?

This is a transaction-isolation question, not a bug in the frontend polling.
SQLAlchemy's `flush()` sends pending INSERTs to Postgres, but they only
become part of the **current, still-open transaction** — they are not
durable or visible elsewhere yet. `commit()` is the step that actually ends
the transaction and makes its changes visible to other connections.

Postgres's default isolation level, **READ COMMITTED**, means any other
connection (like the frontend's `/stats/reading-count` query, running in its
own separate session) can only ever see data from **committed** transactions
— never another transaction's flushed-but-uncommitted writes, no matter how
long that transaction has been open or how much work it's already done
internally.

The original ingestion script called `db.commit()` exactly once, at the very
end, after all ~172,800 rows were processed — so every row was genuinely
being written from the script's own point of view, but invisible to
literally every other connection (the frontend, a `psql` session, anything)
until that single final commit. The fix was to commit periodically (every
1,000 rows) during the loop, so partial progress becomes visible to other
connections as it happens, not just once the whole run finishes.

**If asked**: "Doesn't committing partway through risk leaving inconsistent
data if the script crashes mid-run?" — no more than any batch-import process:
each commit only finalizes rows already fully validated and added to the
session at that point, so a crash after a partial commit leaves a valid
(if incomplete) subset of correctly-validated data, not corrupted rows. The
next run's `existing_reading_ids` check (see the ingestion CLI answer above)
correctly picks up from whatever was truly committed, since it's re-queried
fresh at the start of each run.
