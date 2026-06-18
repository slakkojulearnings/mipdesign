# MIP Agent Architecture

## Principle

Agents orchestrate deterministic tools and focused reasoning. They do not replace parsers, ledgers, tests, or approval gates.

## Agent Roles

1. Repository Discovery Agent
2. COBOL Documentation Translator
3. JCL Batch Flow Analyst
4. Copybook Data Modeler
5. Dependency Graph Builder
6. Diagram Generator
7. Migration Planner
8. Equivalence Test Engineer
9. Modernization Architect
10. Internal OS Maintainer

## Orchestration

```text
Coordinator
  ├── claims todo items
  ├── dispatches non-overlapping artifacts
  ├── validates outputs
  ├── merges catalog and relationships
  └── releases or completes claims
```

## Parallelism Contract

- One active owner per source artifact.
- Shared copybooks may be read by many agents but documented by one owner.
- Writes to ledgers are serialized or performed through helper scripts.
- Each output declares the source content hash.
- Failed work returns to `PENDING` or becomes `BLOCKED` with a reason.

## Google ADK Mapping

- Agent instructions live in skills.
- Deterministic functions are exposed as tools.
- Workflow state includes run ID, claimed items, evidence, validation, and generated files.
- Long-lived canonical memory is stored in files/SQLite, not only in model session state.
