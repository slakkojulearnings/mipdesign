# Copybook Parser Architecture

> Prompt 08 · Category: Parsing · Skill: [mainframe-code-analyst](../../03-skills/mainframe-code-analyst/SKILL.md)
> Honors [MIP Engineering Principles](../../03-skills/MIP_ENGINEERING_PRINCIPLES.md).

## Purpose
Design parser architecture for enterprise copybooks.

## Context
Copybooks define shared data structures across thousands of programs. They often contain the most reusable business knowledge.

## Inputs
Copybook source files.

## Instructions
Support extraction of:
- **Structure Metadata:** Levels · Field Names · PIC Clauses
- **Complex Structures:** REDEFINES · OCCURS · OCCURS DEPENDING ON
- **Relationships:** Parent-Child Hierarchies · Reusable Structures

Generate parser architecture and metadata schema.

## Expected Output
- Parser Architecture
- Metadata Model
- Validation Strategy
- Complexity Scoring Model

## Constraints
No business interpretation. Fault-tolerant; complex/nested structures must degrade gracefully with recorded notes.

## Success Criteria
Complex enterprise copybooks represented consistently.

## Example Usage
Design parser architecture for 20,000 copybooks.

## Review Checklist
- PIC supported?
- OCCURS supported?
- REDEFINES supported?
- Nested structures supported?
