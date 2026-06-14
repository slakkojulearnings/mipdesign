---
name: metadata-modeler
description: Designs and reviews canonical MIP assets, relationships, evidence, confidence, versioning, and persistence mappings. Use when adding an artifact type, relationship type, parser output, schema field, or compatibility change.
license: Apache-2.0
compatibility: Designed for skills-aware coding agents working with the MIP repository.
metadata:
  author: mip-project
  version: "1.0"
---

# Metadata Modeler

## Purpose

Keep all MIP engines aligned to one canonical language.

## Workflow

1. Identify the real business or technical entity.
2. Decide whether it is an asset, relationship, attribute, evidence item, or run state.
3. Define identity, required attributes, cardinality, direction, confidence, and lifecycle.
4. Check ontology compatibility and backward impact.
5. Map to Pydantic, SQLite, graph, API, and portable index formats.
6. Add validation and migration tests.

## Constraints

Do not encode UI concerns or parser-specific temporary state in canonical entities. Preserve unknowns explicitly.

## Success Criteria

The concept has one meaning across parsers, storage, graph queries, APIs, reports, and agents.

## Repository Rules

Follow `CLAUDE.md`, protect proprietary source, keep changes surgical, and run the relevant validation commands before completion.
