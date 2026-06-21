# MIP Enterprise Intelligence Implementation Logic

This document explains the data-only logic used by the current implementation to
scan source code, parse facts, build graph insights, cluster capabilities, and
export results. It is intentionally explicit so incorrect discovery can be
debugged from evidence instead of guesses.

## Scan Discovery

The scanner starts from a source root and walks files recursively. It prunes
excluded directories before reading files. `.git` is always excluded, even if a
custom `exclude_dirs` config is supplied.

Default scan config:

```json
{
  "batch_size": 500,
  "max_workers": 1,
  "parse_timeout_seconds": 0.0,
  "incremental": false,
  "collect_telemetry": true,
  "copybook_dirs": [],
  "resume": false,
  "exclude_dirs": [".git"]
}
```

Discovery records feedback in `scan_progress`:

- `DISCOVERING`: source root, excluded directory names, skipped directory count.
- `CLASSIFYING`: files classified and classification failures.
- `PARSING`: parse candidates, parser cache hits, failures.
- `PERSISTING`: node and edge counts before database write.
- `VALIDATING`: evidence and confidence checks after database write.
- `SUMMARIZING`: graph summaries, root portfolio, clusters.
- `COMPLETED`: final status and validation snapshot.

Each run also writes production telemetry:

- `scan_phase_telemetry`: elapsed milliseconds and peak traced memory per phase.
- `scan_file_telemetry`: per-file classify/parse/graph timings, parse-cache hits,
  reused classification flags, artifact type, and validation status.
- `file_inventory_cache`: cross-run classification cache keyed by source root,
  relative path, and SHA-256.

When `incremental:true` is supplied, unchanged files reuse the inventory cache
for classification and the existing parser-result cache for COBOL parse payloads.
The graph is still rebuilt for the selected run so node ids, evidence, summaries,
and exports remain internally consistent.

## File Classification

Source files do not need extensions. Classification uses only local evidence:

- folder signals such as `cobol`, `copylib`, `jcl`, `proc`, `sql`, `db2`, `ims`
- content signals such as `PROGRAM-ID`, JCL `JOB`/`EXEC`, DB2 `CREATE TABLE`,
  IMS `DBD`/`PSB`/`PCB`, CICS definitions, copybook level numbers
- binary detection by null bytes, non-text byte ratio, and max text size

Each file becomes a source member with:

- `artifact_type`
- `classification_basis`
- `confidence`
- `validation_status`
- source path, hash, size, encoding, and text/binary status

## COBOL Parsing

COBOL members are parsed through the reference parser layer. The parser uses the
vendored ANTLR4 COBOL grammar where available, plus deterministic fallback
extraction when parsing degrades.

Facts extracted from parser output include:

- `PROGRAM-ID`
- static calls
- dynamic/unresolved calls
- `CALL ... USING` argument lists as caller-side interface contracts
- `COPY` and `COPY ... REPLACING`
- DB2 table reads/writes from EXEC SQL
- CICS targets plus COMMAREA, CHANNEL, CONTAINER, queue, map, file, transaction,
  and length data contracts when present on the source line
- data items, including PIC, REDEFINES, OCCURS, OCCURS DEPENDING ON, VALUE,
  USAGE/COMP, and level-88 condition-name flags
- LINKAGE SECTION records as callee-side contract evidence
- field flows from MOVE, arithmetic/COMPUTE, and SQL host-variable lineage
- paragraph/control-flow facts from PERFORM and GO TO
- AST summary, procedure outline, business-rule candidates, and parser metadata

The ANTLR4 backend uses SLL parsing first and retries with LL only on failure.
The preprocessor is run once per member and passed into the ANTLR parse path to
avoid double COPY expansion. Large scans can use process-based parser workers;
when `parse_timeout_seconds` is configured, parsing runs in an isolated process
that is terminated on hard timeout and recorded as `needs_review`.

Regex extraction is now fallback-only for facts already produced by the parser.
It does not duplicate parser-derived CALL/SQL/CICS facts as separate confirmed
edges.

## Feedback And Self-Correction

Reviewer corrections are stored in `discovery_correction` and applied during
later scans.

Supported correction scopes:

- `MEMBER`: override extensionless or misclassified source-member type by
  relative path.
