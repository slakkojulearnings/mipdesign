# MIP Enterprise Intelligence Standalone

Use this folder as the portable Windows package for scanning a mainframe source
tree into SQLite and exploring it in the React UI.

## Requirements

- Windows 10/11 or Windows Server.
- Python 3.11 or later.
- Node.js 18 or later.
- Internet access once for Python/npm install, unless dependencies are already cached.

## First-Time Setup

Open PowerShell in this folder:

```powershell
cd F:\mip\mip_structure\intelligent_platform\mip-enterprise-standalone

python -m venv .venv
.\.venv\Scripts\python -m pip install --upgrade pip
.\.venv\Scripts\python -m pip install -e ".[api,dev]"

cd frontend
npm install
npm run build
cd ..
```

## Scan Source Code

```bat
.\scan_codebase.bat "F:\path\to\source_code" data\my-estate.db my-run-001
```

Arguments:

- `source_code`: required source folder.
- `data\my-estate.db`: optional SQLite DB path. Default is `data\mip-intel.db`.
- `my-run-001`: optional run id. Default is `manual-scan`.

The scan excludes `.git` folders, writes facts to SQLite, and runs validation.

## Start, Check, Stop UI

```bat
.\start_ui.bat data\my-estate.db
.\check_ui.bat
.\stop_ui.bat
```

Open the UI at:

```text
http://127.0.0.1:5174
```

Optional ports:

```bat
.\start_ui.bat data\my-estate.db 8010 5175
.\check_ui.bat 8010 5175
.\stop_ui.bat 8010 5175
```

Logs are written to `logs\`. Process ids are written to `runtime\`.

## Useful CLI Checks

```bat
.\.venv\Scripts\python -m mip_intel.cli --db data\my-estate.db stats
.\.venv\Scripts\python -m mip_intel.cli --db data\my-estate.db validate
.\.venv\Scripts\python -m mip_intel.cli --db data\my-estate.db roots --limit 50
.\.venv\Scripts\python -m mip_intel.cli --db data\my-estate.db search CUST --limit 20
.\.venv\Scripts\python -m mip_intel.cli --db data\my-estate.db graph-slice --root CUST001 --direction both --depth 3 --limit 500
```

## What Is Included

- Backend source under `src\`.
- React UI under `frontend\`.
- Built UI under `frontend\dist\`.
- Tests under `tests\`.
- Skills and prompts under `.agents\`, `03-skills\`, and `04-prompts\`.
- Detailed implementation notes in `IMPLEMENTATION_LOGIC.md`.

Generated folders such as `.git`, `node_modules`, `data`, `logs`, caches, and
virtual environments are intentionally not included.
