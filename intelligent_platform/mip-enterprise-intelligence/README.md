# MIP Enterprise Intelligence

Production-oriented mainframe intelligence platform for very large, extensionless
source estates. The first implementation keeps SQLite as the system of record and
serves bounded graph slices to a React explorer, rather than attempting to render a
full 200K+ file enterprise graph in the browser.

## Current slice

- SQLite schema for runs, source members, assets, relationships, evidence, summaries,
  graph slice cache, and insights.
- Repository abstraction with a SQLite implementation so PostgreSQL can be added later
  behind the same service contracts.
- Graph services for search-first navigation, root portfolio, progressive graph slices,
  application clusters, node profiles, edge evidence, heatmap/matrix summaries, and
  export payloads.
- React application scaffold for dashboard, search, bounded graph view, and detail
  drawer.

## Run backend checks

```powershell
cd F:\mip\mip_structure\intelligent_platform\mip-enterprise-intelligence
python -m unittest discover -s tests
$env:PYTHONPATH='src'; python -m mip_intel.cli --db data\demo.db init-demo
$env:PYTHONPATH='src'; python -m mip_intel.cli --db data\demo.db roots
$env:PYTHONPATH='src'; python -m mip_intel.cli --db data\demo.db graph-slice --root <asset_id_from_roots> --depth 2 --limit 500
```

## Run React UI

```powershell
cd frontend
npm install
npm run dev
```

The UI expects API responses shaped like the backend service contracts in
`src/mip_intel/api.py`.