- `ASSET`: override asset type/name/status by asset id or technical name.
- `RELATIONSHIP`: suppress or override an edge by `SOURCE|TYPE|TARGET` selector.

Corrections are evidence of human review, not hidden magic. Corrected facts carry
`discovery_method=corrected` or `classification_basis=correction:<id>` so future
audits can see where parser output was changed.

## Ground Truth Scorecards

Ground-truth manifests compare expected members, nodes, edges, and forbidden
nodes/edges against a run. Results are persisted in `scorecard_result` with:

- expected count
- matched count
- missing count
- unexpected count
- precision
- recall
- pass/fail status

This gives parser and graph quality a measurable feedback loop for CardDemo,
BankDemo, and internal estates.

## Deep DB2 Model

DB2 facts are extracted from embedded `EXEC SQL` blocks, DDL scripts, DCLGEN-like
members, JCL bind control, PL/I, and assembler source where SQL blocks are
present.

Captured DB2 nodes include:

- `TABLE`
- `DB2_COLUMN`
- `DCLGEN`
- `DB2_STATEMENT`
- `DB2_CURSOR`
- `HOST_VARIABLE`
- `DB2_PACKAGE`
- `DB2_PLAN`
- `DB2_DATABASE`
- `DB2_BUFFERPOOL`
- `DB2_TABLESPACE`
- `DB2_LOCATION`

Captured DB2 edges include:

- `READS_TABLE` and `WRITES_TABLE` from DML
- `USES_DCLGEN` and `DCLGEN_DECLARES_TABLE`
- `DEFINES_TABLE`, `DECLARES_TABLE`, and `INDEXES_TABLE`
- `DEFINES_DB2_CURSOR`
- `CURSOR_READS_TABLE`
- `CURSOR_READS_COLUMN`
- `CURSOR_FILTERS_BY_COLUMN`
- `CURSOR_JOINS_ON_COLUMN`
- `OPENS_DB2_CURSOR`
- `FETCHES_DB2_CURSOR`
- `CLOSES_DB2_CURSOR`
- `DEFINES_DB2_PACKAGE`
- `BINDS_PROGRAM`
- `DEFINES_DB2_PLAN`
- `USES_DB2_PACKAGE`
- `DEFINES_DB2_STATEMENT`
- `STATEMENT_READS_TABLE`
- `STATEMENT_WRITES_TABLE`
- `STATEMENT_READS_COLUMN`
- `STATEMENT_WRITES_COLUMN`
- `STATEMENT_FILTERS_BY_COLUMN`
- `STATEMENT_JOINS_ON_COLUMN`
- `STATEMENT_INPUTS_FROM_HOST_VARIABLE`
- `STATEMENT_OUTPUTS_TO_HOST_VARIABLE`
- `HOST_VARIABLE_BINDS_COLUMN`

Cursor attributes include selected tables, selected columns, predicate columns,
host variables, and query-shape flags for joins, where clauses, grouping,
ordering, and fetch limits. Package and plan attributes include member,
collection, qualifier, owner, action, isolation, and package list when observed.
Statement attributes include statement kind, tables, aliases, read/write
columns, predicate columns, join columns, input/output host variables, and
query-shape flags. Alias-qualified SQL such as `A.CARD_NO` is normalized to the
observed table name where the source statement provides enough evidence.

Current limits are recorded through confidence and validation status. The model
does not yet replace a full SQL optimizer/parser; complex nested SQL, dynamic
SQL strings, and vendor-specific bind syntax may remain inferred or incomplete.

## JCL PROC And Condition Expansion

JCL and PROC members are read as logical statements, so continued `EXEC`,
`PROC`, and `DD` cards are joined before extraction. This supports common cards
such as:

- `EXEC PROC=NAME,` followed by symbolic parameters on continuation lines
- `PROC A=1,` followed by more default parameters
- `DD DSN=... ,` followed by `DISP=...`

Captured batch-control facts include:

- `JOB_STEP`, `PROC_STEP`, `JCL_DD`, and `RETURN_CODE` nodes
- `CONTAINS_STEP`
- step-level `EXECUTES`
- `DECLARES_DD`
- `BINDS_DATASET`
- `INVOKES_PROC`
- `EXECUTES_BEFORE`
- `JCL_CONDITION` nodes
- `DEFINES_CONDITION`
- `CONTROLS_STEP`
- `CONDITION_REFERENCES_STEP`
- `CONDITION_CHECKS_RETURN_CODE`
- `EXPANDS_TO_STEP`
- `EXPANDED_FROM_PROC_STEP`
- expanded dataset reads/writes with symbolic substitution

