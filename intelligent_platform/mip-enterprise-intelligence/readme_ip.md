# MIP Enterprise Intelligence Setup

This guide explains how to set up the application on another machine, point it at
a mainframe source-code folder, scan it into SQLite, and explore the results in
the CLI and React UI.

## What This Build Does

- Uses a vendored ANTLR4 COBOL parser generated from COBOL85 grammar files.
- Expands `COPY ... REPLACING` when copybooks are resolved.
- Stores source members, assets, relationships, evidence, parser metadata, graph
  summaries, graph-slice cache, and parser-result cache in SQLite.
- Supports extensionless source files by using folder signals, content signals,
  and referenced-member promotion for copybooks.
- Persists scan progress, scan issues, validation results, and schema-version
  metadata for production governance.
- Extracts DB2 DDL/catalog infrastructure, DCLGEN-style declarations, CICS
  resources, IMS DBD/PSB/PCB facts, and VSAM file-control metadata.
- Builds bounded graph views instead of trying to render a full enterprise graph
  in the browser.
- Produces graph-derived bounded contexts, service candidates, and modernization
  roadmap work packages with feedback gates and evidence citations.
- Keeps confidence and validation status on assets, relationships, and evidence.

This is a production-direction implementation. It is not yet the final enterprise
platform for every dialect and every mainframe product. The next production waves
should add distributed workers, tenant isolation, PostgreSQL storage, richer
PL/I and assembler parsers, runtime evidence ingestion, and authenticated API/UI
deployment.

## Prerequisites

- Python 3.11 or later.
- Node.js 18 or later.
- Git, if you want to clone public test estates.
- Enough disk for SQLite DBs, parser cache, graph exports, and source bundles.

## Install Backend

From the application folder:

```powershell
cd F:\mip\mip_structure\intelligent_platform\mip-enterprise-intelligence

python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
python -m pip install -e ".[api,dev]"
```

Verify the backend:

```powershell
python -m unittest discover -s tests -v
```

## Install Frontend

```powershell
cd F:\mip\mip_structure\intelligent_platform\mip-enterprise-intelligence\frontend
npm install
npm run build
```

## Analyze Your Source Code

Use any source root. The source can contain files with extensions or no
extensions. Binary files are inventoried but not parsed.

```powershell
cd F:\mip\mip_structure\intelligent_platform\mip-enterprise-intelligence
.\.venv\Scripts\Activate.ps1

python -m mip_intel.cli --db data\my-estate.db analyze "F:\path\to\source_code"
```

Large scan options:

```powershell
python -m mip_intel.cli --db data\my-estate.db analyze "F:\path\to\source_code" --config "{run_id:nightly-001,batch_size:500,max_workers:4,parse_timeout_seconds:60,resume:false}"
```

Useful checks after scan:

```powershell
python -m mip_intel.cli --db data\my-estate.db stats
python -m mip_intel.cli --db data\my-estate.db validate
python -m mip_intel.cli --db data\my-estate.db roots --limit 50
python -m mip_intel.cli --db data\my-estate.db clusters --limit 50
python -m mip_intel.cli --db data\my-estate.db search CUST --limit 20
python -m mip_intel.cli --db data\my-estate.db domains --limit 20
python -m mip_intel.cli --db data\my-estate.db service-candidates --limit 20
python -m mip_intel.cli --db data\my-estate.db roadmap --limit 20
```

Inspect a program:

```powershell
python -m mip_intel.cli --db data\my-estate.db call-graph CUST001 --direction both --depth 8
python -m mip_intel.cli --db data\my-estate.db dependency-graph CUST001 --direction both --depth 4
python -m mip_intel.cli --db data\my-estate.db ast-tree CUST001
python -m mip_intel.cli --db data\my-estate.db required-files CUST001 --depth 8
```

Export a reverse-engineering bundle:

```powershell
python -m mip_intel.cli --db data\my-estate.db export-bundle CUST001 --output data\bundles\CUST001
```

The bundle contains manifest JSON, source files, AST data, evidence, relationships,
and minimal context for reverse-engineering documentation or modernization tools.

Export graph facts:

```powershell
python -m mip_intel.cli --db data\my-estate.db export --format json --limit 5000 --output data\exports\graph.json
```

JSON exports include a manifest with row limits, total counts, truncation flags,
storage backend, and checksum.

