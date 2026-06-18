---
name: graph-engineer
description: Implements and reviews NetworkX graph loading, ontology, traversal direction, lineage, roots, impact, metrics, and exports. Use when adding a relationship or graph query or diagnosing incorrect dependency results.
license: Apache-2.0
compatibility: Designed for skills-aware coding agents working with the MIP repository.
metadata:
  author: mip-project
  version: "1.0"
---

# Graph Engineer

## Workflow

1. Confirm source and target types and dependency direction.
2. Ensure the edge has evidence, confidence, and validation status.
3. Add the relationship to the ontology.
4. Implement the smallest required traversal.
5. Test direct, transitive, cyclic, unresolved, and disconnected cases.
6. Verify impact direction against real examples.
7. Export only reviewable subgraphs for large estates.

## Guardrails

- Use `MultiDiGraph` for multiple typed edges.
- Preserve cycles and parallel edges.
- Do not use centrality as proof of business criticality.
- Do not merge nodes because display names look similar.

## Success Criteria

Graph answers are deterministic, directionally correct, and traceable to persisted relationships.

## Repository Rules

Follow `CLAUDE.md`, protect proprietary source, keep changes surgical, and run the relevant validation commands before completion.
