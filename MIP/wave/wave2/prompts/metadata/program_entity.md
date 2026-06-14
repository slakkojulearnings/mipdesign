# Program Metadata Model

> Prompt 11 · Category: Metadata · Skill: [metadata-modeler](../../batch2/skills_framework/skills/metadata-modeler/skill.md)
> Honors [MIP Engineering Principles](../../batch2/skills_framework/MIP_ENGINEERING_PRINCIPLES.md).

## Metadata Design Principles
Evidence Based (every element references source evidence) · Canonical (one representation regardless of source language) · Traceable (every entity traceable to source artifacts) · Graph Ready · Modernization Ready.

## Purpose
Design the canonical Program entity used throughout MIP.

## Context
Programs are primary execution units. The Program entity becomes the most connected node in the platform.

## Inputs
COBOL Metadata.

## Instructions
Design a canonical Program entity. Include:
- **Identity:** Program Name · Program Type · Source Location
- **Dependencies:** Called Programs · Copybooks · Tables · Files
- **Execution:** Entry Points · Batch Usage · Online Usage
- **Metrics:** Lines of Code · Complexity · Dependency Count
- **Evidence Envelope** (per [principles](../../batch2/skills_framework/MIP_ENGINEERING_PRINCIPLES.md)): source_evidence · discovery_method · confidence · validation_status · discovered_at

**Generate:** Pydantic Model · SQLite Mapping · Graph Mapping.

## Expected Output
- Program Entity Specification
- Validation Rules
- Versioning Strategy

## Constraints
Must support millions of relationships. Must carry the evidence envelope on the entity and each relationship.

## Success Criteria
Program entity supports graph and modernization use cases.

## Review Checklist
- Identity, dependencies, execution, metrics modeled?
- Evidence envelope present?
- Pydantic / SQLite / Graph mappings generated?
- Versioning defined?
