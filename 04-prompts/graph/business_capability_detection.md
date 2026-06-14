# Business Capability Detection

> Prompt 21 · Category: Graph · Skill: [business-capability-analyst](../../03-skills/business-capability-analyst/SKILL.md)
> Honors [MIP Engineering Principles](../../03-skills/MIP_ENGINEERING_PRINCIPLES.md).

## Purpose
Identify and map business capabilities implemented by the application portfolio.

## Context
Modernization programs are increasingly organized around business capabilities rather than technical components.

## Inputs
Program Metadata · Job Metadata · Dataset Metadata · DB2 Metadata · Transaction Metadata · Application Metadata · Knowledge Graph · Semantic Embeddings.

## Instructions
Identify logical business capabilities by analyzing: Program naming patterns · Transaction names · Dataset usage · Table usage · Batch processing flows · Online transaction flows · Shared business entities · Existing documentation · Semantic similarity.

Group related assets into capabilities. Generate capability hierarchies where appropriate. Create relationships:
- **Nodes:** Capability · Application · Program · Job · Dataset · Table
- **Edges:** IMPLEMENTS · SUPPORTS · USES · OWNS · DEPENDS_ON

Generate confidence scores.

## Expected Output
- Business Capability Catalog
- Capability-to-Application Mapping
- Capability Dependency Graph
- Capability Confidence Scores
- Business Domain Groupings

## Constraints
All capability assignments must include supporting evidence. Low-confidence assignments must be flagged for review.

## Success Criteria
- Technical assets can be traced to business capabilities.
- Applications can be grouped by business function.
- Modernization planning can be organized around business outcomes.
