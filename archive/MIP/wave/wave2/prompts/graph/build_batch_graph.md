# Batch Execution Graph

> Prompt 17 · Category: Graph · Skills: [graph-engineer](../../batch2/skills_framework/skills/graph-engineer/skill.md), [resilience-engineer](../../batch2/skills_framework/skills/resilience-engineer/skill.md)
> Honors [MIP Engineering Principles](../../batch2/skills_framework/MIP_ENGINEERING_PRINCIPLES.md).

## Purpose
Model batch execution architecture.

## Context
JCL jobs orchestrate business processing.

## Inputs
Job Metadata · Program Metadata · Dataset Metadata · Scheduler Metadata · Control Card Metadata.

## Instructions
Create graph.
- **Nodes:** Jobs · Steps · Programs · Datasets · Schedules · Utilities
- **Edges:** EXECUTES · READS · WRITES · TRIGGERS · DEPENDS_ON · PRODUCES · CONSUMES

Generate execution paths.
**Identify:** Critical Chains · Failure Points · Restart Dependencies.

## Expected Output
- Batch Graph Architecture
- Execution Traversals
- Dependency Views
- Critical Batch Chains
- Operational Risk Analysis

## Constraints
Evidence-based; confidence-scored. Failure points and restart dependencies feed the resilience-engineer.

## Success Criteria
Batch execution chains become visible.
