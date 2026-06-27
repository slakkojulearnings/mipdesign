# MIP Enterprise Standalone Guide

This guide explains what the standalone MIP application does, how it works, what it captures from a mainframe codebase, and how to use the output without overstating confidence.

## 1. What MIP Solves

MIP reads a mainframe estate and builds an evidence-backed knowledge graph. It helps modernization teams answer practical questions before rewriting code:

- What files, programs, jobs, copybooks, DB2 tables, CICS resources, IMS assets, datasets, and queues exist?
- Which programs call each other?
- Which files and tables does a root driver need?
- Which code looks like a candidate business capability or Java service?
- Which facts are confirmed, inferred, or still need review?

The core rule is simple: MIP should not hide uncertainty. Every asset and relationship carries evidence, confidence, and validation status.

```python
@dataclass(frozen=True)
class Evidence:
    source_path: str
    line_start: int | None = None
    evidence_text: str = ""
    confidence: float = 1.0
    validation_status: str = "confirmed"
```

Outcome: developers get a map they can inspect, challenge, export, and improve before making Java decomposition or cutover decisions.

## 2. Inventory And Classification

MIP scans folder structures and extensionless files. It does not rely only on file extensions. It classifies by folder signals, content signals, and cross-reference promotion.

Example: a file named `CUSTREC` with no extension can still become a `COPYBOOK` if another program says `COPY CUSTREC`.

```python
("COBOL", "content:PROGRAM-ID", 0.90, r"\bPROGRAM-ID\s*\."),
("JCL", "content:JCL JOB/EXEC", 0.85, r"(?m)^\s*//\S+\s+(JOB|EXEC)\b"),
("COPYBOOK", "content:copybook level numbers", 0.70, r"(?m)^\s*(01|05|10|77)\s+\S+"),
```

Captures: file path, member name, artifact type, size, encoding, binary/text status, confidence, validation status, and scan issues.

Outcome: large extensionless estates can be scanned without manually renaming files first.

## 3. Baseline COBOL Parser

The synchronous `analyze` scan now uses the fast baseline parser only: COPY preprocessing plus `cobol_ast`. ANTLR is no longer on the critical scan path.

```python
def parse_cobol(text, resolver=None):
    raw_unit = cobol_ast.parse(text)
    expanded = antlr_adapter.preprocess(text, resolver=resolver)
    expanded_unit = cobol_ast.parse(expanded)
    return _unit_payload(raw_unit, expanded_unit, text, expanded, parser_info, resolver)
```

Captures from COBOL baseline: `PROGRAM-ID`, divisions, paragraphs, data items, `COPY`, `COPY REPLACING`, static calls, resolved dynamic calls, unresolved dynamic calls, DB2 SQL blocks, CICS blocks, field flows, data layout, procedure outline, business rules, AST summary, and parser confidence.

Outcome: initial scans finish much faster and still produce a usable graph even when ANTLR cannot parse a dialect.

## 4. Persistent ANTLR Enrichment

ANTLR deep parsing is now an explicit enrichment job, not temporary UI behavior. It persists parse artifacts and materializes deeper facts back into SQLite.

CLI:

```powershell
python -m mip_intel.cli --db data\mip.db enrich --top-n 100 --timeout 20 --max-workers 1
python -m mip_intel.cli --db data\mip.db parse-status CUST001
python -m mip_intel.cli --db data\mip.db enrichment-coverage
```

Stored tables:

```sql
enrichment_artifact_cache  -- content-keyed ANTLR payload and diagnostics
enrichment_member_status   -- run/member materialization status
enrichment_job             -- audit history for enrichment runs
enrichment_fact_source     -- fact provenance for baseline/deep evidence
```

Example parser status:

```text
Program: CUST001
baseline parser: local-copy-replacing-preprocessor+cobol_ast
deep parser: antlr4_deep_parser
deep parse status: completed
last deep parsed: 2026-06-26T10:30:00
```

Outcome: ANTLR can be run for one program, a bounded batch, or eventually a full estate without redoing unchanged files every time.

## 5. Stable Graph Identity

Relationships now use stable logical identity. Attributes no longer create duplicate edges.

```python
def relationship_id(self) -> str:
    return stable_id(
        self.run_id,
        "relationship",
        self.relationship_type.upper(),
        self.source_asset_id,
        self.target_asset_id,
        self._discriminator(),
    )
```

For normal edges like `CALLS`, source/type/target define identity. For multi-instance edges like `FLOWS_TO`, a declared discriminator keeps separate line-level flows distinct.

