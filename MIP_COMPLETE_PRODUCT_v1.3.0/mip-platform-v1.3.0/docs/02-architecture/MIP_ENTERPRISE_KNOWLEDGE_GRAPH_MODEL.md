# MIP Enterprise Knowledge Graph Model

## Graph Type

Use `networkx.MultiDiGraph` because the same two assets may have multiple typed relationships and separate evidence.

## Node Families

- Technical: programs, jobs, steps, procedures, copybooks, datasets, tables, columns, transactions
- Business: rules, capabilities, processes, domains
- Modernization: service candidates, APIs, events, migration waves, risks
- Governance: owners, teams, classifications, evidence

## Edge Requirements

Every canonical edge must include:

```yaml
relationship_type:
confidence:
evidence_ids:
source_run_id:
validation_status:
```

## Direction Convention

The edge describes `source performs relationship toward target`.

Examples:

- `program-a CALLS program-b`
- `job-step EXECUTES program-a`
- `program-a READS_TABLE table-x`
- `job-a RUNS_BEFORE job-b`

## Core Traversals

- Callers: incoming `CALLS`
- Callees: outgoing `CALLS`
- Batch roots: scheduler/job nodes without incoming execution-trigger edges
- Program roots: executed by jobs, started by transactions, or externally invoked
- Upstream lineage: reverse data-flow traversal
- Downstream impact: forward dependency traversal based on relationship semantics
- Copybook blast radius: incoming `USES_COPYBOOK`, then callers and executing jobs
- Table writers: incoming `WRITES_TABLE`
- Daily workflow: `RUNS_BEFORE` plus dataset producer/consumer edges

## Validation

- Enforce a source/relationship/target ontology.
- Reject impossible edge combinations.
- Preserve cycles; report them rather than removing them.
- Separate observed edges from inferred edges.
- Never use centrality alone to infer business criticality.
