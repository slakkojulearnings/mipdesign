---
name: diagram-generator
description: Generates Mermaid architecture, call, lineage, and batch workflow diagrams from validated catalog and relationship indexes. Use when visualizing repository structure, daily processing, program calls, data flow, or impact paths.
license: Apache-2.0
compatibility: Works with skills-aware coding agents; repository workflows assume Python 3.12+, Git, and local file access.
metadata:
  author: mip-project
  version: "1.0"
---


# Diagram Generator

## Workflow

1. Identify the diagram question and scope.
2. Query indexes/graph for the relevant subgraph.
3. Choose a diagram type:
   - flowchart for execution/data flow
   - sequence diagram for interactions
   - class diagram for data structures
   - state diagram for lifecycle
4. Preserve direction and relationship labels.
5. Group nodes by job, domain, artifact type, or stage only when evidence supports it.
6. Include unresolved nodes with a visible style.
7. Validate Mermaid syntax.
8. Save source `.md` under `knowledge/diagrams/`.

## Constraints

- Do not generate a diagram from memory when index data exists.
- Keep large diagrams split into overview and detail views.
- Never imply runtime order from a call graph alone.

## Operating Rules

- Follow `CLAUDE.md`.
- Preserve source evidence and confidence.
- Do not modify `mfcode/`.
- Keep generated material under `knowledge/` or `output/`.
- Use the work ledger before processing repository artifacts.
- Report unresolved references and unknowns explicitly.
