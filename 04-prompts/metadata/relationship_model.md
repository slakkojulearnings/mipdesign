# Relationship Metadata Model

> Prompt 15 · Category: Metadata · Skill: [metadata-modeler](../../03-skills/metadata-modeler/SKILL.md)
> Honors [MIP Engineering Principles](../../03-skills/MIP_ENGINEERING_PRINCIPLES.md).

## Purpose
Create canonical relationship taxonomy.

## Context
Relationships power the knowledge graph. The relationship is often more important than the node.

## Inputs
All metadata entities.

## Instructions
Design relationship types.
**Core Types:** CALLS · EXECUTES · USES · READS · WRITES · CONTAINS · DEPENDS_ON · PRODUCES · CONSUMES (extend with IMPLEMENTS · SUPPORTS · OWNS · DERIVES_FROM · TRIGGERS for higher-order layers).

**Generate:** Taxonomy · Cardinality Rules · Validation Rules. Every relationship instance carries the evidence envelope (source_evidence, discovery_method, confidence, validation_status, discovered_at).

## Expected Output
- Relationship Catalog
- Schema Definition
- Graph Mapping

## Constraints
Canonical, consistent taxonomy. Evidence envelope mandatory on every relationship instance.

## Success Criteria
Every dependency can be represented consistently.

## Review Checklist
- Core relationship types defined?
- Cardinality and validation rules defined?
- Graph mapping defined?
- Evidence envelope on every relationship?

---

## Part 3 — Metadata Completion Criteria
On completion, MIP can answer: what is a Program / Job / Dataset / Table; how are they related; how do they execute together; what depends on what. Only after metadata is complete should graph construction begin.
