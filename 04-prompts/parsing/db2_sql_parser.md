# DB2 SQL Parser Architecture

> Prompt 09 · Category: Parsing · Skill: [mainframe-code-analyst](../../03-skills/mainframe-code-analyst/SKILL.md)
> Honors [MIP Engineering Principles](../../03-skills/MIP_ENGINEERING_PRINCIPLES.md).

## Purpose
Design parser architecture for embedded DB2 SQL.

## Context
SQL statements reveal: data dependencies, CRUD operations, data lineage, integration points.

## Inputs
EXEC SQL blocks.

## Instructions
Support extraction of:
- **Objects:** Tables · Views · Aliases
- **Operations:** SELECT · INSERT · UPDATE · DELETE
- **Access Patterns:** Joins · Predicates · Cursors
- **Relationships:** Program → Table · Program → View

Generate metadata architecture.

## Expected Output
- Parser Architecture
- Dependency Model
- Metadata Schema
- Validation Rules

## Constraints
Focus only on metadata extraction. Dynamically-built SQL must be flagged with confidence, not silently skipped.

## Success Criteria
All SQL dependencies become graph-ready metadata.

## Example Usage
Analyze DB2 usage across an enterprise card-processing application.

## Review Checklist
- CRUD extraction supported?
- Table extraction supported?
- Join extraction supported?
- Cursor extraction supported?
