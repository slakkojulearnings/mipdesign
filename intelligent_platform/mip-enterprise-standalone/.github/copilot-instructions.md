# GitHub Copilot Instructions

You are working in the standalone **MIP Enterprise Intelligence** package.

Follow these rules:

- Preserve evidence, confidence, validation status, and source citations on all
  graph facts.
- Do not fabricate missing source, missing copybooks, dynamic calls, table
  ownership, or domain names. Mark uncertain facts as inferred or needs review.
- Keep graph queries bounded. Use `graph-slice`, search, coverage, matrices,
  required-files, and exports instead of full graph rendering.
- Keep SQLite v1 portable. Avoid leaking SQLite-specific logic above repository
  boundaries unless the storage layer owns it.
- Keep UI changes consistent with the React app and avoid rendering huge graphs.
- Run focused tests after parser, graph, repository, or UI contract changes.

Useful commands:

```powershell
.\.venv\Scripts\python -m unittest discover -s tests -v
.\.venv\Scripts\python -m mip_intel.cli --db data\my-estate.db validate
cd frontend
npm run build
```

Common scripts:

```bat
.\scan_codebase.bat "F:\path\to\source_code" data\my-estate.db my-run-001
.\start_ui.bat data\my-estate.db
.\check_ui.bat
.\stop_ui.bat
```
