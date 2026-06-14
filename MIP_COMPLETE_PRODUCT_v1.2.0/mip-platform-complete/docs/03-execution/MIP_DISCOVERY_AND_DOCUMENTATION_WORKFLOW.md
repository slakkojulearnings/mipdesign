# MIP Discovery and Documentation Workflow

## Goal

Document a large codebase completely without processing files twice or silently missing files.

## Workflow

### 1. Inventory

Scan all files recursively. Classify using:

- folder evidence
- content signatures
- naming evidence
- extension when present

Do not depend on extensions alone.

### 2. Seed Todo Ledger

Create one row per file in `memory/todo.list`.

### 3. Parallel Claims

Each worker claims an item through `scripts/claim_todo_item.py`.

### 4. Artifact Analysis

Use the matching skill:

- COBOL program → `cobol-documentation-translator`
- JCL/PROC → `jcl-batch-flow-analyst`
- copybook → `copybook-data-modeler`
- cross-artifact flow → `dependency-graph-builder`

### 5. Generate Knowledge

Write to the matching `knowledge/` directory using templates.

### 6. Update Indexes

Append or update:

- `catalog.txt`
- `relationships.txt`
- `processed.log`

### 7. Validate

Run:

```bash
python scripts/validate_memory_indices.py
```

### 8. Generate Diagrams

Use relationships, not free-form recollection, to create Mermaid diagrams.

## Required Program Documentation

- identity and readable name
- purpose with evidence
- execution type
- inputs and outputs
- called programs
- used copybooks
- files/tables read and written
- paragraphs and major control flow
- business rules
- error handling
- unresolved references
- evidence and confidence

## Required Repository Architecture Summary

- directory tree and purpose
- artifact counts
- online and batch entry points
- storage technologies
- daily/periodic workflows
- external interfaces
- unresolved areas
- confidence and coverage
