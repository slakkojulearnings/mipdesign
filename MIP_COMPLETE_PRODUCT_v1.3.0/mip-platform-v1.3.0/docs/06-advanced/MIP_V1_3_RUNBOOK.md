# MIP v1.3 Advanced Runbook

## Install

```powershell
cd F:\mip-platform
py -3.12 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
pip install -e ".[dev]"
```

## Complete Advanced Analysis

```powershell
mip advanced-analyze F:\legacy-source `
  --db data\mip.db `
  --output output `
  --copybook-dir F:\legacy-source\copybooks `
  --proclib F:\legacy-source\proclib `
  --define TESTMODE `
  --symbol ENV=DEV
```

## COBOL Semantic Understanding

```powershell
mip cobol-understand F:\legacy-source\cbl\PROGRAM1 `
  --copybook-dir F:\legacy-source\copybooks `
  --define FEATURE_A `
  --output output\PROGRAM1.semantic.json
```

## JCL Expansion

```powershell
mip jcl-expand F:\legacy-source\jcl\DAILYJOB `
  --proclib F:\legacy-source\proclib `
  --symbol ENV=PROD `
  --output output\DAILYJOB.expanded.json
```

## Intelligence Commands

```powershell
mip rules-extract --db data\mip.db
mip domain-discover --db data\mip.db
mip events-discover --db data\mip.db
mip services-discover --db data\mip.db
mip simulate PROGRAM1 --scenario extract-service --db data\mip.db
mip intelligence-generate --db data\mip.db --output output\intelligence
mip insights --db data\mip.db
```

## API

```powershell
mip serve --db data\mip.db
```

Important endpoints:

- `/intelligence/business-rules`
- `/intelligence/domain-model`
- `/intelligence/events`
- `/intelligence/service-boundaries`
- `/modernization/simulate/{target}`
- `/insights`

## Verification

```powershell
ruff check .
ruff format --check .
mypy src/mip
pytest --cov=mip
python scripts\validate_skills.py
python scripts\validate_memory_indices.py
```
