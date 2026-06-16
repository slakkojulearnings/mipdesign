# MIP — Mainframe Intelligence Platform

> **Understand the system before you transform it.** MIP turns a legacy mainframe estate
> (COBOL, JCL, copybooks, DB2, CICS, CSD) into queryable, evidence-backed knowledge — so
> a new engineer answers in seconds what used to take weeks of SME time. Every fact
> carries **evidence + a confidence**; anything inferred is flagged, never asserted.

```
Source Code → Inventory → Metadata → Knowledge Graph → Reasoning → Copilot → Modernization
              (never skip a layer; AI consumes facts, it doesn't invent them)
```

- **Engine** — `reference-implementation/` (Python 3.13, stdlib-only runtime; optional extras)
- **Web app** — `app/` (FastAPI API + React/Vite UI)
- **Your code goes in** — `source_mf_code/` (or point `MIP_SOURCE` anywhere)
- **Tests** — **90 passing** (engine + graph + parser + app endpoints); advanced ANTLR backend parity **28**
- **Repo design** — `00-foundation/` … `05-build-plan/`, the 12 skills in `03-skills/`, prompts in `04-prompts/`

For a screen-by-screen tour see [`app/USER_MANUAL.md`](app/USER_MANUAL.md); for leadership-facing
samples see [`docs/showcase/`](docs/showcase/); fresh-machine steps in [`readme_setup.md`](readme_setup.md).

---

## 1. Setup

Prereqs: **Python 3.13+**, **uv** (`pip install uv`), **Node 18+** (UI only), git.

> **Shell note (Windows PowerShell):** commands are listed **one per line** — run them one
> at a time. Windows PowerShell 5.1 does **not** support `&&`; use `;` to chain on one line,
> or just paste each line separately. Set environment variables with `$env:NAME="value"`
> (PowerShell) or `NAME=value cmd` (bash/zsh). Paths use forward slashes, which work in both.

```
git clone https://github.com/slakkojulearnings/mipdesign.git
cd mipdesign/reference-implementation
uv venv --python 3.13
uv pip install -e ".[dev,api]"
# optional: uv pip install -e ".[dev,api,advanced]"   # adds the ANTLR runtime for MIP_PARSER=advanced
```

## 2. Run the engine (CLI)

```bash
# scan ANY estate — the sample, your real code in ../source_mf_code, or any path
uv run mip scan ../source_mf_code        # inventory + parse + load SQLite (writes mip.db)

uv run mip query "which jobs execute CRDPOST"     # → DAILYCRD
uv run mip query "what does AUTHTRAN call"        # online CICS LINK → AUTHVAL
uv run mip roots                                  # batch + online entry points
uv run mip dead                                   # dead-code candidates
```

## 3. Run the web app

Run these one at a time. Starting from `reference-implementation` (where step 1 left you):

```
cd ../app/frontend
npm install
npm run build
cd ../../reference-implementation
uv run uvicorn mip.api:app --port 8000
```
Then open http://localhost:8000 — the API serves the built UI on the same port.
(Dev mode with hot reload: run `npm run dev` inside `app/frontend` in a second terminal.)
Screens: Dashboard · Programs (search/sort/facets) · Capabilities (→ **Capability Requirements**:
BR + FR rollup, export to Markdown) · Jobs · **Call Graph** (zoom/pan, confidence slider, edge
filter, clickable edges with evidence, keyboard/ARIA) · Roots · Dead Code · **Query Console**
(deep-linkable `#/query?q=…`, logged reasoning) · **Q&A Log** · plus per-program **Sequence
diagram**, **Field-lineage diagram**, **Impact/blast-radius**, **Business rules**, **Export**
(JSON/CSV/GraphML) and click-to-evidence drill-down.

The top bar shows the active **parser backend** (`default` / `advanced`) and lets you switch it
— switching re-parses the estate. It reflects `/api/health` and only enables `advanced` when the
ANTLR backend is installed/built.

