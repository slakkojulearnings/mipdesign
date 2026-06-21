# Production Readiness Response

This document tracks the Claude review feedback and the follow-up hardening work.
It is intentionally explicit: MIP should not claim production completeness unless
the code, tests, and documentation prove the claim.

## Implemented In This Hardening Pass

| Area | Status | Evidence |
| --- | --- | --- |
| ANTLR parse speed path | Implemented before this pass; verified during review | `cobol_antlr.py` uses SLL first and LL fallback. `reference_parser.py` passes preprocessed text into the parser to avoid double preprocessing. |
| Local parser parallelism | Implemented | `ingestion.py` uses process-based parser workers when `max_workers > 1`; parse-cache writes stay in the parent process. |
| Hard parser timeout | Implemented | `parse_timeout_seconds` runs parsing in an isolated process and terminates it on timeout. Timeout output is `needs_review`, not silently dropped. |
| Parser cache | Implemented | Cache key uses source hash, copybook resolver fingerprint, and parser version. Cached payloads mark `cache_hit=true`. |
| Scan telemetry and slow-file reporting | Implemented and tested | `scan_phase_telemetry` and `scan_file_telemetry` record phase timings, slow files, parse cache hits, and reused classifications. CLI/API/UI expose performance read models. |
| Incremental classification cache | Implemented and tested | `file_inventory_cache` reuses unchanged file classification when `incremental:true`; parser cache reuses unchanged COBOL parse payloads. |
| Discovery correction feedback loop | Implemented and tested | `discovery_correction` stores member/asset/relationship corrections; scans apply member type overrides, asset overrides, and relationship suppression/type overrides. |
| Ground-truth scorecards | Implemented and tested | Scorecard manifests compare expected/forbidden members, nodes, and edges; precision/recall/pass-fail results persist in SQLite and are exposed through CLI/API/UI. |
| SQLite write/read tuning | Implemented before this pass | WAL, `synchronous=NORMAL`, busy timeout, safer conflict handling, and graph slice cache are in place. |
| Duplicate parser/regex extraction | Implemented before this pass | Regex extraction is fallback-only for facts already emitted by parser output. |
| Target-only node evidence | Implemented before this pass | Called programs, datasets, tables, and unresolved targets receive evidence from introducing relationships. |
| `.git` scan exclusion | Implemented before this pass | `.git` is always excluded and skipped directory counts are recorded. |
| DB2 comment handling | Implemented and tested | SQL line and block comments are stripped before DB2 DDL column extraction. |
| DB2 catalog extraction | Implemented v1 | Tables, columns, primary keys, indexes, database, bufferpool, tablespace, and location facts are captured. |
| DB2 cursor/package model | Implemented and tested | Embedded SQL and SQL/JCL bind control create `DB2_CURSOR`, `DB2_PACKAGE`, and `DB2_PLAN` nodes plus cursor table/column/predicate/fetch/open/close and package/plan bind edges. |
| DB2 statement/host-variable model | Implemented and tested | `DB2_STATEMENT` and `HOST_VARIABLE` nodes capture statement table/column/predicate usage, input/output host variables, and host-variable-to-column binding edges. |
| DB2 DCLGEN and join-column model | Implemented and tested | `DCLGEN` nodes, `USES_DCLGEN`, `DCLGEN_DECLARES_TABLE`, alias-normalized DB2 columns, `STATEMENT_JOINS_ON_COLUMN`, and `CURSOR_JOINS_ON_COLUMN` are captured. |
| IMS DBD/PSB/PCB extraction | Implemented v1 | IMS database, segment, field, dataset, PSB, PCB, and segment usage facts are captured. |
| VSAM file-control extraction | Implemented v1 | SELECT/ASSIGN, organization, access mode, record key, and file read/write edges are captured. |
| JCL step graph | Implemented and tested | JOB_STEP nodes, `CONTAINS_STEP`, step-level `EXECUTES`, DD name, DISP, and step dataset edges are captured. |
| PROC expansion and JCL conditions | Implemented and tested | Logical JCL statements, continued EXEC/PROC/DD cards, `INVOKES_PROC`, PROC symbolic expansion, IF/ELSE/ENDIF, `COND`, `CONTROLS_STEP`, and expanded step/dataset edges are captured. |
| JCL DD/GDG/return-code graph | Implemented and tested | `JCL_DD`, `RETURN_CODE`, `DECLARES_DD`, `BINDS_DATASET`, GDG generation metadata, `CONDITION_REFERENCES_STEP`, and `CONDITION_CHECKS_RETURN_CODE` are captured. |
| Copybook field ownership | Implemented and tested | Copybooks create reusable `COPYBOOK_FIELD` nodes and program fields link back with `FIELD_DERIVED_FROM_COPYBOOK` and `USES_COPYBOOK_FIELD`. |
| Copybook resolver precedence/conflict metadata | Implemented and tested | Configured `copybook_dirs` controls search order; duplicate aliases retain selected source, candidate count, conflict flag, and candidates in copy-resolution diagnostics. |
| PL/I static extraction | Implemented and tested | Extensionless PL/I members are classified; CALL, `%INCLUDE`, file I/O, and embedded DB2 facts are captured with confidence metadata. |
| Assembler static extraction | Implemented and tested | Extensionless assembler members are classified; CSECT/DSECT, COPY/INCLUDE, linkage macros, and register-based dynamic calls are captured. |
| COBOL data semantics | Implemented and tested | Data items include PIC, REDEFINES, OCCURS, OCCURS DEPENDING ON, USAGE/COMP, VALUE, and level-88 flags. |
| Field/data lineage | Implemented and tested | `DECLARES_FIELD` and `FLOWS_TO` graph edges are persisted and exposed through dependency graphs. |
| Control flow | Implemented and tested | `CONTAINS_PARAGRAPH`, `PERFORMS`, and `BRANCHES_TO` edges are persisted. |
| CALL contracts | Implemented and tested | `CALL ... USING` arguments are stored on CALLS edges; LINKAGE SECTION items are stored on the program node. |
| CICS data contracts | Implemented and tested | CICS edge attributes and `CICS_CONTRACT` graph nodes capture COMMAREA, CHANNEL, CONTAINER, QUEUE/QNAME, MAP, FILE/DATASET, TRANSID, RESP/RESP2, and LENGTH when present. `HANDLE CONDITION` emits `CICS_CONDITION` and paragraph branch edges. |
| File I/O operation semantics | Implemented and tested | `FILE_IO_OPERATION` and `FILE_RECORD` nodes capture OPEN modes, READ/WRITE/REWRITE/DELETE/START/CLOSE, keys, exception handlers, FD record layouts, and operation-level file reads/writes. |
| Decision, transformation, and statement flow | Implemented and tested | `BUSINESS_RULE`, `TRANSFORMATION`, `STATEMENT`, `SECTION`, and `SORT_MERGE_OPERATION` nodes capture IF/EVALUATE/COMPUTE, transformation inputs/outputs, source-order statement flow, sections, SORT/MERGE files, and keys. |
| Coverage report | Implemented and tested | Node profiles include parser/copy/call/data/control/DB2/CICS/business-rule coverage checks. CLI adds `coverage`. API adds `/coverage/{asset}`. |
| Graph slice from any node | Implemented before this pass | Graph slice resolves asset id or technical name and supports upstream, downstream, and both directions. |
| Root and normal program selector | Implemented before this pass | `/nodes` and UI node picker support roots, programs, normal programs, jobs, tables, copybooks, transactions, and all nodes. |
| UI Flow Diagram | Implemented | React workbench now includes a bounded flow diagram for control and data-movement edges. |
| Export | Implemented before this pass | CLI/API export bounded graph facts and reverse-engineering bundles with manifest/checksum/truncation metadata. |

