# MIP Project Charter

## Problem

Large legacy estates contain critical business logic, data semantics, batch orchestration, and operational knowledge that are difficult to understand and risky to change.

## Vision

Create a continuously improving enterprise knowledge system that discovers, explains, validates, and supports modernization of legacy applications.

## Goals

- Build a complete, evidence-backed inventory.
- Identify execution roots and dependency chains.
- Extract canonical metadata and business rules.
- Build queryable lineage and knowledge graphs.
- Support impact analysis and modernization decisions.
- Preserve behavior during migration through automated equivalence testing.

## Non-Goals for the Initial Release

- Blind whole-estate conversion.
- Production deployment without human approval.
- Replacing domain experts.
- Treating LLM output as source truth.
- Building distributed infrastructure before local scale is measured.

## Users

- Mainframe engineers
- Java and cloud engineers
- Application owners
- Architects
- Test engineers
- Modernization program leaders

## Success Metrics

- Inventory coverage
- Parser precision and recall
- Percentage of relationships with evidence
- Percentage of artifacts documented
- Time to answer impact questions
- Behavioral equivalence coverage
- Reduction in unknown dependencies

## Delivery Principle

Prove reliable understanding first. Modernize only what is understood and testable.