**Render the graph to a standalone file** (the in-app Call Graph already visualizes the same
NetworkX graph; this is for a slide/export). From `reference-implementation`:
```
uv pip install -e ".[viz]"                    # adds pyvis + matplotlib (one-time)
uv run python scripts/draw_graph.py --source ../source_mf_code --out graph.html
```
Writes an interactive HTML (pyvis — alongside a `lib/` folder of viewer assets, git-ignored),
or a PNG (matplotlib) if pyvis is absent. With neither, it points you to **GraphML** (Export menu
/ `/api/export?format=graphml`) for Gephi/yEd/Cytoscape.

## 4. Configuration (environment variables)

| Var | Default | Effect |
|-----|---------|--------|
| `MIP_SOURCE` | `<repo>/source_mf_code` | estate the API scans |
| `MIP_PARSER` | `default` | `advanced` uses the ANTLR COBOL-85 backend if built, else falls back (see [ADVANCED_PARSER.md](reference-implementation/ADVANCED_PARSER.md)) |
| `MIP_WORKERS` | all CPU cores | parse parallelism (`1` forces serial) |
| `MIP_BINARY_LIBS` | — | comma-separated extra compiled-library folder names treated as binary |

Set them before the command that uses them — for example, to scan with 8 workers:
```
# PowerShell:  $env:MIP_WORKERS="8"  (then run the command on the next line)
# bash/zsh:    MIP_WORKERS=8 uv run mip scan ../source_mf_code
```

---

## 5. Test the complete functionality

Run everything (one line at a time). From `reference-implementation`:
```
uv run pytest -q                              # 90 passing
uv run python ../03-skills/validate_catalog.py   # skills ⇄ catalog in sync (12 skills)
```
Then confirm the UI compiles (from the repo root):
```
cd app/frontend
npm run build
```

Per-capability (each maps to a test you can run on its own):

| Capability | How to see it work | Test |
|------------|--------------------|------|
| Discovery, roots, dead code, precision/recall | `uv run python tests/test_groundtruth.py` (prints metrics) | `test_groundtruth.py` |
| Grammar parser / AST, dynamic-call resolution, arithmetic + group-move lineage | `uv run pytest tests/test_parser.py -q` | `test_parser.py` |
| Adaptive content-driven classification + `profile_estate` + binary detection | `uv run pytest tests/test_scanner_adaptive.py tests/test_scanner_binary.py -q` | `test_scanner_*.py` |
| Knowledge graph: blast radius, PageRank, Louvain communities | `uv run pytest tests/test_graphx.py -q` | `test_graphx.py` |
| Field-level data lineage (SQL host-var ↔ column) | part of `test_parser.py` + `GET /api/program/STMTDRV/lineage` | `test_parser.py` |
| Business-rule extraction | `uv run pytest tests/test_rules.py -q` | `test_rules.py` |
| Capability requirements (BR + FR rollup, triggers, data access) | `uv run pytest tests/test_capability_requirements.py -q` | `test_capability_requirements.py` |
| Online layer: CICS + CSD transaction→program | `uv run pytest tests/test_cics.py tests/test_csd.py -q` | `test_cics.py`, `test_csd.py` |
| Runtime-evidence correlation | `uv run pytest tests/test_runtime.py -q` | `test_runtime.py` |
| Global search | `uv run pytest tests/test_search.py -q` | `test_search.py` |
| Export (JSON/CSV/GraphML) + Mermaid sequence diagrams | `uv run pytest tests/test_export.py tests/test_sequence.py -q` | `test_export.py`, `test_sequence.py` |
| Advanced ANTLR COBOL-85 backend (parity + COPY/REPLACING) | set `MIP_PARSER=advanced` (see shell note above), then `uv run pytest tests/test_antlr_backend.py tests/test_groundtruth.py -q` | `test_antlr_backend.py` |
| Parallel parsing == serial (180K-scale) | `uv run pytest tests/test_parallel.py -q` | `test_parallel.py` |
| Scan/insert performance | `uv run pytest tests/test_perf.py -q` ; `uv run python scripts/benchmark_scan.py` | `test_perf.py` |

