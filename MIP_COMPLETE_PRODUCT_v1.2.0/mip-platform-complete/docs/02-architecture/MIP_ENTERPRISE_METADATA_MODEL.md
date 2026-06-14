# MIP Enterprise Metadata Model

## Canonical Asset

Every asset contains:

```yaml
asset_id: stable unique identifier
asset_type: program|job|job-step|copybook|dataset|table|column|transaction|rule|capability|service
technical_name: original source identifier
readable_name: human-readable proposed or approved name
source_path: repository-relative path
content_hash: hash of source content
status: discovered|parsed|validated|blocked|retired
confidence: 0.0 to 1.0
review_status: unreviewed|reviewed|approved|rejected
```

## Evidence

```yaml
evidence_id:
asset_id:
relationship_id:
source_path:
line_start:
line_end:
extractor:
evidence_text:
confidence:
```

## Core Relationships

- `CALLS`: program → program
- `EXECUTES`: job-step → program
- `CONTAINS_STEP`: job → job-step
- `USES_COPYBOOK`: program/copybook → copybook
- `READS_DATASET`: program/job-step → dataset
- `WRITES_DATASET`: program/job-step → dataset
- `READS_TABLE`: program → table
- `WRITES_TABLE`: program → table
- `STARTS_PROGRAM`: transaction → program
- `RUNS_BEFORE`: job → job
- `IMPLEMENTS_RULE`: program/paragraph → rule
- `SUPPORTS_CAPABILITY`: asset → capability
- `CANDIDATE_FOR`: asset cluster → service

## Identity Rules

- Technical identity is never replaced by a readable name.
- Use repository-relative path plus technical identifier where names are not globally unique.
- Relationships reference stable IDs, not display names.
- Unknown targets are represented as unresolved assets, not discarded.

## Confidence Rules

- 1.00: explicit static declaration
- 0.90–0.99: deterministic resolution with complete context
- 0.70–0.89: deterministic but partially unresolved
- 0.40–0.69: evidence-supported inference
- below 0.40: hypothesis; excluded from automated decisions
