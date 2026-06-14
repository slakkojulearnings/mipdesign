# MIP — Setup, Run, Test & Evaluate (on a fresh machine)

Step-by-step to clone, run, and evaluate MIP on any machine. Everything is pure-Python
at runtime (plus Node for the UI). No mainframe and no network required.

---

## 1. Prerequisites

| Tool | Version | Install |
|------|---------|---------|
| Git | any | https://git-scm.com |
| Python | **3.13+** | https://python.org |
| uv | latest | `pip install uv` or https://docs.astral.sh/uv |
| Node.js | **18+** | https://nodejs.org (only for the web UI) |

Check:
```bash
python --version    # 3.13+
uv --version
node --version      # 18+
```

## 2. Clone

```bash
git clone https://github.com/slakkojulearnings/mipdesign.git
cd mipdesign
```

## 3. Set up the engine

```bash
cd reference-implementation
uv venv --python 3.13
uv pip install -e ".[dev,api]"      # engine + tests + API + NetworkX
```

## 4. Run the engine (CLI)

```bash
# scan the bundled estate (or any folder of mainframe source)
uv run mip scan ../source_mf_code

uv run mip query "which jobs execute CRDPOST"     # -> DAILYCRD
uv run mip query "what does PAYUPD write"
uv run mip query "tell me everything about INTDRV"
uv run mip roots                                  # true entry points
uv run mip dead                                   # dead-code candidates
```

## 5. Run the web app

```bash
# build the UI (from repo root)
cd ../app/frontend
npm install
npm run build

# serve API + UI on one port (from reference-implementation)
cd ../../reference-implementation
uv run uvicorn mip.api:app --port 8000
# open http://localhost:8000
```
Dev mode (hot reload) instead: `npm run dev` in `app/frontend` (proxies to the API on
:8000, which you run separately with `uvicorn`).

Explore: **Dashboard · Programs · Capabilities · Jobs · Call Graph** (click a node →
profile + AST; click an edge → evidence) **· Root Programs · Dead Code · Query Console ·
Q&A Log**. Each program page has an **Impact / blast radius** analysis (NetworkX).

## 6. Test

```bash
cd reference-implementation
uv run pytest -q                          # 9 tests: ground-truth + graph layer
python ../03-skills/validate_catalog.py   # skills <-> catalog in sync (12 skills)
```

Expected: `9 passed`, and the validator prints `OK — 12 skills valid …`.

## 7. Evaluate the quality (it measures itself)

- **Precision / recall** against a hand-labeled ground truth:
  ```bash
  cd reference-implementation
  uv run python tests/test_groundtruth.py
  # prints: precision = 1.000  recall = 1.000  + roots / dead code / needs_review
  ```
  This proves the extracted call graph, jobs, copybooks, and tables match the known
  truth for the sample estate, and that the dynamic `CALL WS-VAR` is kept as
  `needs_review` (never asserted) — MIP's core resilience guarantee.

- **Impact / blast radius** (NetworkX), e.g. "what breaks if CARD_MASTER changes":
  ```bash
  uv run python -c "from mip import store, graphx; from mip.pipeline import build_db; \
build_db('../source_mf_code','e.db'); c=store.connect('e.db'); \
import json; print(json.dumps(graphx.blast_radius(c,'CARD_MASTER'), indent=2))"
  ```

- **Capabilities** inferred from the artifacts: open the **Capabilities** tab, or
  `GET /api/capabilities`. Each is confidence-scored and flagged `inferred`.

## 8. Point it at your own / a real estate

Drop real mainframe source (COBOL/JCL/copybooks/DB2 — extensions optional) into
`source_mf_code/`, then re-scan (`mip scan ../source_mf_code`) or click **↻ Rescan** in
the UI. To try a real public corpus:

```bash
git clone -b experimentation \
  https://github.com/hpatel-appliedai/aws-mainframe-modernization-carddemo
uv run mip scan aws-mainframe-modernization-carddemo
```
Or set `MIP_SOURCE=/path/to/estate` before starting the API. Real-world repos exercise
the documented v0.1 limits (regex parsing, no `COPY REPLACING`, CICS/IMS out of scope) —
that's expected; the gaps become measurable rather than hidden.

## Troubleshooting

- **`mip` not found** → activate the venv or prefix with `uv run`.
- **UI shows nothing / API errors** → ensure the API is running on :8000 and you ran
  `mip scan` (the API also auto-scans `source_mf_code` on first request).
- **PageRank/impact errors** → install the API/graph extra (`uv pip install -e ".[api]"`)
  which includes NetworkX.
- **Windows line-ending warnings** on commit are harmless.
