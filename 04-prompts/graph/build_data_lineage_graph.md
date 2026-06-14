# Data Lineage Graph

> Prompt 18 · Category: Graph · Skills: [graph-engineer](../../03-skills/graph-engineer/SKILL.md), [security-compliance-analyst](../../03-skills/security-compliance-analyst/SKILL.md)
> Honors [MIP Engineering Principles](../../03-skills/MIP_ENGINEERING_PRINCIPLES.md).

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
