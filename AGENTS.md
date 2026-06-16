# Working in the MIP repo — Agent & Engineer Guidelines

> This file makes the repo **self-instructing**: any Codex session (or engineer)
> on any machine that opens this repo should follow these rules. They adapt the
> community **Andrej Karpathy guidelines**
> (github.com/multica-ai/andrej-karpathy-skills) to this project, and they reinforce the
> MIP Engineering Principles in [`00-foundation/ENGINEERING_PRINCIPLES.md`](00-foundation/ENGINEERING_PRINCIPLES.md).

## What this repo is
The single source of truth for the **Mainframe Intelligence Platform (MIP)** design:
philosophy, principles, metadata model, algorithms, the canonical **skills** and
**prompt library**, and a runnable **v0.1 reference implementation**. MIP's thesis:
**understand the system before transforming it** — build Inventory → Metadata → Graph →
Reasoning → Copilot → Modernization, in that order, never skipping a layer.

## The four working rules

**1. Think before coding.**
Don't assume; don't hide confusion; surface tradeoffs. State assumptions explicitly and
ask when a requirement is ambiguous. Prefer the simpler approach and say so.

**2. Simplicity first.**
Write the minimum that solves the stated problem. No speculative features,
abstractions, or config. No error handling for impossible cases. *If 200 lines could be
50, rewrite it.* The reference implementation is deliberately small — keep it that way.

**3. Surgical changes.**
Touch only what the task requires. Match existing style. Don't refactor working code or
reformat adjacent lines. Remove only what your own change orphaned. Flag pre-existing
dead code; don't delete it unasked. Every changed line should trace to the request.

**4. Goal-driven execution.**
Turn tasks into verifiable success criteria. Write/extend the ground-truth test before
changing a parser. Run `pytest` and the CLI before and after. Loop until verified — a
green run is the definition of done, not a confident-sounding summary.

## MIP-specific rules (non-negotiable)

- **Evidence + confidence on every fact.** Anything not directly proven is `inferred`
  or `needs_review` with confidence < 1.0. Never present inference as `confirmed`.
  Dynamic calls and unresolved targets are *kept and flagged*, never dropped.
- **Degrade gracefully.** Partial/missing source is the normal case. Produce the best
  evidence-based result, record the gap, lower confidence — never fabricate.
- **AI consumes knowledge, it doesn't replace it.** LLM output (explanations,
  translations, recommendations) is a *proposal* grounded in and citing the graph, and
  is verified by tests before it becomes a decision.
- **Be honest about scale.** State numbers the chosen tools (SQLite, NetworkX) actually
  hit; name the trigger + target before claiming more. See
  [`00-foundation/ARCHITECTURE.md`](00-foundation/ARCHITECTURE.md).
- **Skills are standard + cataloged.** Skills follow the Agent Skills spec (folder +
  `SKILL.md` with `name`/`description` frontmatter). When you add/delete/rename a skill,
  update [`03-skills/skills.catalog.json`](03-skills/skills.catalog.json) in the same
  change and run `python 03-skills/validate_catalog.py` (must pass).

## Map of the repo
- `00-foundation/` — philosophy, principles, architecture (+ honest scale plan)
- `01-metadata-model/` — `ENTITIES.md`, `RELATIONSHIPS.md`, `models.py`, `schema.sql`
- `02-algorithms/` — concrete pseudocode for root/impact/lineage/clustering
- `03-skills/` — the 13 canonical skills + `MIP_ENGINEERING_PRINCIPLES.md` + `modernization-leverage/`
- `04-prompts/` — canonical V2 prompt library + `community/` modernization prompts
- `05-build-plan/` — the v0.1 vertical-slice plan
- `reference-implementation/` — runnable Python v0.1 + `sample_estate/` + tests
- `ASSESSMENT.md` — the three assessments of the original repo

## Run the reference implementation (any machine)
```
cd reference-implementation
python -m pip install -e .
mip scan sample_estate/                 # inventory + parse + load SQLite
mip query "which jobs execute CRDPOST"  # root-driver query
pytest                                  # ground-truth precision/recall
```
Pure-Python, standard-library + pydantic/typer/networkx only — no mainframe and no
network required. Portable across machines.
