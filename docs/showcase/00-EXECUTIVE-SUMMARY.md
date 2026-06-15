# MIP — Executive Summary

**MIP (Mainframe Intelligence Platform) makes a legacy mainframe understandable
before anyone tries to change it.** It reads your COBOL, JCL, copybooks, database
definitions and online (CICS) screens, and turns that pile of code into a clear,
searchable map: what runs what, what touches which data, what is business-critical,
and what is safe to leave alone. Every fact it states comes with the evidence behind
it and a confidence score — so leadership can plan a modernization with eyes open
instead of guessing.

## Why this matters

Most "modernization" tools start by rewriting or migrating code. MIP's thesis is the
opposite: **understand the system first.** It builds knowledge in layers, never
skipping one:

> **Inventory → Metadata → Graph → Reasoning → Copilot → Modernization**

Each layer is grounded in the one below it. You cannot get a trustworthy modernization
plan without first knowing the true dependency graph; you cannot trust the graph
without first parsing the code into evidence-backed facts.

## The headline numbers (from a real scan)

These are captured by running MIP against the bundled sample card-processing estate
(`source_mf_code/`). Your numbers will differ; the method is the same.

| Measure | Value |
|---|---|
| Artifacts scanned | **24** (12 COBOL, 4 JCL, 3 copybooks, 3 DB2, 1 CICS, 1 other) |
| Programs | **12** |
| Batch jobs (steps) | **4** (4 steps) |
| Relationships (edges) | **31** |
| Root / entry programs | **5** |
| Dead-code candidates | **1** |
| Dynamic (inferred) calls flagged | **1** |

**Most operationally critical program (runtime-weighted):** `AUTHVAL` (score 0.86),
followed by `AUTHTRAN` (0.69) — the online card-authorization path, which ran
**4.8 million times** in the measured month.

## Quality / test status

MIP is verified against a ground-truth test suite, not just demoed:

- **Engine suite: 67 tests passing** (parser, graph, lineage, rules, runtime, export, search, CICS).
- **Advanced ANTLR COBOL-85 backend: 28 tests passing** — proves the heavy-duty
  industrial parser produces the *same* results as the default one (parity-tested).

## What makes MIP different — in one paragraph

Transform-first tools convert code and hope the behavior survives. MIP refuses to
state anything it cannot prove. Every relationship carries its **source evidence**
(file and line), a **validation status** (`confirmed`, `inferred`, or `needs_review`),
and a **confidence score**. Inferred facts — a dynamically chosen program call, an
auto-named business capability, a clustered application boundary — are kept and
clearly badged, never presented as certainty and never silently dropped. **Nothing is
fabricated.** That honesty is what makes the output safe to base million-dollar
decisions on.

## Capability status

All capabilities below are **Done** and demonstrated with real captured output in the
linked documents.

| # | Capability | Status | Doc |
|---|---|---|---|
| 1 | Discovery & inventory (roots, dead code) | Done | [01-discovery-inventory.md](01-discovery-inventory.md) |
| 2 | Grammar parsing & AST (+ advanced ANTLR backend) | Done | [02-parsing-and-ast.md](02-parsing-and-ast.md) |
| 3 | Knowledge graph (blast radius, criticality, communities) | Done | [03-knowledge-graph.md](03-knowledge-graph.md) |
| 4 | Field-level data lineage | Done | [04-data-lineage.md](04-data-lineage.md) |
| 5 | Business-rule extraction | Done | [05-business-rules.md](05-business-rules.md) |
| 6 | Online / CICS layer | Done | [06-online-cics.md](06-online-cics.md) |
| 7 | Runtime evidence correlation | Done | [07-runtime-correlation.md](07-runtime-correlation.md) |
| 8 | Business capabilities & modernization | Done | [08-capabilities-and-modernization.md](08-capabilities-and-modernization.md) |
| 9 | Web app & data export | Done | [09-web-app-and-export.md](09-web-app-and-export.md) |

*All numbers and samples in these documents were captured by running the platform.
None are illustrative or invented.*
