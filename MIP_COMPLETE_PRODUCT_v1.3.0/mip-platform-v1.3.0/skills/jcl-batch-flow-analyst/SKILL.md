---
name: jcl-batch-flow-analyst
description: Analyzes JCL, PROCs, scheduler definitions, DD statements, utilities, datasets, and job sequencing. Use to discover batch roots, executed programs, dataset lineage, conditional execution, and end-to-end batch workflows.
license: Apache-2.0
compatibility: Works with skills-aware coding agents; repository workflows assume Python 3.12+, Git, and local file access.
metadata:
  author: mip-project
  version: "1.0"
---


# JCL Batch Flow Analyst

## Workflow

1. Extract JOB identity and parameters.
2. Resolve EXEC PGM and PROC calls.
3. Expand cataloged/in-stream procedures when sources exist.
4. Resolve symbolic parameters without inventing missing values.
5. Extract DD datasets, DISP semantics, temporary datasets, and generation references.
6. Classify each step as program, procedure, or utility.
7. Determine step conditions and restart implications.
8. Derive producer/consumer relationships from datasets.
9. Merge scheduler evidence when available.
10. Generate job and workflow documentation.

## Required Relationships

- job `CONTAINS_STEP` step
- step `EXECUTES` program
- step `READS_DATASET` dataset
- step `WRITES_DATASET` dataset
- job `RUNS_BEFORE` job when supported

## Success Criteria

The output can explain what starts the job, what each step runs, what data it consumes/produces, and which jobs depend on its outputs.

## Operating Rules

- Follow `CLAUDE.md`.
- Preserve source evidence and confidence.
- Do not modify `mfcode/`.
- Keep generated material under `knowledge/` or `output/`.
- Use the work ledger before processing repository artifacts.
- Report unresolved references and unknowns explicitly.
