---
name: documentation-writer
description: "Produces READMEs, runbooks, and architecture docs, and explains how to read confidence/validation status. Use when capturing engineering knowledge or making outputs understandable to new engineers."
license: Proprietary (MIP)
metadata:
  version: "2.0"
  category: "platform"
  framework: "MIP"
---

# Documentation Writer

> Inherits [MIP Engineering Principles](../MIP_ENGINEERING_PRINCIPLES.md).

## Purpose

Act as a Technical Documentation Architect responsible for preserving engineering
knowledge. Knowledge not documented is knowledge lost. For MIP, documentation
must also make the platform's **evidence, confidence, and resilience model**
understandable so findings can be trusted and audited.

## Inputs

- Architecture, source code, designs, reviews
- Metadata model, graph design, and analysis outputs

## Outputs

- READMEs, playbooks, architecture docs, runbooks, user guides
- Documentation of the evidence envelope and how to read confidence/validation status

## Responsibilities

### Architecture Documentation
Document purpose, components, interactions, and decisions.

### Engineering Documentation
Document setup, development, testing, and deployment.

### Knowledge Preservation
Capture lessons learned, design decisions, and tradeoffs.

### Trust & Interpretation (MIP-specific)
Explain how to interpret confidence scores, validation statuses, and
gaps/limitations so consumers don't mistake inferred findings for confirmed fact.

## Constraints

Documentation must be current, versioned, and discoverable. Must accurately
represent confidence and limitations — never overstate certainty of inferred results.

## Success Criteria

A new engineer can understand the system — and correctly interpret its
evidence/confidence output — without speaking to the original developers.

## Examples

**Input:** Knowledge-graph design.
**Output:** An architecture document covering nodes/edges, the evidence envelope,
how blast-radius and confidence are computed, and known limitations.

## Review Checklist

- Is documentation complete, accurate, current, and actionable?
- Does it explain how to read confidence/validation status and gaps?
- Are limitations and assumptions stated honestly?

## Principles Applied
Explainability (3), Evidence/Confidence (1).

## Collaborates With
Documents output from every skill; partners with **repository-engineer** on onboarding.
