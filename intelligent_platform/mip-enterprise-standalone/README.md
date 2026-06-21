# MIP Enterprise Intelligence

Production-oriented mainframe intelligence platform for very large, extensionless
source estates. The first implementation keeps SQLite as the system of record and
serves bounded graph slices to a React explorer, rather than attempting to render a
full 200K+ file enterprise graph in the browser.

## Current slice

- SQLite schema for runs, source members, graph nodes, graph edges, evidence, summaries,
  graph slice cache, and insights.
- Repository abstraction with a SQLite implementation so PostgreSQL can be added later
  behind the same service contracts.
- Graph services for search-first navigation, root portfolio, progressive directed graph slices,
  application clusters, node profiles, edge evidence, heatmap/matrix summaries, and
  export payloads.
- ANTLR-backed COBOL extraction with COPY REPLACING, DB2/CICS facts, data
  dictionary semantics, field lineage, paragraph flow, CALL/LINKAGE contracts,
  CICS contracts, file I/O semantics, business-rule/transformation graph facts,
  statement ordering, SORT/MERGE, JCL DD/GDG/return-code flow, parser cache,
  process workers, and hard-timeout quarantine.
- Node coverage reports for parser, copybook, call contract, data dictionary,
  field lineage, control-flow, DB2, DCLGEN, CICS, file I/O, JCL DD binding,
  statement ordering, SORT/MERGE, and business-rule capture.
- Discovery excludes `.git` folders and records feedback-loop progress through
  discovery, parsing, persistence, validation, summarization, and completion.
- React application for dashboard, search, bounded graph view, flow diagram,
  dependency matrix, architecture views, AST tree, required files, and detail
  drawer.

## Run backend checks

```powershell
cd F:\mip\mip_structure\intelligent_platform\mip-enterprise-intelligence
python -m unittest discover -s tests
python -m coverage run -m unittest discover -s tests
python -m coverage report
$env:PYTHONPATH='src'; python -m mip_intel.cli --db data\demo.db init-demo
$env:PYTHONPATH='src'; python -m mip_intel.cli --db data\demo.db roots
$env:PYTHONPATH='src'; python -m mip_intel.cli --db data\demo.db nodes --scope programs --limit 20
$env:PYTHONPATH='src'; python -m mip_intel.cli --db data\demo.db graph-slice --root CRDPOST --direction downstream --depth 2 --limit 500
$env:PYTHONPATH='src'; python -m mip_intel.cli --db data\demo.db coverage CRDPOST
$env:PYTHONPATH='src'; python -m mip_intel.cli --db data\demo.db export --format json --limit 50000 --output data\graph-export.json
```

## Run React UI

```powershell
cd frontend
npm install
npm run dev
```

The UI expects API responses shaped like the backend service contracts in
`src/mip_intel/api.py`.

For the implemented parsing, clustering, insight, and export rules, see
`IMPLEMENTATION_LOGIC.md`. For the Claude-review response and remaining
production gaps, see `PRODUCTION_READINESS_RESPONSE.md`.
