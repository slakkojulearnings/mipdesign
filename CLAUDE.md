# MIP — Mainframe Intelligence Platform (repo root)

> Project instructions for Claude Code. The canonical, shippable system lives in
> **[`mip_design/`](mip_design/)** — start there. Its own
> [`mip_design/CLAUDE.md`](mip_design/CLAUDE.md) has the full working rules.

## What this repo is
MIP turns a legacy mainframe estate into queryable, evidence-backed knowledge:
`Inventory → Metadata → Knowledge Graph → Reasoning → Copilot → Modernization`.
Thesis: **understand before you transform.**

- **Real source** to analyze: [`source_mf_code/`](source_mf_code/) (extension-less PDS-style members).
- **Engine + tests**: [`mip_design/reference-implementation/`](mip_design/reference-implementation/) (Python 3.13, stdlib-only).
- **Web app**: [`mip_design/app/`](mip_design/app/) (FastAPI + React).
- **Skills** (project, Claude-Code-discoverable): [`.claude/skills/`](.claude/skills/) — canonical source in `mip_design/03-skills/`.
- **Agents**: [`.claude/agents/`](.claude/agents/) — `mip-discovery`, `mip-modernization-architect`.

## Working rules (short form — full set in mip_design/CLAUDE.md)
1. **Think before coding**; surface assumptions; prefer the simpler approach.
2. **Simplicity first**; minimal, non-speculative code.
3. **Surgical changes**; touch only what's asked.
4. **Goal-driven**; verify with tests, not confidence.
5. **Evidence + confidence on every fact**; dynamic/inferred → `needs_review`, never asserted.
6. **Skills are standard + cataloged**: edit in `mip_design/03-skills/`, re-deploy to
   `.claude/skills/`, update `skills.catalog.json`, run `validate_catalog.py`.

## Quick start
```bash
# engine + tests
cd mip_design/reference-implementation && uv venv --python 3.13 && uv pip install -e ".[dev,api]" && uv run pytest -q
# scan the real source
uv run mip scan ../../source_mf_code && uv run mip query "which jobs execute CRDPOST"
# web app (serves built UI)
cd ../app/frontend && npm install && npm run build && cd ../../reference-implementation && uv run uvicorn mip.api:app --port 8000
```
