# MIP — Mainframe Intelligence Platform

> **Understand the system before you transform it.** MIP turns a legacy mainframe
> estate into queryable, evidence-backed knowledge — so a new engineer can answer in
> seconds what used to take weeks of SME time.
>
> This repository is the **single source of truth**: philosophy, principles,
> metadata model, algorithms, the canonical skills + prompt library, and a **runnable,
> tested v0.1 reference implementation**. It consolidates ~50 scattered design docs and
> fixes the gaps found in review (see [`ASSESSMENT.md`](ASSESSMENT.md)).

## The idea in one picture

```
Source Code → Inventory → Metadata → Knowledge Graph → Reasoning → Copilot → Modernization
              (never skip a layer; AI consumes facts, it doesn't invent them)
```

The first thread to pull is the **root / driver program**: in a batch mainframe,
execution starts in JCL (`EXEC PGM=`), not COBOL. Find the roots, and the system
becomes navigable. The v0.1 implementation does exactly this — and it runs today.

## Map of the folder

| Path | What's there |
|------|--------------|
| [`CLAUDE.md`](CLAUDE.md) | working rules for any agent/engineer in this repo (adapted Karpathy guidelines) — makes the repo self-instructing on any machine |
| [`ASSESSMENT.md`](ASSESSMENT.md) | the 3 assessments of the original repo (why this folder exists) |
| [`00-foundation/`](00-foundation/) | [PHILOSOPHY](00-foundation/PHILOSOPHY.md) · [ENGINEERING_PRINCIPLES](00-foundation/ENGINEERING_PRINCIPLES.md) · [ARCHITECTURE](00-foundation/ARCHITECTURE.md) (incl. honest scale plan) |
| [`01-metadata-model/`](01-metadata-model/) | canonical [ENTITIES](01-metadata-model/ENTITIES.md) · [RELATIONSHIPS](01-metadata-model/RELATIONSHIPS.md) · `models.py` (Pydantic) · `schema.sql` (SQLite) |
| [`02-algorithms/`](02-algorithms/) | [CORE_ALGORITHMS](02-algorithms/CORE_ALGORITHMS.md) — root, impact/blast-radius, lineage, clustering, confidence aggregation (pseudocode) |
| [`03-skills/`](03-skills/) | the **12 canonical skills** + [MIP_ENGINEERING_PRINCIPLES](03-skills/MIP_ENGINEERING_PRINCIPLES.md) + [modernization-leverage](03-skills/modernization-leverage/SKILLS.md) |
| [`04-prompts/`](04-prompts/) | the **canonical V2 prompt library** (27 prompts) + [community modernization prompts](04-prompts/community/COMMON_MODERNIZATION_PROMPTS.md) |
| [`05-build-plan/`](05-build-plan/) | [V0.1_VERTICAL_SLICE](05-build-plan/V0.1_VERTICAL_SLICE.md) |
| [`reference-implementation/`](reference-implementation/) | **runnable** v0.1 engine (Python 3.13) + `sample_estate/` + tests |
| [`app/`](app/) | **React UI + FastAPI API** ([USER_MANUAL](app/USER_MANUAL.md)) over the engine |
| [`source_mf_code/`](source_mf_code/) | the mainframe estate MIP analyzes (drop real code here) |
| [`.claude/`](.claude/) · [`.github/`](.github/) | project skills/agents/settings · CI |

## What's proven today (the runnable spine)

```bash
cd reference-implementation
uv venv --python 3.13 && uv pip install -e ".[dev]"
uv run mip scan sample_estate                  # 20 extension-less members → SQLite
uv run mip query "which jobs execute CRDPOST"  # → DAILYCRD
uv run pytest -q                               # ground-truth precision/recall = 1.0  (5/5)
```

- **Content-based classification** of extension-less PDS-style members (as real
  mainframe source is).
- **Root/driver detection**, call graph, copybook & DB2 usage, **dead-code** detection.
- **Resilience proven, not claimed:** the dynamic `CALL WS-VAR` is kept and flagged
  `needs_review` (conf 0.3), never dropped or asserted — and a test enforces it.

See [`reference-implementation/README.md`](reference-implementation/README.md) for the
full run guide (incl. running it against the public AWS CardDemo estate) and the honest
v0.1 limits.

## What makes this the "better version"

1. **Single source of truth** — no more skills/prompts duplicated in 4+ places.
2. **It runs and measures itself** — design caught up to vision; the spine is tested.
3. **Resilience baked in** — the evidence envelope (source · method · confidence ·
   validation_status · timestamp) is in the model, the schema, and the code.
4. **Honest about scale and limits** — real numbers + a named trigger/target for graph
   scaling; v0.1 limits documented, not hidden.
5. **Portable** — stdlib-only runtime; runs on any machine with Python 3.13+, no
   network. `git clone` and go.

## Where it goes next

Graph algorithms on NetworkX (blast radius, clustering) → real COBOL grammar/AST →
field-level lineage → capability detection → LLM Q&A — each **incremental on a spine
that already works**, in the layer order above. The modernization prompts/skills
([`04-prompts/community`](04-prompts/community/COMMON_MODERNIZATION_PROMPTS.md),
[`03-skills/modernization-leverage`](03-skills/modernization-leverage/SKILLS.md)) plug in
at the Copilot/Modernization layer once the graph exists.