Smoke-test the API surface (27 endpoints) without the UI. Save this as `smoke.py` in
`reference-implementation`, then run `uv run python smoke.py` (works in any shell):
```python
from fastapi.testclient import TestClient
from mip.api import app
c = TestClient(app); c.post("/api/scan")
print("health   :", c.get("/api/health").json()["parser"])
print("summary  :", c.get("/api/summary").json())
print("rules    :", [r["kind"] for r in c.get("/api/program/CRDVAL/rules").json()["rules"]])
print("impact   :", sorted(x["id"] for x in c.get("/api/program/CARD_MASTER/impact").json()["impacted"]))
print("sequence :", c.get("/api/program/AUTHTRAN/sequence").json()["participants"])
print("search   :", [(x["kind"], x["id"]) for x in c.get("/api/search?q=AUTH").json()["results"]])
print("runtime  :", c.get("/api/runtime").json().get("reconciliation", {}).get("summary"))
print("cap req  :", c.get("/api/capability/CRDPOST/requirements").json()["summary"])
print("parser   :", c.post("/api/parser?mode=default").json()["parser"])
```

## 6. Try it on a real / larger estate

Drop real COBOL/JCL/copybooks/CSD into `source_mf_code/` (extensions optional), then from
`reference-implementation`:
```
uv run mip scan ../source_mf_code
```
Or pull a public corpus (the clone lands in the current folder, so scan that same name):
```
git clone -b experimentation https://github.com/hpatel-appliedai/aws-mainframe-modernization-carddemo
# PowerShell — set workers, then scan:
$env:MIP_WORKERS="8"
uv run mip scan aws-mainframe-modernization-carddemo
# bash/zsh equivalent:  MIP_WORKERS=8 uv run mip scan aws-mainframe-modernization-carddemo
```
Inspect the learned folder map (no hardcoded folder names):
```
uv run python -c "import json; from mip import scanner; print(json.dumps(scanner.profile_estate('../source_mf_code'), indent=2))"
```
Scale notes: scanning reads only a 64 KB header per file and skips binaries fast; inserts
are bulk/transactional; parsing fans out across cores (`MIP_WORKERS`); classification is
learned per-folder so new/renamed folders need no code change. See
[`00-foundation/ARCHITECTURE.md`](00-foundation/ARCHITECTURE.md) for the honest scale plan
(NetworkX/SQLite limits + the trigger/target to move to a graph DB).

---

## 7. How skills and agents were used

MIP uses "agents and skills" in **two distinct senses** — the platform's own skill/agent
assets, and the Claude Code agents that *built* it. Both are captured here.

