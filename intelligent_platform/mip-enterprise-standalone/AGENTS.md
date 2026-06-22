# Working In This Standalone MIP Package

This folder is the portable application package for **MIP Enterprise Intelligence**.
It scans mainframe source into SQLite, builds evidence-backed graph facts, and
serves a React UI for modernization discovery.

## Agent Rules

1. Keep facts evidence-backed. Every node, edge, insight, and explanation must
   preserve confidence and validation status.
2. Degrade gracefully. Missing copybooks, dynamic calls, malformed source, and
   binary files are normal; keep gaps visible instead of fabricating facts.
3. Keep graph views bounded. Use graph slices, searches, matrices, and exports;
   do not try to render the full enterprise graph in the browser.
4. Make surgical changes. Touch only files needed for the task and keep generated
   runtime output out of source control.
5. Test before claiming done.

## Important Paths

- `src\mip_intel\` - backend, parsers, graph services, SQLite repositories.
- `frontend\` - React UI.
- `tests\` - backend regression tests.
- `.agents\`, `.claude\skills\`, `03-skills\` - reusable AI skills.
- `04-prompts\` - reusable prompt library.
- `IMPLEMENTATION_LOGIC.md` - parsing, insight, clustering, and export logic.

## Common Commands

```powershell
python -m venv .venv
.\.venv\Scripts\python -m pip install -e ".[api,dev]"
cd frontend
npm install
npm run build
cd ..
```

```bat
.\scan_codebase.bat "F:\path\to\source_code" data\my-estate.db my-run-001
.\start_ui.bat data\my-estate.db
.\check_ui.bat
.\stop_ui.bat
```

```powershell
.\.venv\Scripts\python -m unittest discover -s tests -v
.\.venv\Scripts\python -m mip_intel.cli --db data\my-estate.db validate
```

## Do Not Commit

Do not commit `.venv`, `frontend\node_modules`, `data`, `logs`, `runtime`,
`__pycache__`, `.pytest_cache`, or `.claude\settings.local.json`.
