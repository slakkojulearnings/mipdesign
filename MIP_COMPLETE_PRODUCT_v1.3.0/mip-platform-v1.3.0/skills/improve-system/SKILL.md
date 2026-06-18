---
name: improve-system
description: Reviews the current work session and improves the MIP Internal OS. Use after repeated corrections, newly learned lessons, stale guidance, duplicated files, or process failures to update skills, preserve experiences, and flag consolidation needs.
license: Apache-2.0
compatibility: Works with skills-aware coding agents; repository workflows assume Python 3.12+, Git, and local file access.
metadata:
  author: mip-project
  version: "1.0"
---


# Improve System

## Purpose

Turn session feedback into durable process improvement without broadly rewriting the repository.

## Workflow

1. Review what happened in the current session.
2. Identify:
   - repeated correction
   - missing instruction
   - stale guidance
   - duplicate guidance
   - successful reusable pattern
   - failure or near miss
3. Map the lesson to the smallest durable location:
   - skill instruction
   - reference file
   - template
   - `CLAUDE.md`
   - governance decision
   - experience note
4. Make a surgical update.
5. Add an experience file when a concrete story or lesson is reusable.
6. Flag duplicates instead of silently deleting canonical material.
7. Record the update in `memory/processed.log`.

## Output

- changed files
- reason for each change
- verification performed
- stale/duplicate items requiring human review

## Constraints

- Do not rewrite all skills for one local issue.
- Do not store confidential source content in experience files.
- Do not promote an anecdote to a global rule without evidence.

## Operating Rules

- Follow `CLAUDE.md`.
- Preserve source evidence and confidence.
- Do not modify `mfcode/`.
- Keep generated material under `knowledge/` or `output/`.
- Use the work ledger before processing repository artifacts.
- Report unresolved references and unknowns explicitly.
