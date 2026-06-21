# Job Metadata Model

> Prompt 12 · Category: Metadata · Skill: [metadata-modeler](../../03-skills/metadata-modeler/SKILL.md)
> Honors [MIP Engineering Principles](../../03-skills/MIP_ENGINEERING_PRINCIPLES.md).

## Purpose
Create canonical representation of batch jobs.

## Context
Batch jobs are often true system entry points.

## Inputs
JCL Metadata.

## Instructions
Design Job entity. Include: Job Name · Steps · Programs · Procedures · Datasets. Carry the evidence envelope on the entity and its relationships.

**Generate:** Metadata Model · Graph Representation · Lineage Mapping.

## Expected Output
- Job Entity Definition
- Relationship Model
- Validation Rules

## Constraints
Support large enterprise batch ecosystems. Evidence envelope mandatory.

## Success Criteria
Job execution flows become graph-ready.

## Review Checklist
- Steps/programs/datasets modeled?
- Lineage mapping defined?
- Evidence envelope present?
