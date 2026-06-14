# Root Program Discovery

> Prompt 05A · Category: Discovery · Skills: [mainframe-code-analyst](../../batch2/skills_framework/skills/mainframe-code-analyst/skill.md), [graph-engineer](../../batch2/skills_framework/skills/graph-engineer/skill.md)
> Honors [MIP Engineering Principles](../../batch2/skills_framework/MIP_ENGINEERING_PRINCIPLES.md).

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
