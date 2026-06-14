# Dead Code and Orphan Asset Detection

> Prompt 24 · Category: Graph · Skill: [graph-engineer](../../03-skills/graph-engineer/SKILL.md)
> Honors [MIP Engineering Principles](../../03-skills/MIP_ENGINEERING_PRINCIPLES.md).

## Purpose
Identify unused, unreachable, and orphaned assets.

## Inputs
Call Graph · Batch Graph · Root Program Catalog · Runtime Evidence.

## Instructions
**Detect:** Unreachable Programs · Unused Copybooks · Orphan Tables · Orphan Datasets · Dormant Transactions.
Assign confidence scores.

## Expected Output
- Dead Code Inventory
- Orphan Asset Catalog
- Retirement Candidates

## Constraints
Reachability is computed from roots; absence of runtime evidence lowers confidence (an asset may be rarely-but-legitimately used). Never recommend retirement on low confidence without flagging for review.

## Success Criteria
Unused assets become visible and measurable.

---

## Part 4 — Graph Completion Criteria
On completion, MIP can answer: which program calls this program; which programs are impacted; which jobs execute this program; which datasets flow through the system; which tables are affected; what are the root programs; which business capability owns this program; which applications support this capability; what business processes are impacted by a change; which applications exist; which assets are dead code / modernization candidates / business critical; which dependencies create operational risk; which interfaces are undocumented; which applications should be decomposed first; what is the execution architecture; what is the blast radius of a change; which assets can be retired; which services can be extracted; which APIs can be generated; which domains exist.

At enterprise scale the strongest approach is not Graph vs AST — it is **AST + Control Flow + Data Flow + Knowledge Graph + Graph Algorithms + Semantic Intelligence + Runtime Evidence + LLM Reasoning.**