Symbolic substitution handles JCL delimiter dots, so `&APP..AUTH.IN` becomes
`APPVALUE.AUTH.IN` when `APP` is supplied. GDG names such as `DATA.SET(+1)` are
preserved on dataset nodes with generation metadata. Unresolved symbolics remain
on edge attributes instead of being dropped.

Current limits: GDG arithmetic, INCLUDE libraries, scheduler overrides, runtime
condition-code propagation, and every installation-specific PROC convention are
not treated as fully confirmed unless directly observed in the current source.

## CICS Contracts, File I/O, Rules, And Statement Flow

COBOL extraction now turns high-value procedure facts into graph nodes and
edges, not only program attributes.

Captured CICS contract nodes and edges:

- `CICS_CONTRACT`
- `CICS_CONDITION`
- `DEFINES_CICS_CONTRACT`
- `CONTRACT_USES_FIELD`
- `HANDLES_CICS_CONDITION`
- condition `BRANCHES_TO` paragraph targets from `HANDLE CONDITION`

Captured file I/O nodes and edges:

- `FILE_IO_OPERATION`
- `FILE_RECORD`
- `DEFINES_FILE_IO`
- `HAS_RECORD_LAYOUT`
- `RECORD_DECLARES_FIELD`
- operation-level `READS_FILE`, `WRITES_FILE`, and `USES_FILE`

File I/O attributes include observed verb, mode, file, record, key, and exception
handler signals such as `AT END` and `INVALID KEY`. FD record layouts are linked
to their fields when the FILE SECTION gives enough structure.

Captured decision and transformation nodes and edges:

- `BUSINESS_RULE`
- `TRANSFORMATION`
- `DEFINES_BUSINESS_RULE`
- `RULE_USES_FIELD`
- `DEFINES_TRANSFORMATION`
- `TRANSFORMATION_INPUT_FIELD`
- `TRANSFORMATION_OUTPUT_FIELD`

Rule text remains deterministic and source-grounded. Conditions and expressions
are observed; kind/classification remains `inferred` unless a stronger parser or
review confirms it.

Captured procedure ordering and SORT/MERGE nodes and edges:

- `SECTION`
- `STATEMENT`
- `SORT_MERGE_OPERATION`
- `CONTAINS_SECTION`
- `SECTION_CONTAINS_PARAGRAPH`
- `CONTAINS_STATEMENT`
- statement-level `EXECUTES_BEFORE`
- `DEFINES_SORT_MERGE`

SORT/MERGE facts include work files, input files, output files, and keys when
present on the source line.

## Copybook Field Ownership

Resolved copybooks are selected with a scored resolver. Configured
`copybook_dirs` define search order; otherwise artifact confidence and path order
are used. Duplicate aliases are retained in metadata with candidate count,
selected source, conflict flag, and candidate source paths. Resolved copybooks
are parsed into reusable `COPYBOOK_FIELD` nodes. A program that uses a copybook
receives provenance edges from program fields to copybook fields.

Captured copybook-field edges include:

- `DECLARES_COPYBOOK_FIELD`
- `FIELD_DERIVED_FROM_COPYBOOK`
- `USES_COPYBOOK_FIELD`

Field attributes include level number, PIC, REDEFINES, OCCURS, OCCURS DEPENDING
ON, USAGE, VALUE, and condition-name markers where observed. These facts help
identify shared data contracts before Java DTOs, entities, or API payloads are
generated.

## PL/I And Assembler Static Extraction

PL/I and assembler members are classified even when extensionless. They use
dedicated deterministic static extractors, not the COBOL ANTLR parser.

PL/I extraction captures:

- procedure identity
- `CALL` targets
- `%INCLUDE` copybook usage
- file reads/writes
- embedded DB2 SQL table/cursor/package facts

Assembler extraction captures:

- CSECT program identity
- DSECT ownership
- `COPY`/`INCLUDE` dependencies
- direct linkage macro calls such as `CALL`, `LINK`, `LOAD`, `XCTL`, and `ATTACH`
- register-based dynamic-call markers such as `BALR/BASR/BASSM`
- embedded DB2 SQL table/cursor/package facts when present

