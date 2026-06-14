# MIP Reference Architecture

> The layered architecture, the technology choices, and — critically — an **honest
> scale plan** that doesn't promise what the chosen tools can't deliver.

## Layered architecture

```
┌─────────────────────────────────────────────────────────┐
│  Source Systems                                          │
│  COBOL · JCL · PROC · Copybooks · DB2 · VSAM · CICS ·    │
│  IMS · MQ · REXX · Scheduler defs · Control cards        │
└───────────────┬─────────────────────────────────────────┘
                ▼
┌─────────────────────────────────────────────────────────┐
│  Discovery & Parsing Layer        [skill: mainframe-code-analyst]
│  Repository scan → file classification → deterministic    │
│  parsers → AST → CFG/DFG inputs                           │
└───────────────┬─────────────────────────────────────────┘
                ▼
┌─────────────────────────────────────────────────────────┐
│  Metadata Repository              [skill: metadata-modeler · sqlite-engineer]
│  Canonical entities + relationships, each carrying the    │
│  evidence envelope. SQLite (Phase 0/1) → PostgreSQL.     │
└───────────────┬─────────────────────────────────────────┘
                ▼
┌─────────────────────────────────────────────────────────┐
│  Knowledge Graph                  [skill: graph-engineer]
│  Call · Batch · Lineage graphs + graph algorithms        │
│  (SCC, PageRank, Louvain, centrality, reachability)      │
└───────────────┬─────────────────────────────────────────┘
                ▼
┌─────────────────────────────────────────────────────────┐
│  Reasoning Services    [skills: resilience-/business-capability-/modernization-]
│  Root detection · Impact/blast radius · Lineage ·        │
│  Capability & boundary detection · Risk & resilience     │
└───────────────┬─────────────────────────────────────────┘
                ▼
┌─────────────────────────────────────────────────────────┐
│  AI Copilot Layer                                        │
│  NL Q&A · documentation · modernization recommendations  │
│  — grounded in and citing the graph                      │
└─────────────────────────────────────────────────────────┘
```

Each box maps to one or more skills in [`../03-skills`](../03-skills) and a set of
prompts in [`../04-prompts`](../04-prompts). Algorithms for the Reasoning layer are
specified in [`../02-algorithms/CORE_ALGORITHMS.md`](../02-algorithms/CORE_ALGORITHMS.md).

## Technology choices (Phase 0/1)

| Concern | Choice | Why |
|---|---|---|
| Language | Python 3.13 | ecosystem, Pydantic, NetworkX |
| Models | Pydantic v2 | validation + the evidence envelope as types |
| Persistence | SQLite | zero-ops, single-file, fast for ≤ low-millions of rows |
| Graph | NetworkX (`MultiDiGraph`) | in-memory, rich algorithms, no infra |
| CLI | Typer | ergonomic command surface |
| Tests | Pytest | ground-truth corpus + precision/recall |
| COBOL parse | regex (v0.1) → grammar-based later | see parser strategy below |

## Parser strategy (the hardest part — be deliberate)

- **v0.1 (now):** regex extractors for `PROGRAM-ID`, static `CALL 'literal'`, `COPY`,
  and JCL `EXEC PGM=`. Fast to build, good enough to prove the spine, but **honest
  about limits** (below).
- **v1.0 (next):** move to a real COBOL grammar — evaluate
  **ProLeap COBOL parser** or **Koopa**, or an ANTLR4 COBOL85 grammar — producing a
  proper **AST** (see [`../01-metadata-model`](../01-metadata-model) for the AST node
  shape). Regex does not survive real-world COBOL (continuations, `REPLACING`,
  copybook expansion, free vs fixed format).

**Known v0.1 limitations (documented, not hidden):**
- Dynamic calls (`CALL WS-PGM`) are detected as *dynamic* and emitted with
  `validation_status = Needs Review`, `confidence = Low` — never dropped, never
  marked Confirmed.
- Copybook `COPY ... REPLACING` is not expanded.
- CICS/IMS/MQ flows are out of v0.1 scope.

## The honest scale plan

The vision documents claim *"100k+ programs, 10M+ relationships."* Here is what the
chosen tools actually support, and the trigger for changing them:

| Store | Comfortable range | Hard ceiling (practical) |
|---|---|---|
| **SQLite** | ≤ ~5–10M rows; simple indexed lookups | complex multi-join traversal slows past ~10M relationship rows |
| **NetworkX** (in-memory) | ≤ ~1–2M edges on a dev laptop | memory-bound; **not** suitable for 10M+ edges |

**Crossing-the-line plan (explicit, not "future"):**
- **Trigger:** edge count projected to exceed ~1.5M, *or* graph build > 60s, *or* RSS
  > ~4 GB.
- **Target:** persist relationships in **PostgreSQL** (already the SQLite migration
  target) and move graph workloads to a store built for it — **Neo4j** (Cypher
  traversal) or **igraph**/**graph-tool** (C-backed, fits tens of millions of edges in
  memory far more compactly than NetworkX).
- **Insulation:** all graph access goes through a thin `graph` interface so the
  backing store can change without touching reasoning code.

> Principle: state numbers the tools can actually hit for v0.1, and name the concrete
> trigger + target for scaling — rather than quoting an aspirational number the Phase
> 0 stack cannot serve.

## Multi-tenancy / "any organization" (Stage 3 ambition)

The model is tech-agnostic and the estate of any org reduces to the same entities
(Program, Job, Table, Copybook, Dataset, Transaction, Capability). To serve multiple
organizations: one metadata store **per tenant** (isolation + compliance), a shared
**canonical model + skills + prompt library**, and per-tenant confidence/coverage
dashboards. Nothing in the model assumes a single customer — which is what makes the
"universal mainframe problem" framing defensible.
