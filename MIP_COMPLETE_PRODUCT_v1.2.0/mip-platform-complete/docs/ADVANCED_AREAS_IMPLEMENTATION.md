# Advanced Areas Implementation

## Implemented in v1.1.0

| Area | Implementation |
|---|---|
| COPY REPLACING | COBOL parser detects replacement pairs and records expansion metadata through `USES_COPYBOOK` and `EXPANDS_TO` relationships. |
| Complex JCL symbolic PROC expansion | JCL parser supports SET statements, EXEC parameter overrides, in-file PROC body collection, symbolic substitution, and expanded EXEC PGM relationships. |
| Proprietary scheduler adapters | Generic adapter supports pipe-delimited, key-value, CSV, and JSON scheduler dependency exports. This is the open adapter layer for proprietary exports. |
| IMS | DBD/PSB analyzer extracts databases, segments, parent-child hierarchy, and PSB-to-DBD references. |
| MQ | MQSC and COBOL MQ call detection extract queues and PUT/GET/OPEN relationships. |
| Assembler | CSECT/START and CALL/LINK metadata extraction. |
| PL/I | PROC, CALL, %INCLUDE, and embedded SQL read/write extraction. |
| Distributed execution | Deterministic shard planner for parallel workers and CI matrix jobs. |
| Multi-tenancy | Tenant table, tenant-aware schema foundation, and tenant CLI commands. |

## What Remains Enterprise-Hardening Work

These are not blockers for v1.1.0, but they are the next hardening items for real 180k-file estates:

1. Full expanded copybook materialization with line maps.
2. Cross-library PROC search path resolution.
3. Direct parsers for actual scheduler export formats used by the target organization.
4. IMS PCB sensitivity, SSA, and segment-level CRUD modeling.
5. MQ queue alias/remote resolution and constant propagation from copybooks.
6. Assembler macro expansion and register-flow analysis.
7. PL/I preprocessor and include path resolution.
8. Queue-based worker execution and result merging.
9. Tenant-aware API authorization and per-tenant encryption/secrets.
10. Performance benchmarks and tuning for the user's full repository.

## Open Source Position

The implementation uses open-source Python libraries and Apache-2.0 project licensing. Proprietary adapters should be implemented as configuration-driven importers, not by embedding vendor credentials or private environment assumptions.
