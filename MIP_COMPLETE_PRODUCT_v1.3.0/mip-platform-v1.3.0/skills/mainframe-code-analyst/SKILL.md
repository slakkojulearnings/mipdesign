---
name: mainframe-code-analyst
description: Analyzes legacy source across COBOL, JCL, copybooks, SQL, CICS, VSAM, IMS, MQ, and related artifacts. Use for evidence-backed explanations, dependencies, entry points, data access, and unresolved mainframe semantics.
license: Apache-2.0
compatibility: Designed for skills-aware coding agents working with the MIP repository.
metadata:
  author: mip-project
  version: "1.0"
---

# Mainframe Code Analyst

## Purpose

Explain source behavior and relationships without inventing business meaning.

## Workflow

1. Identify artifact type from source evidence.
2. Preserve original line numbers, fixed columns, continuations, and encoding.
3. Extract identities, inputs, outputs, calls, copybooks, data stores, runtime entry points, rules, and errors.
4. Distinguish static references from dynamic or unresolved references.
5. Record each fact with source path, line range, extractor, and confidence.
6. Update the canonical catalog and relationship model.
7. Flag compiler-, scheduler-, or installation-specific behavior for review.

## Outputs

- structured metadata
- evidence-backed explanation
- dependencies and entry points
- unresolved questions

## Constraints

Do not translate source or assign business capability names unless that is the explicit reviewed task.

## Success Criteria

A second engineer can reproduce every material conclusion from the cited source.

## Repository Rules

Follow `CLAUDE.md`, protect proprietary source, keep changes surgical, and run the relevant validation commands before completion.
