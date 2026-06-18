# MIP Domain Model

## Aggregates

### Analysis Run

Owns the immutable snapshot of one repository scan: source root, files, assets, relationships, evidence, issues, and completion statistics.

### Source File

Represents one path and content hash. Classification is evidence, not identity.

### Asset

Represents a technical or business entity with stable type/name identity within a run.

### Relationship

A directed, typed, evidence-backed connection between assets.

### Evidence

Source path, line range, extractor, text, and confidence supporting an asset or relationship.

## Core invariants

- One source path appears once per analysis run.
- One asset type/name appears once per analysis run.
- Relationships always reference existing assets; unresolved targets become explicit placeholder assets.
- Confidence ranges from 0 to 1.
- Source evidence is immutable for a completed run.
- A new scan creates a new snapshot; it does not silently rewrite history.

## Cardinality examples

- Job 1 → many Job Steps
- Job Step 0..1 → Program via `EXECUTES`
- Program many ↔ many Program via `CALLS`
- Program many ↔ many Copybook via `USES_COPYBOOK`
- Program many ↔ many Table/Dataset/File via read/write relationships
- Copybook 1 → many Data Fields
- Program 1 → many extracted Rule Candidates
