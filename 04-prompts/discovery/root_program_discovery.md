# Root Program Discovery

> Prompt 05A · Category: Discovery · Skills: [mainframe-code-analyst](../../03-skills/mainframe-code-analyst/SKILL.md), [graph-engineer](../../03-skills/graph-engineer/SKILL.md)
> Honors [MIP Engineering Principles](../../03-skills/MIP_ENGINEERING_PRINCIPLES.md).

## Purpose
Identify true enterprise entry points.

## Context
Many organizations do not know which programs actually initiate business processing.

## Inputs
Program Inventory · JCL Inventory · CICS Definitions · Scheduler Definitions.

## Instructions
**Identify:** Batch Drivers · Online Drivers · Scheduler Entry Points · Utility Entry Points · Service Entry Points.

**Generate:** Root Program Catalog · Entry Point Rankings · Dependency Reach Analysis.

## Expected Output
- Root Program Inventory
- Entry Point Analysis
- Dependency Reach Report

## Constraints
Evidence-based; rank by observable reach. Flag low-confidence roots for review.

## Success Criteria
All execution roots identified.

## Review Checklist
- Batch and online drivers identified?
- Entry points ranked by dependency reach?
- Low-confidence roots flagged?
