---
name: repository-discovery
description: Inventories and classifies large legacy repositories, including files without extensions. Use for initial scans, artifact counts, source hashing, todo generation, unknown-file detection, and repository architecture summaries.
license: Apache-2.0
compatibility: Works with skills-aware coding agents; repository workflows assume Python 3.12+, Git, and local file access.
metadata:
  author: mip-project
  version: "1.0"
---


# Repository Discovery

## Purpose

Create a complete, reproducible repository inventory before parsing or modernization.

## Inputs

- repository root
- optional classification rules
- ignored-path policy

## Workflow

1. Scan every regular file.
2. Record relative path, size, hash, encoding indicators, and content signature.
3. Classify from content first and naming/folder evidence second.
4. Create unresolved classification when confidence is insufficient.
5. Reconcile inventory count with filesystem count.
6. Seed `memory/todo.list`.
7. Produce repository statistics and an unknown-artifact report.

## Required Outputs

- inventory file
- artifact counts
- unknown files
- todo ledger
- repository architecture summary
- scan errors

## Success Criteria

- every file is represented exactly once
- source hashes are present
- ignored files are explicitly reported
- rerunning without changes produces the same inventory

## Operating Rules

- Follow `CLAUDE.md`.
- Preserve source evidence and confidence.
- Do not modify `mfcode/`.
- Keep generated material under `knowledge/` or `output/`.
- Use the work ledger before processing repository artifacts.
- Report unresolved references and unknowns explicitly.