## Run API And React UI

Terminal 1, backend API:

```powershell
cd F:\mip\mip_structure\intelligent_platform\mip-enterprise-intelligence
.\.venv\Scripts\Activate.ps1
python -m mip_intel.cli --db data\my-estate.db serve --host 127.0.0.1 --port 8000
```

Terminal 2, React UI:

```powershell
cd F:\mip\mip_structure\intelligent_platform\mip-enterprise-intelligence\frontend
npm run dev
```

Open:

```text
http://127.0.0.1:5174
```

If backend port `8000` is busy, start backend on another port:

```powershell
python -m mip_intel.cli --db data\my-estate.db serve --host 127.0.0.1 --port 8010
```

Then start frontend with:

```powershell
$env:VITE_API_PROXY_TARGET='http://127.0.0.1:8010'
npm run dev
```

Important UI rule: the React app renders bounded graph slices, not the full
enterprise graph. Use search, roots, clusters, heatmaps, and architecture views
to navigate large estates.

## Public Test Estate: BankDemo

BankDemo is useful because it includes COBOL, copybooks, BMS, JCL, PROC, PL/I,
assembler, SQL DDL, CSD, data files, scripts, and executable/runtime folders.

Clone it:

```powershell
cd F:\mip\mip_structure
git clone --depth 1 --branch develop https://github.com/RocketSoftwareCOBOLandMainframe/BankDemo.git _tmp_bankdemo
```

Recommended first scan, source only:

```powershell
cd F:\mip\mip_structure\intelligent_platform\mip-enterprise-intelligence
.\.venv\Scripts\Activate.ps1
python -m mip_intel.cli --db data\bankdemo-sources.db analyze F:\mip\mip_structure\_tmp_bankdemo\sources
python -m mip_intel.cli --db data\bankdemo-sources.db validate
python -m mip_intel.cli --db data\bankdemo-sources.db roots --limit 50
python -m mip_intel.cli --db data\bankdemo-sources.db clusters --limit 50
```

Broader validation scan, whole repo:

```powershell
python -m mip_intel.cli --db data\bankdemo-full.db analyze F:\mip\mip_structure\_tmp_bankdemo
python -m mip_intel.cli --db data\bankdemo-full.db stats
python -m mip_intel.cli --db data\bankdemo-full.db validate
```

Use the source-only scan for parser quality. Use the full-repo scan to validate
inventory behavior across scripts, data files, executable folders, and project
metadata.

## Reading Confidence And Validation

- `confirmed`: directly observed in source or parser output.
- `inferred`: likely, but based on content/folder signals or deterministic inference.
- `needs_review`: incomplete or unresolved, such as dynamic calls or missing copybooks.

Confidence is a numeric score from `0.0` to `1.0`. Do not treat low-confidence
facts as final modernization decisions. Use them to guide review.

Parser metadata appears under asset attributes:

```json
{
  "parser": {
    "effective": "local-antlr4-full-grammar",
    "confidence": 0.95,
    "validation_status": "confirmed",
    "cache_hit": false
  }
}
```

If `effective` is a fallback parser mode, downstream relationships are capped by
the parser confidence.

Validation is persisted in SQLite:

```powershell
python -m mip_intel.cli --db data\my-estate.db validate
```

The checks cover evidence presence, visible review gaps, confidence ranges,
allowed validation statuses, and evidence line ranges.

## Storage And Migration Readiness

- SQLite is the v1 backend and records schema version in `schema_version`.
- Repository interfaces isolate most graph reads and writes from the API layer.
- `mip_intel.storage.create_repository()` is the storage factory.
- PostgreSQL is intentionally not faked; selecting a PostgreSQL DSN raises a
  clear `NotImplementedError` until the real adapter is implemented.

## Current Production Gaps

- Distributed worker orchestration is still needed beyond local thread pools.
- DB2 extraction should evolve into a normalized SQL catalog with cursor usage,
  referential constraints, packages/plans, and generated test fixtures.
- PL/I and assembler are inventoried today, but need deeper parsers.
- Runtime/scheduler evidence should be ingested and reconciled with static graph facts.
- Authentication, authorization, tenant isolation, and audit trails are needed
  before enterprise deployment.
- LLM explanations should remain grounded in SQLite evidence and should never
  replace parser facts.
