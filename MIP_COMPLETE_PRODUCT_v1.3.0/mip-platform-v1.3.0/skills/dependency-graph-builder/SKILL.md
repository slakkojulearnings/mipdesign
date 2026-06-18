---
name: dependency-graph-builder
description: Builds evidence-backed dependency and lineage graphs from catalog and relationship indexes. Use for callers, callees, roots, batch workflows, dataset/table producers and consumers, blast radius, graph validation, and NetworkX exports.
license: Apache-2.0
compatibility: Works with skills-aware coding agents; repository workflows assume Python 3.12+, Git, and local file access.
metadata:
  author: mip-project
  version: "1.0"
---


# Dependency Graph Builder

## Inputs

- `memory/catalog.txt`
- `memory/relationships.txt`
- optional SQLite metadata

## Workflow

1. Validate identifiers and relationship ontology.
2. Create `MultiDiGraph` nodes from catalog entries.
3. Add typed edges with evidence.
4. Preserve unresolved targets as explicit unresolved nodes.
5. Run graph integrity checks.
6. Provide root, caller, callee, producer, consumer, lineage, and impact queries.
7. Export machine-readable and Mermaid-friendly views.

## Guardrails

- Do not infer business criticality from centrality alone.
- Do not collapse distinct technical assets sharing a display name.
- Keep observed and inferred edges distinguishable.

## Success Criteria

Every graph edge is traceable to a relationship-index record and source evidence.

## Operating Rules

- Follow `CLAUDE.md`.
- Preserve source evidence and confidence.
- Do not modify `mfcode/`.
- Keep generated material under `knowledge/` or `output/`.
- Use the work ledger before processing repository artifacts.
- Report unresolved references and unknowns explicitly.
