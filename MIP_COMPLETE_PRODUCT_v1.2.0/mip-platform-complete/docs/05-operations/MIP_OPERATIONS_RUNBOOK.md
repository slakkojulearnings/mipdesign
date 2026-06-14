# MIP Operations Runbook

## Install

```bash
python -m venv .venv
pip install -e ".[dev]"
```

## Analyze

```bash
mip analyze /path/to/source --db data/mip.db --output output
mip validate --db data/mip.db
```

## Start API

```bash
mip serve --db data/mip.db --host 0.0.0.0 --port 8000
```

## Backup

Stop writers or use SQLite online backup tooling. Preserve the database and corresponding generated run directory together.

## Recovery

The source repository remains authoritative. A database can be rebuilt by rerunning analysis. Preserve completed run databases when audit history matters.

## Troubleshooting

- Many UNKNOWN files: inspect folder/content signatures and add minimized classifier fixtures.
- Missing program calls: inspect fixed/free format and dynamic-call variables.
- Missing JCL datasets: verify continuation and symbolic parameter handling.
- Incorrect copybook length: inspect usage, sign, REDEFINES, OCCURS, and compiler-specific rules.
- API has no data: verify `MIP_DB_PATH` and run `mip stats`.
