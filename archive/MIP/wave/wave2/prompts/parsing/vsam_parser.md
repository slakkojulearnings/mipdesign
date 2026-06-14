# VSAM Parser Architecture

> Prompt 10 · Category: Parsing · Skill: [mainframe-code-analyst](../../batch2/skills_framework/skills/mainframe-code-analyst/skill.md)
> Honors [MIP Engineering Principles](../../batch2/skills_framework/MIP_ENGINEERING_PRINCIPLES.md).

## Purpose
Design parser architecture for VSAM metadata extraction.

## Context
Many mainframe systems rely heavily on VSAM. VSAM relationships are critical modernization inputs.

## Inputs
COBOL source code and VSAM definitions.

## Instructions
Support extraction of:
- **VSAM Objects:** KSDS · ESDS · RRDS
- **Access Methods:** READ · WRITE · REWRITE · DELETE · START
- **Relationships:** Program → VSAM · Job → VSAM

Generate architecture and metadata model.

## Expected Output
- Parser Design
- Metadata Schema
- Relationship Model
- Validation Rules

## Constraints
Do not infer business semantics. Attach confidence to inferred dataset relationships.

## Success Criteria
VSAM usage becomes traceable and graph-ready.

## Example Usage
Analyze VSAM dependencies in a core banking platform.

## Review Checklist
- Access patterns captured?
- Dataset relationships captured?
- CRUD operations represented?
- Metadata graph ready?

---

## Part 2 — Parsing Completion Criteria
On completion, MIP can convert raw source into structured metadata and answer: which programs exist; which jobs execute them; which copybooks define data; which DB2 tables are accessed; which VSAM files are used; which dependencies exist. Only after parsing should metadata modeling begin.
