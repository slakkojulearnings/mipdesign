# Data Lineage Graph

> Prompt 18 · Category: Graph · Skills: [graph-engineer](../../batch2/skills_framework/skills/graph-engineer/skill.md), [security-compliance-analyst](../../batch2/skills_framework/skills/security-compliance-analyst/skill.md)
> Honors [MIP Engineering Principles](../../batch2/skills_framework/MIP_ENGINEERING_PRINCIPLES.md).

## Purpose
Construct enterprise data lineage.

## Context
Data lineage is required for modernization, governance, compliance, and auditability.

## Inputs
Dataset Metadata · DB2 Metadata · Program Metadata · AST Metadata · Data Flow Metadata.

## Instructions
**Model:** Producers · Consumers · Transformations.
**Track:** Source Data · Intermediate Data · Target Data.
Use AST and Data Flow Graph evidence.
**Support:** Dataset-Level Lineage · Table-Level Lineage · Field-Level Lineage.

## Expected Output
- Lineage Model
- Lineage Traversals
- Impact Analysis Paths
- Field-Level Lineage
- Transformation Chains

## Constraints
Evidence-based; confidence-scored. Field-level lineage feeds sensitive-data exposure analysis.

## Success Criteria
End-to-end lineage becomes traceable.
