---
name: cobol-documentation-translator
description: Explains and documents COBOL programs for engineers who do not know COBOL. Use to analyze program purpose, paragraphs, files, copybooks, calls, SQL/CICS usage, control flow, business rules, errors, and evidence-linked Java-oriented explanations.
license: Apache-2.0
compatibility: Works with skills-aware coding agents; repository workflows assume Python 3.12+, Git, and local file access.
metadata:
  author: mip-project
  version: "1.0"
---


# COBOL Documentation Translator

## Purpose

Create an evidence-backed program page that helps a modern engineer understand a COBOL program without hiding mainframe semantics.

## Inputs

- one claimed COBOL source file
- resolved copybooks when available
- related JCL and relationship index
- documentation template

## Workflow

1. Confirm the artifact is claimed and not already complete.
2. Extract program identity and execution type.
3. Describe divisions and important data structures.
4. List files, tables, datasets, transactions, copybooks, and called programs.
5. Summarize paragraph/section responsibilities.
6. Reconstruct major control flow and control-break logic.
7. Extract business rules with source ranges.
8. Explain mainframe-specific behavior in Java terms without proposing translation prematurely.
9. Record unresolved dynamic calls and missing copybooks.
10. Update catalog and relationships.
11. Mark the todo item complete only after validation.

## Output Sections

- Technical identity
- Readable name and confidence
- Business purpose
- Inputs and outputs
- Dependencies
- Processing flow
- Business rules
- Error handling
- Java developer notes
- Evidence
- Unknowns

## Parallel Use

Multiple instances may run only on distinct claimed source paths. Shared-ledger writes must use serialized helpers.

## Operating Rules

- Follow `CLAUDE.md`.
- Preserve source evidence and confidence.
- Do not modify `mfcode/`.
- Keep generated material under `knowledge/` or `output/`.
- Use the work ledger before processing repository artifacts.
- Report unresolved references and unknowns explicitly.
