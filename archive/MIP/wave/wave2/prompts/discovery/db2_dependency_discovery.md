# Enterprise Database Dependency Discovery

> Prompt 05 · Category: Discovery · Skills: [mainframe-code-analyst](../../batch2/skills_framework/skills/mainframe-code-analyst/skill.md), [security-compliance-analyst](../../batch2/skills_framework/skills/security-compliance-analyst/skill.md)
> Honors [MIP Engineering Principles](../../batch2/skills_framework/MIP_ENGINEERING_PRINCIPLES.md).

## Purpose
Identify all database dependencies and construct foundational data lineage intelligence.

## Context
Database dependencies are critical for modernization, compliance, and impact analysis.

## Inputs
COBOL source files containing EXEC SQL.

## Instructions
**Extract:** Tables · Views · Aliases · Synonyms · Cursors · Joins · CRUD Operations · Host Variables · Stored Procedures · Triggers · Packages.

**Capture:** Read Patterns · Write Patterns · Update Frequencies · Shared Data Usage.

**Identify:** Critical Tables · Shared Tables · Master Data · Reference Data · High-Risk Tables · Compliance-Sensitive Tables.

**Generate:** Dependency Matrix · Data Flow Analysis · Data Lineage Foundations · Risk Assessment.

## Expected Output
- Table Inventory `| Table | Operation | Program |`
- DB2 Dependency Matrix
- Shared Tables
- Critical Tables
- Data Lineage Summary
- High-Risk Tables

## Constraints
Use SQL evidence only. Attach confidence to inferred or dynamically-constructed SQL targets.

## Success Criteria
All database dependencies are represented and traceable.

## Example Usage
Analyze EXEC SQL statements and generate a DB2 dependency report.

## Review Checklist
- Tables identified?
- Operations classified?
- Shared tables identified?
- Critical tables identified?
- Lineage foundations generated?
