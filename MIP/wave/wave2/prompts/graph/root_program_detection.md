# Root Program Detection

> Prompt 20 · Category: Graph · Skill: [graph-engineer](../../batch2/skills_framework/skills/graph-engineer/skill.md)
> Honors [MIP Engineering Principles](../../batch2/skills_framework/MIP_ENGINEERING_PRINCIPLES.md).

## Purpose
Identify true entry points.

## Context
Many organizations do not know which programs are actual roots.

## Inputs
Call Graph · Batch Graph · Transaction Metadata · Scheduler Metadata · CICS Metadata · MQ Metadata · IMS Metadata · Runtime Evidence.

## Instructions
**Identify:** Batch Drivers · Online Drivers · Scheduler Entry Points · Utility Entry Points · CICS Transaction Entry Points · MQ Trigger Entry Points · IMS Transaction Entry Points · External Interface Entry Points · API Entry Points.

Classify roots by type.
**Determine:** Root Program · Invocation Method · Execution Frequency · Downstream Reach · Criticality Score · Business Importance.

Rank roots by business importance and execution impact.

## Expected Output
- Root Program Catalog
- Entry Point Graph
- Dependency Rankings
- Critical Root Programs
- Execution Reach Analysis
- Business Criticality Rankings

## Constraints
Evidence-based; confidence-scored; low-confidence roots flagged.

## Success Criteria
- Execution entry points become visible.
- All executable paths can be traced back to one or more root programs.
- Business-critical roots are identified and prioritized.
