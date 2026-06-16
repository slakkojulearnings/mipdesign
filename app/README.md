# MIP App — React UI + FastAPI

A full-stack app over the MIP engine. The **FastAPI backend** (`mip.api`) reuses the
same scanner/parser/queries as the CLI and scans the real source at
`<repo-root>/source_mf_code`. The **React (Vite) frontend** is an elegant, insight-first
explorer.

```
source_mf_code/  ──scan──►  mip engine  ──►  FastAPI (/api/*)  ──►  React UI
```

## Run it (two terminals, dev)

```bash
# 1) backend  (from reference-implementation/)
cd ../reference-implementation
uv pip install -e ".[dev,api]"
uv run uvicorn mip.api:app --reload --port 8000

# 2) frontend (from app/frontend/)
cd ../app/frontend
npm install
npm run dev          # opens http://localhost:5173  (proxies /api -> :8000)
```

## Run it (one process, prod)

Run one line at a time (Windows PowerShell doesn't support `&&`). From `app/frontend`:
```
npm install
npm run build                          # builds dist/
cd ../../reference-implementation
uv run uvicorn mip.api:app --port 8000 # serves API + the built UI
```
Then open http://localhost:8000

The backend auto-scans `source_mf_code` on first request. Drop real mainframe code in
that folder (or set `MIP_SOURCE=/path`) and click **↻ Rescan**.

## API

| Endpoint | Purpose |
|---|---|
| `POST /api/scan` | (re)scan the source estate |
| `GET /api/summary` | counts + inventory breakdown |
| `GET /api/programs` · `GET /api/program/{id}` · `…/profile` | program list / detail / 360° profile + AST |
| `GET /api/jobs` · `/api/roots` · `/api/deadcode` | jobs, root drivers, dead code |
| `GET /api/graph` · `/api/insights` | call/execution graph + insights |
| `GET /api/capabilities` | inferred business capabilities |
| `POST /api/query` | NL question → answer + reasoning trace + full profile (logged) |
| `GET /api/log` · `/api/log/raw` | Q&A audit log (also written to `question_log.md`) |
| `GET /api/source?path=` | raw member source (evidence viewer) |

See **USER_MANUAL.md** for what each screen does.
