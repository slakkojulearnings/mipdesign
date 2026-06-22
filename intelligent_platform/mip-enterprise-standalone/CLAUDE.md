# Claude Code Instructions For MIP Enterprise Intelligence

This standalone folder is a portable mainframe intelligence application. Use it
as the project root when working with Claude Code.

## Operating Principles

- Understand before transforming: Inventory -> Metadata -> Graph -> Reasoning
  -> Copilot -> Modernization.
- Evidence and confidence are mandatory. Do not present inferred or unresolved
  facts as confirmed.
- Partial source is expected. Keep unresolved calls, missing copybooks, parse
  issues, and low-confidence findings visible.
- Prefer bounded graph slices and search-first workflows over full graph loads.
- Keep edits scoped and verify with tests or CLI commands.

## Useful Claude Assets

- `.claude\agents\` - project agent prompts.
- `.claude\skills\` - Claude-compatible MIP skills.
- `.agents\skills\` - Codex/GPT-compatible MIP skills.
- `03-skills\` and `04-prompts\` - canonical skill and prompt library.

## Setup Commands

```powershell
python -m venv .venv
.\.venv\Scripts\python -m pip install -e ".[api,dev]"
cd frontend
npm install
npm run build
cd ..
```

## Run Commands

```bat
.\scan_codebase.bat "F:\path\to\source_code" data\my-estate.db my-run-001
.\start_ui.bat data\my-estate.db
.\check_ui.bat
.\stop_ui.bat
```

## Validation

```powershell
.\.venv\Scripts\python -m unittest discover -s tests -v
.\.venv\Scripts\python -m mip_intel.cli --db data\my-estate.db validate
```

## Safety

Do not commit machine-specific files, secrets, generated DBs, runtime logs,
virtual environments, or node modules. Personal Claude overrides belong in
`.claude\settings.local.json`, which is ignored.
