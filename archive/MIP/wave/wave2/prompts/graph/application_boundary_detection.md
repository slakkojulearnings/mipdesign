# Application Boundary Detection

> Prompt 22 · Category: Graph · Skill: [business-capability-analyst](../../batch2/skills_framework/skills/business-capability-analyst/skill.md)
> Honors [MIP Engineering Principles](../../batch2/skills_framework/MIP_ENGINEERING_PRINCIPLES.md).

## Purpose
Automatically discover logical applications and domains.

## Context
Many enterprises do not have accurate application inventories.

## Inputs
Knowledge Graph · Call Graph · Batch Graph · Data Lineage Graph.

## Instructions
**Apply:** Community Detection · SCC Analysis · Dependency Clustering · Semantic Clustering.
**Identify:** Applications · Domains · Shared Services · Integration Hubs.
Generate confidence scores.

## Expected Output
- Application Catalog
- Domain Catalog
- Dependency Clusters
- Shared Service Inventory
- Application Confidence Scores

## Constraints
Evidence-based clustering; every boundary carries confidence; low-confidence boundaries flagged.

## Success Criteria
Logical application boundaries become visible.