These extractors are intentionally confidence-scored. Direct macro targets are
inferred unless a stronger parser proves them. Register-based calls are kept as
`DYNAMIC_CALL` unresolved nodes with `needs_review` rather than fabricated
targets.

## Nodes And Edges

Product terminology is nodes and edges. The current SQLite schema still uses the
legacy table names `asset` and `relationship` for compatibility.

Node examples:

- `PROGRAM`
- `JOB`
- `COPYBOOK`
- `COPYBOOK_FIELD`
- `TABLE`
- `DB2_COLUMN`
- `DCLGEN`
- `DB2_STATEMENT`
- `DB2_CURSOR`
- `HOST_VARIABLE`
- `DB2_PACKAGE`
- `DB2_PLAN`
- `DATASET`
- `TRANSACTION`
- `JCL_CONDITION`
- `JCL_DD`
- `RETURN_CODE`
- `CICS_CONTRACT`
- `CICS_CONDITION`
- `FILE_IO_OPERATION`
- `FILE_RECORD`
- `BUSINESS_RULE`
- `TRANSFORMATION`
- `SECTION`
- `STATEMENT`
- `SORT_MERGE_OPERATION`
- `UNRESOLVED`

Edge examples:

- `CALLS`
- `DYNAMIC_CALL`
- `EXECUTES`
- `INVOKES_PROC`
- `CONTAINS_STEP`
- `EXECUTES_BEFORE`
- `DEFINES_CONDITION`
- `CONTROLS_STEP`
- `DECLARES_DD`
- `BINDS_DATASET`
- `CONDITION_REFERENCES_STEP`
- `CONDITION_CHECKS_RETURN_CODE`
- `EXPANDS_TO_STEP`
- `EXPANDED_FROM_PROC_STEP`
- `USES_COPYBOOK`
- `DECLARES_COPYBOOK_FIELD`
- `FIELD_DERIVED_FROM_COPYBOOK`
- `USES_COPYBOOK_FIELD`
- `DECLARES_FIELD`
- `FLOWS_TO`
- `CONTAINS_PARAGRAPH`
- `CONTAINS_SECTION`
- `SECTION_CONTAINS_PARAGRAPH`
- `CONTAINS_STATEMENT`
- `PERFORMS`
- `BRANCHES_TO`
- `DEFINES_BUSINESS_RULE`
- `RULE_USES_FIELD`
- `DEFINES_TRANSFORMATION`
- `TRANSFORMATION_INPUT_FIELD`
- `TRANSFORMATION_OUTPUT_FIELD`
- `DEFINES_CICS_CONTRACT`
- `CONTRACT_USES_FIELD`
- `HANDLES_CICS_CONDITION`
- `DEFINES_FILE_IO`
- `HAS_RECORD_LAYOUT`
- `RECORD_DECLARES_FIELD`
- `USES_FILE`
- `DEFINES_SORT_MERGE`
- `READS_TABLE`
- `WRITES_TABLE`
- `USES_DCLGEN`
- `DCLGEN_DECLARES_TABLE`
- `USES_DATASET`
- `DEFINES_TABLE`
- `INDEXES_TABLE`
- `DEFINES_DB2_CURSOR`
- `CURSOR_READS_TABLE`
- `CURSOR_READS_COLUMN`
- `CURSOR_FILTERS_BY_COLUMN`
- `CURSOR_JOINS_ON_COLUMN`
- `DEFINES_DB2_PACKAGE`
- `BINDS_PROGRAM`
- `DEFINES_DB2_PLAN`
- `USES_DB2_PACKAGE`
- `DEFINES_DB2_STATEMENT`
- `STATEMENT_READS_TABLE`
- `STATEMENT_WRITES_TABLE`
- `STATEMENT_READS_COLUMN`
- `STATEMENT_WRITES_COLUMN`
- `STATEMENT_FILTERS_BY_COLUMN`
- `STATEMENT_JOINS_ON_COLUMN`
- `STATEMENT_INPUTS_FROM_HOST_VARIABLE`
- `STATEMENT_OUTPUTS_TO_HOST_VARIABLE`
- `HOST_VARIABLE_BINDS_COLUMN`

Every persisted edge carries source evidence. Target-only nodes, such as called
programs, tables, datasets, and unresolved dynamic targets, also get node-level
evidence from the source line that introduced them.

