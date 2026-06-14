# Relationship Taxonomy

> Relationships power the knowledge graph; the relationship is often more important
> than the node (Principle 4). All edges live in one generic `relationship` table
> ([`schema.sql`](schema.sql)) / `Relationship` model ([`models.py`](models.py)) so the
> call graph, batch graph, and lineage graph all materialize from the same store.

## Core edge types (v0.1)

| `rel_type` | Source → Target | Meaning | Discovered from |
|-----------|-----------------|---------|-----------------|
| `EXECUTES` | Job → Program | a job step runs a program | JCL `EXEC PGM=` |
| `CALLS` | Program → Program | a program invokes another | COBOL `CALL` |
| `USES` | Program → Copybook | a program includes a copybook | COBOL `COPY` |
| `READS` | Program → Db2Table | reads a table | `EXEC SQL SELECT` |
| `WRITES` | Program → Db2Table | writes a table | `EXEC SQL INSERT/UPDATE/DELETE` |

Extended types (`CONTAINS`, `DEPENDS_ON`, `PRODUCES`, `CONSUMES`, `IMPLEMENTS`,
`DERIVES_FROM`, `TRIGGERS`) are defined in the metadata prompt
[`../04-prompts/metadata/relationship_model.md`](../04-prompts/metadata/relationship_model.md)
and added with the graph/lineage layers.

## Every edge carries the evidence envelope

A relationship row stores `source_evidence`, `discovery_method`, `confidence`,
`validation_status`, `discovered_at` — identical to entities. This is what lets the
graph **tolerate** uncertainty instead of dropping it.

### The dynamic-call case (the one that breaks naive call graphs)

```cobol
CALL WS-PGM-NAME USING ...      *> target only known at runtime
```

MIP does **not** drop this. It records:

```
CALLS  PROGRAM:CRDPOST → PROGRAM:??WS-PGM-NAME
  discovery_method = inference
  confidence       = 0.3
  validation_status = needs_review
  source_evidence  = "COBOL/CRDPOST:142"
```

The edge is visible, queryable, and honestly labeled. A reviewer (or a later
data-flow pass) can resolve or reject it. This single behavior is the difference
between a call graph you can trust and one you can't.

## Resolution rule (names → entities)

1. A `JobStep.program_name` or `CALLS` target that matches a known `Program.program_id`
   → resolved edge, `confirmed`.
2. A target with no matching program → kept as an **unresolved name**,
   `validation_status = needs_review`. (Missing source is the normal case on partial
   estates — Principle 2.)
3. A target built from a variable (dynamic) → `needs_review`, low confidence, even if a
   same-named program happens to exist.