Outcome: deep enrichment can replace or improve a baseline edge instead of creating a second edge that inflates coupling and graph centrality.

## 6. Knowledge Graph

MIP stores facts as nodes and directed edges in SQLite.

Common nodes: `PROGRAM`, `JOB`, `STEP`, `COPYBOOK`, `TABLE`, `DB2_COLUMN`, `DATASET`, `FILE`, `TRANSACTION`, `BUSINESS_RULE`, `CICS_CONTRACT`, `IMS_DATABASE`.

Common edges: `CALLS`, `DYNAMIC_CALL`, `OBSERVED_CALLS`, `USES_COPYBOOK`, `READS_TABLE`, `WRITES_TABLE`, `READS_FILE`, `WRITES_FILE`, `FLOWS_TO`, `EXECUTES`, `CONTAINS_STEP`, `BINDS_DATASET`, `CATALOG_ALIASES_DATASET`.

Example:

```text
JOB CYCLE01 -> EXECUTES -> PROGRAM CUST001
PROGRAM CUST001 -> CALLS -> PROGRAM CUSTVAL
PROGRAM CUST001 -> READS_TABLE -> TABLE CUSTOMER
```

Outcome: developers can inspect blast radius, upstream/downstream calls, required files, and data usage from one database.

## 6.1 External Runtime And Catalog Evidence

Static source cannot prove every runtime path. MIP now imports external evidence as separate confirmed facts instead of overwriting static parser facts.

Runtime calls:

```powershell
python -m mip_intel.cli --db data\mip.db import-runtime runtime_calls.json --source-system smf
python -m mip_intel.cli --db data\mip.db external-evidence
```

Example runtime JSON:

```json
[
  {
    "source_program": "CUST001",
    "target_program": "CUSTVAL",
    "count": 42,
    "environment": "PROD",
    "job": "CUSTJOB"
  }
]
```

Stored fact:

```text
PROGRAM CUST001 -> OBSERVED_CALLS -> PROGRAM CUSTVAL
```

Catalog datasets:

```powershell
python -m mip_intel.cli --db data\mip.db import-catalog catalog.csv --catalog-source idcams
```

Example CSV:

```csv
raw_dataset,canonical_dataset,dataset_type,owner,application
CARD.AUTH.OUT(+1),CARD.AUTH.OUT,GDG,CARDS,CARD-AUTH
```

Stored facts:

```text
DATASET CARD.AUTH.OUT(+1) -> CATALOG_ALIASES_DATASET -> DATASET_IDENTITY CARD.AUTH.OUT
DATASET_IDENTITY CARD.AUTH.OUT -> CATALOG_DESCRIBES_DATASET -> DATASET CARD.AUTH.OUT(+1)
```

Outcome: runtime-only calls and catalog truth become durable graph evidence, visible in CLI/API/UI coverage, without corrupting source-derived `CALLS` or dataset facts.

## 7. Graph Slices, Workbench, And Exports

The browser does not render the full 200K-file graph. It renders bounded slices.

CLI examples:

```powershell
python -m mip_intel.cli --db data\mip.db graph-slice --root CUST001 --direction both --depth 2
python -m mip_intel.cli --db data\mip.db call-graph CUST001 --direction both --depth 8
python -m mip_intel.cli --db data\mip.db required-files CUST001 --limit 5000
python -m mip_intel.cli --db data\mip.db export-bundle CUST001 --output out\cust001
```

UI views:

- Dashboard: scan status, root drivers, clusters, parser coverage, external runtime/catalog evidence.
- Graph Slice: bounded node/edge view with direction and relationship filters.
- Matrix: compact heatmaps for large relationships.
- 360 Workbench: call graph, dependency graph, flow diagram, required files, AST.
- Architecture: bounded contexts, service candidates, roadmap.
- Quality: validation checks, telemetry, corrections, scorecards.

Outcome: users navigate from search or a root driver into focused evidence instead of trying to load the whole estate at once.

## 8. Modernization And Decision Grade

MIP proposes bounded contexts and Java service candidates from graph evidence. Decision-grade status is now based on normalized graph facts, not broad proxies.

Decision-grade gates:

```text
CALL USING + LINKAGE contracts are modeled as INTERFACE_CONTRACT nodes.
CICS COMMAREA / channel / container contracts are linked to fields.
Dataset references normalize to DATASET_IDENTITY nodes.
COPY REPLACING sites materialize bounded copybook layout fields.
```

Example facts:

