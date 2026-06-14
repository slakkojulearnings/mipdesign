# DB2 Metadata Model

> Prompt 14 · Category: Metadata · Skill: [metadata-modeler](../../03-skills/metadata-modeler/SKILL.md)
> Honors [MIP Engineering Principles](../../03-skills/MIP_ENGINEERING_PRINCIPLES.md).

## Purpose
Represent database dependencies consistently.

## Context
DB2 objects often become future microservice boundaries.

## Inputs
DB2 Metadata.

## Instructions
Design metadata for: Tables · Views · Aliases · Indexes.
**Capture:** CRUD Usage · Access Frequency · Sharing Level. Carry the evidence envelope.

## Expected Output
- DB2 Entity Model
- Relationship Definitions
- Migration Metadata

## Constraints
Support modernization/microservice-boundary analysis. Evidence envelope mandatory.

## Success Criteria
Database dependencies support modernization analysis.

## Review Checklist
- Tables/views/aliases/indexes modeled?
- CRUD usage and sharing level captured?
- Migration metadata defined?
- Evidence envelope present?
