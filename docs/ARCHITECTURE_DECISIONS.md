# Architecture Decisions

Decisions made for the Community Energy Monitoring Dashboard (BET Hons project,
B. Nyoni, 260119806). Reference: `Bongani_Nyoni_260119806_Proposal.pdf`.

## Stack

| Layer | Choice | Why |
|---|---|---|
| Backend | **FastAPI** (Python) | Pydantic models give request/response validation for free — doubles as the documented validation layer required by Objective 2. Auto-generated OpenAPI/Swagger docs (`/docs`) support the documented-analytics requirement in Objective 3 (formula, inputs, outputs per endpoint). Async fits an ingestion + analytics API better than Flask's sync-by-default model, without Django's unneeded admin/ORM overhead. |
| Frontend | **React** (Vite) | Matches proposal's dashboard requirement (5+ chart types, 4 KPI cards, peer-comparison panel, CSV/PDF export, responsive ≥320px). More setup than Streamlit but demonstrates web dashboard design distinct from the backend, as the proposal's evaluation criteria expect. |
| Database | **PostgreSQL** | Matches the proposal's stated fallback for larger datasets / multi-user testing (Section C.4). Used from the start rather than starting on SQLite and migrating, to avoid a migration step later. |
| Dataset generation | Python script (pandas/numpy) | Produces the simulated smart-controller dataset per Table 3 field spec; output is CSV, ingested through the same pipeline real exports would use. |

## Hosting: Render

Three services:

1. **Static Site** — React production build, served from Render's CDN.
2. **Web Service** — FastAPI + Uvicorn, connects to Postgres via Render's internal
   connection string (env var, never committed).
3. **PostgreSQL** — Render managed Postgres.

**Known constraints:**
- Render's free-tier Postgres expires after 30 days unless upgraded — relevant given
  the project runs Feb–Oct 2026; plan to re-provision or upgrade before it lapses.
- Free-tier web services spin down after inactivity (~30-60s cold start on next
  request) — expected behavior, not a bug, worth flagging before a live demo.
- CORS must be configured on the FastAPI service to allow the static site's origin.

## Repository structure (planned)

```
community-energy-dashboard/
├── backend/          # FastAPI app: ingestion, validation, analytics, API routes
├── frontend/          # React (Vite) dashboard
├── data-generator/    # Simulated smart-controller dataset generation scripts
├── docs/              # This file, data specification, evaluation reports
└── Bongani_Nyoni_260119806_Proposal.pdf
```

## Working process

Development proceeds in small, reviewable steps. Each step is implemented and
described, then the user reviews and runs `git add` / `git commit` themselves —
commits are not created by the assistant unless explicitly asked.

## Open questions / to revisit

- Tariff structure for cost estimation (Section C.3, `C = E × tariff`) — which
  municipality/Eskom tariff to use as the default configurable rate.
- Whether the optional forecasting/XAI extension (Section C.2, table row
  "Optional extension") gets attempted at all, given it's explicitly out of the
  minimum deliverable set.
