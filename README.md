# Community Energy Monitoring Dashboard

Web-based community energy monitoring dashboard with comparative analytics,
using simulated smart circuit controller (CBi Astute-style) data.

BET Hons Electrical Engineering project — B. Nyoni, 260119806.
Full proposal: `Bongani_Nyoni_260119806_Proposal.pdf`.
Stack and hosting decisions: `docs/ARCHITECTURE_DECISIONS.md`.

## Structure

- `data-generator/` — simulated smart-controller dataset generation
- `backend/` — FastAPI ingestion, validation, storage and analytics API
- `frontend/` — React dashboard (Vite)
- `docs/` — decisions, data specification, evaluation reports

## Local development

**Backend**
```
cd backend
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
cp .env.example .env
uvicorn app.main:app --reload
```

**Frontend**
```
cd frontend
npm install
npm run dev
```
