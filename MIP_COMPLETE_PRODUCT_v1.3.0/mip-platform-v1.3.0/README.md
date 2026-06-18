# Mainframe Intelligence Platform

## MIP v1.3.0 — Advanced Intelligence

MIP is an open-source, evidence-driven platform for understanding and modernizing legacy application estates.

## v1.3 Capabilities

- compiler-oriented COBOL source expansion and semantic understanding
- nested COPY and COPY REPLACING
- conditional compilation directives
- symbol tables and dynamic CALL candidate resolution
- paragraph/control-flow analysis
- enterprise JCL PROC/INCLUDE/symbolic expansion
- structured business-rule extraction
- domain model discovery
- event discovery
- graph-backed service-boundary discovery
- modernization simulation
- persisted derived insights
- CLI, FastAPI, SQLite, NetworkX, and optional Google ADK integration

## Install on Windows

```powershell
cd F:\mip-platform
py -3.12 -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -e ".[dev]"
```

## Run Complete Advanced Analysis

```powershell
mip advanced-analyze F:\legacy-source `
  --db data\mip.db `
  --output output `
  --copybook-dir F:\legacy-source\copybooks `
  --proclib F:\legacy-source\proclib
```

## Key Commands

```powershell
mip cobol-understand <program> --copybook-dir <copybooks>
mip jcl-expand <job> --proclib <proclib>
mip rules-extract --db data\mip.db
mip domain-discover --db data\mip.db
mip events-discover --db data\mip.db
mip services-discover --db data\mip.db
mip simulate <asset> --scenario extract-service --db data\mip.db
mip insights --db data\mip.db
mip serve --db data\mip.db
```

## Architecture Principle

```text
Source → Deterministic Metadata → Relationships → Graph → Intelligence → Modernization
```

AI may explain or rank results, but it does not replace source evidence, deterministic analysis, validation, or human approval.

## Documentation

- `docs/06-advanced/MIP_ADVANCED_INTELLIGENCE_ARCHITECTURE.md`
- `docs/06-advanced/MIP_V1_3_RUNBOOK.md`
- `docs/06-advanced/MIP_V1_3_SCOPE_AND_LIMITS.md`
- `MIP_V1_3_RELEASE_REPORT.md`

## License

Apache License 2.0.