### 7a. MIP skills (the platform's personas/charters)
`03-skills/` holds **12 skills** written to the **Agent Skills standard**
([agentskills.io](https://agentskills.io/specification)) — each is a folder with a
`SKILL.md` (`name` + `description` frontmatter). They define *who does what* and the rules
every contributor (human or AI) follows; the prompts in `04-prompts/` invoke them, and the
engine implements them.

- **[`skills.catalog.json`](03-skills/skills.catalog.json)** is the registry mapping each
  skill → the prompts that invoke it → the tools/code that implement it, plus a `status`
  (`implemented` / `partial` / `specified`). Run **`python 03-skills/validate_catalog.py`**
  to confirm folders ⇄ catalog stay 1:1 (CI enforces this).
- Skill → code, e.g.: `mainframe-code-analyst` → scanner/`cobol_ast`; `graph-engineer` →
  `graphx` (blast radius, PageRank, Louvain); `metadata-modeler`/`sqlite-engineer` →
  `models.py`/`schema.sql`/`store.py`; `business-capability-analyst` → `queries.capabilities`;
  `resilience-engineer` → dead-code/runtime; `test-engineer` → the test suite.
- All inherit [`03-skills/MIP_ENGINEERING_PRINCIPLES.md`](03-skills/MIP_ENGINEERING_PRINCIPLES.md)
  (evidence + confidence, graceful degradation, explainability). `03-skills/modernization-leverage/`
  adds common community roles (incl. the Karpathy engineering guidelines that shape `CLAUDE.md`).

### 7b. Project agents (Claude Code, ship with the repo)
[`.claude/agents/`](.claude/agents/) defines two subagents available to anyone using Claude
Code in this repo (also mirrored into `.claude/skills/` so Claude Code auto-discovers the
12 skills):
- **`mip-discovery`** — runs the engine to inventory/graph/root/dead-code/capability-map an
  estate and explain findings with evidence + confidence.
- **`mip-modernization-architect`** — turns that evidence into an incremental, low-risk
  modernization plan (extract lowest-blast-radius capability first), citing the evidence.

### 7c. How agents built this platform (multi-agent orchestration)
The implementation was produced by **fanning out parallel Claude Code subagents with
strictly disjoint file ownership** so they never clobber each other, then integrating +
verifying centrally. Representative waves:
- **Feature pairs in parallel** — e.g. business-rule extraction (backend) ‖ router+search
  (frontend); ANTLR backend ‖ runtime-evidence correlation; scan-performance ‖
  binary-artifact classification. Each agent owned a non-overlapping set of files and was
  given the exact API contracts so the halves lined up on first integration.
- **Adversarial code review** — a dedicated review subagent audited new parser/graph code
  and found 4 real correctness/honesty bugs (fabricated lineage edges, a false dead-code
  case); all were fixed with regression tests before shipping.
- **Documentation** — a subagent generated the [`docs/showcase/`](docs/showcase/) management
  pack from **real** captured engine/API output (no invented numbers).
- **Guardrails** — every agent was held to: don't fabricate, keep the default parser the
  verified reference, keep the suite green, and commit only verified work. Recovered
  partial work (e.g. parallel-parsing) was finished and re-verified in the main thread.

---

## 8. Repository map

| Path | What's there |
|------|--------------|
| [`CLAUDE.md`](CLAUDE.md) | self-instructing working rules (adapted Karpathy guidelines) |
| [`ASSESSMENT.md`](ASSESSMENT.md) | the three assessments of the original repo |
| [`00-foundation/`](00-foundation/) | philosophy · engineering principles · architecture (+ scale plan) |
| [`01-metadata-model/`](01-metadata-model/) | entities · relationships · `models.py` · `schema.sql` |
| [`02-algorithms/`](02-algorithms/) | root / impact / lineage / clustering / confidence pseudocode |
| [`03-skills/`](03-skills/) | 12 skills + `skills.catalog.json` + `validate_catalog.py` + principles |
| [`04-prompts/`](04-prompts/) | V2 prompt library + community modernization prompts |
| [`05-build-plan/`](05-build-plan/) | the v0.1 vertical-slice plan |
| [`reference-implementation/`](reference-implementation/) | the engine, `sample_estate/`, tests, `scripts/`, `ADVANCED_PARSER.md` |
| [`app/`](app/) | React UI + FastAPI API, `USER_MANUAL.md`, `UX_SHOWCASE.md` |
| [`docs/`](docs/) | `MAINFRAME_ARTIFACTS.md` (binary/IMS/MQ taxonomy) + `showcase/` |
| [`source_mf_code/`](source_mf_code/) | the estate MIP analyzes |
| [`.claude/`](.claude/) · [`.github/`](.github/) | project skills/agents/settings · CI |

## 9. Honest limits & where it goes next
v0.1 default parser is a focused grammar (the `advanced` ANTLR backend adds full COBOL-85
coverage + `COPY REPLACING`); inferred outputs (capabilities, communities, business-rule
meaning, resolved dynamic calls) are confidence-scored and flagged for review. Remaining
roadmap tier: **IMS/MQ extraction**, a **graph-DB/scale backend**, and **multi-tenant**
(see [`COMPARISON_AND_ROADMAP.md`](COMPARISON_AND_ROADMAP.md)).
