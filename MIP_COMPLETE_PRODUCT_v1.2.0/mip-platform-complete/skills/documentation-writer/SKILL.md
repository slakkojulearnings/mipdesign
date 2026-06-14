---
name: documentation-writer
description: Creates and maintains evidence-linked MIP architecture, program, job, copybook, workflow, API, runbook, ADR, and user documentation. Use when generated or hand-written knowledge must be clear, canonical, and actionable.
license: Apache-2.0
compatibility: Designed for skills-aware coding agents working with the MIP repository.
metadata:
  author: mip-project
  version: "1.0"
---

# Documentation Writer

## Workflow

1. Identify audience and decision or task the document supports.
2. Link to source evidence or canonical models.
3. Preserve technical identifiers while adding reviewed readable names.
4. Separate observed facts, derived facts, inferences, and unknowns.
5. Use diagrams only when they clarify relationships.
6. Include setup or validation commands that have been executed.
7. Update the canonical index and avoid duplicate documents.

## Constraints

No unsupported performance claims, invented business intent, or stale screenshots. Generated pages must remain reproducible.

## Success Criteria

A reader can complete the intended task or decision without contacting the original author.

## Repository Rules

Follow `CLAUDE.md`, protect proprietary source, keep changes surgical, and run the relevant validation commands before completion.
