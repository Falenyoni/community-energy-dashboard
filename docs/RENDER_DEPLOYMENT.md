# Render Deployment Guide

Consolidated steps for deploying and troubleshooting this project on Render.
Companion to `docs/ARCHITECTURE_DECISIONS.md` (which explains *why* Render/this
stack was chosen). Written so this can be reproduced solo, without assistant
help, e.g. at a presentation.

Live services:
- Backend API: https://community-energy-dashboard.onrender.com
- Frontend: https://community-energy-dashboard-frontend.onrender.com

## Architecture

Three separate Render services:

1. **PostgreSQL** — managed database.
2. **Web Service** (backend) — FastAPI + Uvicorn, root directory `backend`.
3. **Static Site** (frontend) — React/Vite build, root directory `frontend`.

## 1. PostgreSQL

Render dashboard → **New** → **PostgreSQL**.
- Name it (e.g. `community-energy-dashboard`).
- Free tier is fine for the prototype — **note: free-tier Postgres expires
  after 30 days** unless upgraded. Track this against the project timeline
  (Feb–Oct 2026).

Once created, the instance's **Connect/Info** page gives you two connection
strings:
- **Internal Database URL** — short hostname (e.g. `dpg-xxxx-a`), only
  resolvable from *within* Render's network. Use this for the backend Web
  Service's `DATABASE_URL`.
- **External Database URL** — full hostname with a region suffix (e.g.
  `dpg-xxxx-a.virginia-postgres.render.com`), reachable from anywhere,
  including your laptop. Use this for local development (`backend/.env`).

Both are in standard SQLAlchemy/libpq URL form:
```
postgresql://<username>:<password>@<host>[:5432]/<database>
```

## 2. Backend Web Service

Render dashboard → **New** → **Web Service** → connect the GitHub repo.

| Setting | Value |
|---|---|
| Root Directory | `backend` |
| Runtime | Python 3 |
| Build Command | `pip install -r requirements.txt` |
| Start Command | `uvicorn app.main:app --host 0.0.0.0 --port $PORT` |

**About `$PORT`**: you don't set this yourself. Render injects a `PORT` env
var automatically at runtime; `$PORT` in the Start Command just reads it.
Type the literal string `$PORT`, not a hardcoded port number.

**Environment variables to set:**
- `DATABASE_URL` = the **Internal** Database URL from step 1.
- `CORS_ORIGINS` = comma-separated list of allowed origins, e.g.:
  ```
  http://localhost:5173,https://community-energy-dashboard-frontend.onrender.com
  ```
  (no trailing slash on the deployed URL)

## 3. Frontend Static Site

Render dashboard → **New** → **Static Site** → same GitHub repo.

| Setting | Value |
|---|---|
| Root Directory | `frontend` |
| Build Command | `npm install && npm run build` |
| Publish Directory | `dist` |

**Environment variable:**
- `VITE_API_URL` = the backend Web Service's URL, e.g.
  `https://community-energy-dashboard.onrender.com`

Important: Vite bakes `VITE_`-prefixed env vars into the JS bundle **at build
time**, not read at runtime. Set this *before* the first build, and trigger a
new build any time it changes.

## 4. Verification

```powershell
Invoke-RestMethod https://community-energy-dashboard.onrender.com/health
Invoke-RestMethod https://community-energy-dashboard.onrender.com/health/db
```
Then open the frontend URL and confirm both status rows show ✅.

## Viewing logs

- **Backend (Web Service)**: has real runtime logs. Dashboard → service →
  **Logs** tab streams live server output (requests, exceptions, `print`/
  `logging` calls).
- **Frontend (Static Site)**: has **no runtime logs**. It's pre-built files
  served from a CDN — nothing executes server-side. Its **Logs** tab only
  shows the one-time build output. For anything happening once the page is
  loaded (blank page, failed fetch, CORS errors), open the deployed URL in a
  browser and check DevTools (F12) → **Console** and **Network** tabs.

## Troubleshooting log — issues hit during setup

| Symptom | Cause | Fix |
|---|---|---|
| Build fails: `pydantic-core` metadata generation error, `maturin failed`, `Read-only file system` on a Cargo cache path | Render defaulted to a very new Python version (3.14.x) with no prebuilt wheel yet for `pydantic-core`; pip fell back to compiling it from source via Rust/maturin, which failed on Render's read-only build filesystem | Add `backend/.python-version` pinning to `3.12.7` (or another version with prebuilt wheels for everything in `requirements.txt`) |
| Runtime crash: `sqlalchemy.exc.ArgumentError: Could not parse SQLAlchemy URL from string 'Host=...;Port=...;Database=...'` | `DATABASE_URL` was pasted in ADO.NET-style format (`Key=Value;...`) instead of a URL | Replace with the actual `postgresql://user:pass@host/db` string copied directly from Render's Postgres Connect page — don't hand-reconstruct it |
| Browser console: `Access to fetch at '.../health' from origin '...' has been blocked by CORS policy` | Backend's `CORS_ORIGINS` env var didn't include the deployed frontend's origin | Update `CORS_ORIGINS` on the backend Web Service to include the frontend's exact deployed URL (comma-separated if keeping `localhost` too), save, let it auto-redeploy |

## Known constraints

- Free-tier Postgres expires after 30 days — re-provision or upgrade before
  then.
- Free-tier Web Services spin down after inactivity (~30-60s cold start on
  the next request) — expected, not a bug; worth mentioning before a live
  demo so a slow first request doesn't look like a failure.
- Render auto-deploys both services on every push to `main` — no GitHub
  Actions needed for basic CI/CD. Revisit only if/when automated tests should
  gate a deploy.
