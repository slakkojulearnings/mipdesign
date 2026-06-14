# Canonical Entities

> The technology-agnostic vocabulary of the platform. One representation regardless of
> source dialect. Implemented as Pydantic v2 types in [`models.py`](models.py) and
> SQLite tables in [`schema.sql`](schema.sql).

## The evidence envelope (on every entity and relationship)

This is what makes MIP **resilient and auditable** (Principles 1–3). Nothing exists in
the model without it.

| Field | Type | Meaning |
|-------|------|---------|
| `source_evidence` | text | `file:line` / `paragraph` / `scan:path` |
| `discovery_method` | enum | `scan · static-parse · ast · data-flow · semantic · runtime · inference` |
| `confidence` | 0.0–1.0 | strength of belief |
| `validation_status` | enum | `confirmed · inferred · needs_review` |
| `discovered_at` | timestamp | when found |

> **Rule:** anything not directly proven is `inferred` or `needs_review` with
> confidence < 1.0. Dynamic calls, semantic groupings, and unresolved targets are
> *kept* (not dropped) and flagged — never presented as `confirmed`.

## Entities

| Entity | Identity | Key fields | Level |
|--------|----------|------------|-------|
| **Artifact** | `artifact_id` (hash of path) | path, artifact_type, line_count | 1 — inventory |
| **Program** | `program_id` (PROGRAM-ID) | program_name, language, line_count | 2 — metadata |
| **Job** | `job_id` (JOB name) | job_name | 2 |
| **JobStep** | `step_id` | job_id, step_name, **program_name** (EXEC PGM=) | 2 |
| **Copybook** | `copybook_id` | copybook_name | 2 |
| **Db2Table** | `table_id` | table_name | 2 |

`Capability`, `Application`, `Domain`, `Dataset`, `Transaction` are part of the full
model (see the metadata prompts in [`../04-prompts/metadata`](../04-prompts/metadata))
and are added in later phases; v0.1 implements the six above — enough to answer the
root-driver and call-graph questions.

## Why `JobStep.program_name` is a plain string (not a foreign key)

A JCL `EXEC PGM=X` may name a program whose source isn't in the repository, or whose
name is built dynamically. Storing it as a resolvable-or-not **name** (with an evidence
envelope) lets discovery proceed on partial estates — Principle 2 (resilience). The
graph layer resolves it to a `Program` when one exists, and flags it `needs_review`
when it can't.

## Mapping to the source dialects

| Entity | COBOL | JCL | DB2 | Copybook |
|--------|-------|-----|-----|----------|
| Program | `PROGRAM-ID` | — | — | — |
| Job / JobStep | — | `//NAME JOB`, `//STEP EXEC PGM=` | — | — |
| Copybook | `COPY x` (use) | — | — | the member itself |
| Db2Table | `EXEC SQL ... tbl` | — | `CREATE TABLE` | — |
