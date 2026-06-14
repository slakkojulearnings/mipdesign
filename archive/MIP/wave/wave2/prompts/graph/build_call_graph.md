# Call Graph Construction

> Prompt 16 · Category: Graph · Skill: [graph-engineer](../../batch2/skills_framework/skills/graph-engineer/skill.md)
> Honors [MIP Engineering Principles](../../batch2/skills_framework/MIP_ENGINEERING_PRINCIPLES.md).

## Purpose
Create a complete application call graph.

## Context
Program-to-program relationships reveal execution architecture.

## Inputs
Program Metadata · Relationship Metadata · AST Metadata · Runtime Evidence (optional).

## Instructions
Create graph.
- **Nodes:** Programs · Services · Transactions
- **Edges:** CALLS · INVOKES · EXECUTES
- **Capture:** Direct Calls · Recursive Calls · Circular Dependencies · Dynamic Calls · External Service Calls · MQ Invocations · CICS Transfers · IMS Calls

Use AST evidence wherever possible. Generate traversal strategies.
**Calculate:** Reachability · Centrality · Criticality.

## Expected Output
- Call Graph Design
- Node Model
- Edge Model
- Traversal Examples
- Critical Program Rankings
- Dependency Hotspots

## Constraints
Use evidence-based relationships only. Inferred/resolved dynamic calls carry confidence + `Needs Review`. The graph tolerates missing/partial input via confidence scoring.

## Success Criteria
Every program dependency represented.
