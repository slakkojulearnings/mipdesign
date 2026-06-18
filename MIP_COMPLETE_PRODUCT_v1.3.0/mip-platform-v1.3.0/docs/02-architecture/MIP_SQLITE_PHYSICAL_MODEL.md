# MIP SQLite Physical Model

The executable schema is `src/mip/persistence/schema.sql`.

## Tables

- `scan_run`: immutable analysis snapshot and aggregate counts
- `source_file`: path, hash, classification, encoding, parse status
- `asset`: canonical entity identity, attributes, status, confidence
- `relationship`: typed directed edges with attributes and confidence
- `evidence`: source-linked support for assets and relationships
- `parse_issue`: isolated parser warnings and errors
- `validation_result`: persistent quality checks for future workflow use

## Local-operability decisions

- WAL mode improves local read/write concurrency.
- Stable UUID5 identifiers make reruns deterministic within a scan.
- JSON attributes allow parser evolution without table proliferation.
- Indexed source, target, name, type, and evidence paths support core queries.
- Full runs are retained for comparison and audit.

## PostgreSQL evolution

Preserve logical entities and IDs. Replace SQLite JSON text with JSONB, add tenant/repository keys, use managed migrations, and introduce job queues only after concurrency measurements require them.