Node profiles include a `coverage_report` checklist for parser coverage,
copybook resolution, call contracts, data dictionary, field lineage, control
flow, DB2 SQL, DB2 cursor/package model, JCL PROC/conditions, copybook field
ownership, PL/I, assembler, CICS, and business-rule candidates. A
`not_observed` status means the current source evidence did not show that fact,
not proof that the behavior does not exist.

## Confidence And Validation

Confidence is a score from `0.0` to `1.0`.

- `confirmed`: directly observed from source with strong parser/classifier
  evidence.
- `inferred`: derived from source evidence but not fully confirmed.
- `needs_review`: partial, unresolved, dynamic, degraded, or uncertain.

No LLM output is treated as a confirmed fact. LLMs can be used later for naming
or explanation only when grounded in stored nodes, edges, evidence, and
confidence values.

## Graph Slices

The browser does not render the full enterprise graph. The graph-slice endpoint
starts from any resolvable node id or technical name and returns a bounded
neighborhood.

Supported directions:

- `downstream`: outgoing edges from the selected node
- `upstream`: incoming edges to the selected node
- `both`: full 360-degree neighborhood

Supported controls:

- depth
- node/edge limit
- relationship type filter
- minimum confidence

Graph-slice responses are cached by run, selected node, direction, depth, limit,
relationship types, and confidence threshold.

## Root Drivers

Root drivers are detected from graph data:

- node type is `PROGRAM`
- no confirmed program callers through `CALLS` or `DYNAMIC_CALL`
- at least one entry relationship such as `EXECUTES`, `STARTS_PROGRAM`, or
  `TRIGGERS`

The root-driver query is aggregate SQL, not one query per program.

## Capability And Domain Clustering

Clusters are data-derived, not hardcoded labels. Current v1 signals include:

- dependency edges between programs, jobs, copybooks, tables, datasets, CICS,
  IMS, and scheduler nodes
- folder proximity
- root-driver membership
- shared data touchpoints
- unresolved/risky edge concentration
- graph component structure

Capability names are inferred from graph evidence such as technical names,
tables, files, jobs, transactions, and dependency context. Low-confidence names
remain `Needs Review`. A production naming layer can add LLM suggestions later,
but those names must cite the graph evidence that caused the suggestion.

## Dependency Matrix

The UI label `Dependency Matrix` replaces the older heatmap wording. It is a
compact aggregation:

- left node type
- right node type
- edge type
- count of observed edges

Examples:

- programs to tables by `READS_TABLE`
- jobs to programs by `EXECUTES`
- programs to copybooks by `USES_COPYBOOK`
- programs to fields by `DECLARES_FIELD`
- fields to fields/DB2 columns by `FLOWS_TO`

The matrix is for large estates where rendering thousands of edges is less
useful than seeing dependency concentration.

## Flow Diagram

The React workbench includes a focused Flow Diagram built from bounded graph
payloads. It filters to control and data movement edges:

- `CALLS`, `DYNAMIC_CALL`, `EXECUTES`, `INVOKES_PROC`
- `CONTAINS_PARAGRAPH`, `CONTAINS_STEP`, `PERFORMS`, `BRANCHES_TO`
- `DEFINES_CONDITION`, `CONTROLS_STEP`, `EXPANDS_TO_STEP`
- `DECLARES_FIELD`, `DECLARES_COPYBOOK_FIELD`, `FLOWS_TO`
- table, DB2 cursor/package, file, copybook-field, and dataset read/write edges

This is a developer navigation view, not a full enterprise render. The full graph
remains backend/export-only.

## Export

The CLI and API export bounded graph data from SQLite:

```powershell
python -m mip_intel.cli --db data\my-estate.db export --format json --limit 50000 --output data\exports\graph.json
```

JSON exports include both names:

- `nodes` and `edges`
- legacy aliases `assets` and `relationships`

The manifest includes:

- row limit
- total and exported counts
- truncation flags
- storage backend
- terminology mapping
- checksum

For reverse engineering a specific program, use:

```powershell
python -m mip_intel.cli --db data\my-estate.db export-bundle CUST001 --output data\bundles\CUST001
```

That bundle contains required files, source locations, AST data, evidence, and
relationships for downstream documentation or modernization tooling.