## Validated Tests Added Or Strengthened

- `tests/test_production_intelligence_depth.py`
  - COBOL field semantics, field lineage, paragraph flow, CALL USING contracts,
    CICS contracts, dependency graph visibility, and coverage reports.
  - JCL step-level graph depth.
  - Process parser backend and hard timeout quarantine.
- `tests/test_phase2_parser_coverage.py`
  - DB2 DDL comment stripping so commented columns are not persisted as facts.
- `tests/test_phase7_10_complete_intelligence.py`
  - DB2 DCLGEN, join-column lineage, CICS contracts, file I/O semantics,
    business-rule graph facts, statement ordering, SORT/MERGE, JCL DD/GDG, and
    return-code condition flow.

## Still Not Fully Production-Complete

These are not being hidden. They require larger architecture work beyond the
current local SQLite/React implementation.

| Gap | Why It Still Matters | Recommended Next Work |
| --- | --- | --- |
| Full deleted-file incremental semantics | Inventory and parser caches now skip unchanged classification/parse work, but discovery still walks and hashes the estate and deleted-file tombstones are not modeled. | Add filesystem snapshot diffing, deleted-source tombstones, and changed-folder-only scan mode. |
| Streaming batch pipeline | Current pipeline is improved but still holds too much estate text in memory for the largest scans. | Convert ingestion to batch classify/parse/persist/drop-text with resume checkpoints. |
| Distributed workers | Local process parallelism helps one machine but not a 200K+ estate at enterprise speed. | Add job queue/workers, shard by folder/run, and persist task state. |
| Full PostgreSQL adapter | Storage factory is explicit, but services still use SQLite-flavored SQL in places. | Move remaining SQL into repository interfaces, then add Postgres implementation and migration tests. |
| Full JCL semantics | PROC expansion, DD binding, GDG names, and condition references are modeled, but INCLUDE libraries, scheduler overrides, restart/rerun semantics, and runtime condition-code propagation still need stronger structured parsing. | Add a structured JCL parser, catalog/proclib resolver, and batch-control-flow simulator. |
| Full DB2 SQL semantics | Cursor/package/statement/DCLGEN/join facts are now modeled, but nested SQL, dynamic SQL strings, constraints, optimizer/catalog metadata, and complex host-variable binding still need stronger SQL AST coverage. | Add SQL grammar integration, catalog imports, statement normalization tables, and more precision/recall scorecards. |
| Full copybook semantics | Copybook search order and field ownership exist, but conditional copy variants, compiler options, and installation-specific library concatenation still need more resolver coverage. | Add copylib profile files, nested COPY provenance reports, and compiler-option-aware resolver tests. |
| Full PL/I and assembler grammar depth | Dedicated static extractors exist, but they are not full grammar parsers. Macro expansion, PL/I preprocessor semantics, assembler USING/DSECT addressability, and register dataflow remain inferred. | Add grammar-backed PL/I and assembler parsers or integrate proven parsers; keep regex fallback confidence-scored. |
| Precision/recall harness | Unit tests cover fixtures, but there is no labeled public-estate scorecard yet. | Create ground-truth manifests for CardDemo and BankDemo and report precision/recall per extractor. |
| Enterprise deployment controls | Local API/UI is not hardened for network enterprise use. | Add auth, tenant isolation, audit logs, rate limits, secrets handling, and CORS policy. |

## Additional Callouts

- The most production-friendly architecture is still two-tier:
  - Tier 1: fast inventory, classification, cheap relationships, search, roots,
    and bounded graph slices.
  - Tier 2: deep ANTLR AST, field lineage, control flow, contracts, business-rule
    extraction, and validation updates in the background.
- LLMs should be used for grounded explanations, names, summaries, and review
  proposals only after graph evidence is persisted. LLM output should never
  overwrite confirmed parser facts.
- For 200K+ files, browser rendering must stay slice-based. Full graph remains
  export/offline-tool territory.
