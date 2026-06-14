# Dataset Metadata Model

> Prompt 13 · Category: Metadata · Skills: [metadata-modeler](../../batch2/skills_framework/skills/metadata-modeler/skill.md), [security-compliance-analyst](../../batch2/skills_framework/skills/security-compliance-analyst/skill.md)
> Honors [MIP Engineering Principles](../../batch2/skills_framework/MIP_ENGINEERING_PRINCIPLES.md).

## Purpose
Represent enterprise datasets consistently.

## Context
Datasets connect jobs, programs, and business processes.

## Inputs
JCL Metadata · COBOL Metadata.

## Instructions
Model: Dataset · Dataset Type · Producers · Consumers · Retention · Ownership. Generate lineage-ready metadata. Carry the evidence envelope.

## Expected Output
- Dataset Entity
- Lineage Relationships
- Governance Metadata

## Constraints
Lineage-ready and governance-aware. Evidence envelope mandatory; sensitive/governed datasets flagged with confidence.

## Success Criteria
Data lineage can be reconstructed.

## Review Checklist
- Producers/consumers modeled?
- Governance metadata captured?
- Lineage relationships defined?
- Evidence envelope present?
