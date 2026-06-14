# MIP — Mainframe Intelligence Platform

**Understand a legacy mainframe estate before you transform it.** MIP turns a folder of
COBOL/JCL/copybooks/DB2 into queryable, evidence-backed knowledge — so a new engineer can
answer in seconds what used to take weeks of SME time.

```
Source → Inventory → Metadata → Knowledge Graph → Reasoning → Copilot → Modernization
```

## Quick start

```bash
# engine + tests (Python 3.13, stdlib-only runtime)
cd mip_design/reference-implementation
uv venv --python 3.13 && uv pip install -e ".[dev,api]"
uv run pytest -q                                  # ground-truth tests (5/5)
uv run mip scan ../../source_mf_code              # scan the real estate
uv run mip query "which jobs execute CRDPOST"     # -> DAILYCRD

# web app (FastAPI + React) — serves the built UI on http://localhost:8000
cd ../app/frontend && npm install && npm run build
cd ../../reference-implementation && uv run uvicorn mip.api:app --port 8000
```

## What's here

| Path | What |
|------|------|
| [`mip_design/`](mip_design/) | **the consolidated platform** — single source of truth |
| `mip_design/00-foundation/` | philosophy, engineering principles, architecture (+ honest scale plan) |
| `mip_design/01-metadata-model/` | canonical entities, `models.py`, `schema.sql` (evidence envelope) |
| `mip_design/02-algorithms/` | root / impact / lineage / clustering pseudocode |
| `mip_design/03-skills/` | 12 skills (Agent Skills standard) + `skills.catalog.json` |
| `mip_design/04-prompts/` | V2 prompt library + community modernization prompts |
| `mip_design/reference-implementation/` | runnable engine + `sample_estate/` + tests |
| `mip_design/app/` | React UI + FastAPI API ([USER_MANUAL](mip_design/app/USER_MANUAL.md)) |
| [`source_mf_code/`](source_mf_code/) | the mainframe estate MIP analyzes (drop real code here) |
| [`.claude/`](.claude/) | project skills, subagents, settings for Claude Code |
| [`.github/`](.github/) | CI + Claude Code GitHub workflows |

## Principles in one line

MIP never guesses silently: every fact carries **evidence + a confidence**, anything
dynamic or inferred is **flagged `needs_review`** (never asserted), and the system
**degrades gracefully** on partial input. See
[`mip_design/00-foundation/ENGINEERING_PRINCIPLES.md`](mip_design/00-foundation/ENGINEERING_PRINCIPLES.md).

🤖 Generated with [Claude Code](https://claude.com/claude-code)
