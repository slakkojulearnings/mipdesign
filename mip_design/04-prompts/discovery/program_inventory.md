# COBOL Program Discovery and Execution Intelligence

> Prompt 02 · Category: Discovery · Skill: [mainframe-code-analyst](../../03-skills/mainframe-code-analyst/SKILL.md)
> Honors [MIP Engineering Principles](../../03-skills/MIP_ENGINEERING_PRINCIPLES.md).

## Purpose
Build a complete inventory of COBOL programs and identify execution architecture, dependencies, complexity, and modernization readiness.

## Context
Programs are the primary execution units of most mainframe systems. Discovery should reveal: what programs exist, how they interact, which are critical, which are obsolete, which are modernization candidates.

## Inputs
COBOL source files.

## Instructions
**Extract:** PROGRAM-ID · Author · Compilation Options · Called Programs · Calling Programs · Dynamic Calls · Copybooks · Files Referenced · Tables Referenced · MQ Usage · CICS Usage · IMS Usage · External Interfaces · APIs · Batch Dependencies.

**Capture:** Cyclomatic Complexity · Structural Complexity · Program Size · Maintainability Indicators · Technical Debt Indicators.

**Identify:** Root Programs · Utility Programs · Shared Components · Dead Programs · Circular Dependencies · High-Risk Programs.

**Generate:** Dependency Maps · Program Risk Scores · Modernization Readiness Scores.

## Expected Output
- Program Inventory `| Program | Path | Type | Complexity | Risk |`
- Dependency Summary
- Root Program Candidates
- Shared Components
- Dead Code Candidates
- Modernization Readiness Assessment
- Missing Information

## Constraints
Use source code evidence only. Dynamic/unresolved calls must be emitted with a confidence score and `Needs Review` status — never dropped, never asserted as confirmed.

## Success Criteria
All COBOL programs are represented with dependency and risk intelligence.

## Example Usage
Analyze all COBOL members and generate an enterprise execution inventory.

## Review Checklist
- PROGRAM-ID extracted?
- Calls identified?
- Dynamic calls identified (and flagged with confidence)?
- Complexity measured?
- Root programs identified?
- Risk scores generated?
