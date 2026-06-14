# MIP Reference Architecture

## Layers

```text
1. Raw Source Layer
   COBOL, JCL, copybooks, SQL, CICS, VSAM, scheduler definitions, documentation

2. Discovery Layer
   Recursive scanner, content classifier, encoding detector, todo ledger

3. Parsing Layer
   Language and artifact-specific deterministic extractors

4. Canonical Metadata Layer
   Assets, relationships, evidence, confidence, validation

5. Knowledge Layer
   Catalogs, documentation, lineage, graph, diagrams

6. Reasoning Layer
   Impact, root detection, risk, capability and service candidates

7. Modernization Layer
   Migration specifications, target design, equivalence tests, wave plans

8. Interaction Layer
   CLI, Google ADK agents, APIs, and natural-language queries
```

## Local Runtime

- SQLite stores canonical metadata, run state, evidence, and results.
- NetworkX provides typed graph traversal and analytics.
- Files under `memory/` provide portable, reviewable indexes.
- Google ADK orchestrates workflows but does not replace deterministic services.

## Enterprise Evolution

SQLite may migrate to PostgreSQL when concurrency and scale require it. NetworkX may export to a graph database when measured graph size or multi-user query requirements justify the move.

## Trust Boundary

LLMs may summarize, name, classify, and recommend. They may not create canonical facts without evidence. Deterministic extractors and validation rules remain authoritative.
