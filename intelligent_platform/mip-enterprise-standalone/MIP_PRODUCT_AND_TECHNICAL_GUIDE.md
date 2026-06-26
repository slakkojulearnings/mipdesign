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

Common edges: `CALLS`, `DYNAMIC_CALL`, `USES_COPYBOOK`, `READS_TABLE`, `WRITES_TABLE`, `READS_FILE`, `WRITES_FILE`, `FLOWS_TO`, `EXECUTES`, `CONTAINS_STEP`, `BINDS_DATASET`.

Example:

```text
JOB CYCLE01 -> EXECUTES -> PROGRAM CUST001
PROGRAM CUST001 -> CALLS -> PROGRAM CUSTVAL
PROGRAM CUST001 -> READS_TABLE -> TABLE CUSTOMER
```

Outcome: developers can inspect blast radius, upstream/downstream calls, required files, and data usage from one database.

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

- Dashboard: scan status, root drivers, clusters, parser coverage.
- Graph Slice: bounded node/edge view with direction and relationship filters.
- Matrix: compact heatmaps for large relationships.
- 360 Workbench: call graph, dependency graph, flow diagram, required files, AST.
- Architecture: bounded contexts, service candidates, roadmap.
- Quality: validation checks, telemetry, corrections, scorecards.

Outcome: users navigate from search or a root driver into focused evidence instead of trying to load the whole estate at once.

## 8. Modernization And Decision Grade

MIP proposes bounded contexts and Java service candidates from graph evidence. These are intentionally not final decisions until critical facts are present.

Decision-grade gates:

```text
CALL USING + LINKAGE contracts
CICS COMMAREA / channel / container contracts
dataset identity normalization
bounded copybook layout
```

Until all gates pass, service candidates and roadmap items carry:

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
- Enrichment coverage rollup in validation and dashboard.
- Decision-grade warning on architecture outputs.
- Required-files, graph slice, call graph, dependency graph, AST, exports, scorecards, corrections, and telemetry remain available.

Still not decision-grade for Java decomposition:

- Bounded copybook layout is designed but not fully materialized as separate `CopyExpansionSite` nodes.
- CALL USING/LINKAGE and CICS COMMAREA extraction exist partially but still need stricter contract modeling.
- Dataset identity normalization exists for several paths but still needs estate-grade reconciliation across COBOL FD, JCL DD, VSAM, IMS, and catalog metadata.
- Full ANTLR success depends on dialect coverage; failures are persisted and visible instead of hidden.

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
python -m mip_intel.cli --db data\mip.db required-files CUST001
```

The output is useful because it is inspectable: every important conclusion should trace back to source evidence, confidence, and validation status.