```text
PROGRAM CALLER -> DEFINES_CALL_CONTRACT -> INTERFACE_CONTRACT
FIELD CALLER::AUTH-REC -> CALL_ARGUMENT_MAPS_TO_LINKAGE -> FIELD AUTHSVC::LK-REQ
CICS_CONTRACT -> COMMAREA_CONTAINS_FIELD -> FIELD CALLER::AUTH-NO
DATASET CARD.AUTH.OUT(+1) -> NORMALIZES_TO_DATASET_IDENTITY -> DATASET_IDENTITY CARD.AUTH.OUT
COPY_SITE -> COPY_SITE_DECLARES_FIELD -> FIELD CALLER::AUTH-NO
```

If a context does not contain all required facts, service candidates and roadmap items carry:

```json
{
  "decision_grade": false,
  "validation_status": "needs_review"
}
```

Outcome: the platform can guide modernization planning without pretending that service boundaries are ready for cutover.

## 9. Quality, Feedback, And Validation

MIP records scan progress, parser cache hits, slow files, failed files, issues, corrections, and scorecard results.

```powershell
python -m mip_intel.cli --db data\mip.db validate
python -m mip_intel.cli --db data\mip.db performance
python -m mip_intel.cli --db data\mip.db scorecard scorecards\bankdemo.json
```

Human corrections are stored as data, not hidden code changes. Scorecards measure precision and recall against ground truth.

Outcome: parser quality can improve through feedback loops instead of one-time assumptions.

## 10. Current Honest Assessment

Implemented and working:

- Baseline-first parser path for scan performance.
- Persistent enrichment schema and `mip enrich` job.
- Parser status in CLI/API/UI.
- Stable relationship identity for enrichment supersession.
- Bounded copybook layout via `COPY_SITE`, `COPY_SITE_DECLARES_FIELD`, and `MATERIALIZES_COPYBOOK_FIELD`.
- CALL USING/LINKAGE contracts via `INTERFACE_CONTRACT`, `CALL_PASSES_FIELD`, `ENTRY_CONTRACT_USES_FIELD`, and `CALL_ARGUMENT_MAPS_TO_LINKAGE`.
- CICS COMMAREA contracts via `DEFINES_COMMAREA_CONTRACT`, `CONTRACT_USES_FIELD`, and `COMMAREA_CONTAINS_FIELD`.
- Dataset identity normalization via `DATASET_IDENTITY` and `*_DATASET_IDENTITY` relationships.
- Runtime observation import via `OBSERVED_CALLS`.
- Catalog reconciliation import via `CATALOG_DESCRIBES_DATASET` and `CATALOG_ALIASES_DATASET`.
- Graph/coverage/UI visibility for external runtime/catalog evidence.
- Bounded per-site copybook field projection: small copybooks stay complete; large copybooks materialize used fields plus top-level context.
- Bounded program data-dictionary graph projection while preserving the full parser payload in node attributes.
- Batched SQLite persistence for scan members, nodes, edges, and evidence.
- Enrichment coverage rollup in validation and dashboard.
- Decision-grade warning on architecture outputs.
- Required-files, graph slice, call graph, dependency graph, AST, exports, scorecards, corrections, and telemetry remain available.

Still needs enterprise hardening:

- ANTLR success remains dialect-dependent; failures are persisted and visible instead of hidden.
- Catalog reconciliation works when catalog metadata is supplied. Full enterprise truth still depends on the quality and completeness of external catalog/CMDB/SMF feeds.
- Interface mapping is positional for static calls where caller and callee are in the same scan; unresolved dynamic calls stay `needs_review`.
- Runtime observed calls can be imported, but runtime-only behavior such as scheduler overrides, generated JCL, or dynamically constructed program names still depends on available runtime evidence.
- Large-estate performance is improved by bounded projection and batched writes, but should still be benchmarked against a representative 200K-file estate before calling the storage tier complete.

## 11. Quick Start

Install and run:

```powershell
cd F:\mip\mip_structure\intelligent_platform\mip-enterprise-standalone
python -m pip install -e ".[api,dev]"
python -m mip_intel.cli --db data\mip.db analyze F:\path\to\source
python -m mip_intel.cli --db data\mip.db validate
python -m mip_intel.cli --db data\mip.db enrich --top-n 100
start_ui.bat
```

Useful checks:

```powershell
python -m mip_intel.cli --db data\mip.db parse-status CUST001
python -m mip_intel.cli --db data\mip.db enrichment-coverage
python -m mip_intel.cli --db data\mip.db external-evidence
python -m mip_intel.cli --db data\mip.db required-files CUST001
```

The output is useful because it is inspectable: every important conclusion should trace back to source evidence, confidence, and validation status.
