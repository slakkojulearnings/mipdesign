# Resilience and Operational Risk Discovery

> Prompt 05C · Category: Discovery · Skill: [resilience-engineer](../../batch2/skills_framework/skills/resilience-engineer/skill.md)
> Honors [MIP Engineering Principles](../../batch2/skills_framework/MIP_ENGINEERING_PRINCIPLES.md).

## Purpose
Identify operational resilience characteristics and systemic risks.

## Context
Modern enterprises require resilient architectures. This is the discovery prompt most directly aligned with MIP's goal of building a resilient system that understands the complete system.

## Inputs
Programs · JCL · Datasets · Database Dependencies · Operational Assets.

## Instructions
**Identify:** Single Points of Failure · Critical Dependencies · Recovery Dependencies · Restart Mechanisms · Operational Bottlenecks · Legacy Risks · Unsupported Components.

**Assess:** Availability Risks · Recovery Risks · Scalability Risks · Security Risks.

**Generate:** Resilience Score · Risk Heat Map · Recovery Readiness Assessment.

## Expected Output
- Resilience Assessment
- Risk Heat Map
- Recovery Dependency Analysis
- Recommendations

## Constraints
All findings evidence-based with confidence. Where operational/runtime evidence is missing, infer from static/graph evidence, lower confidence, and flag for review — never fabricate recovery behavior.

## Success Criteria
Operational resilience posture is measurable and explainable.

## Review Checklist
- Single points of failure identified with evidence?
- Recovery paths and restart dependencies mapped?
- Resilience Score explainable and confidence-scored?
- Findings honest under partial operational data?

---

## Part 1 — Discovery Completion Criteria
On completion of the Discovery prompts, MIP can answer: what exists; where; how many artifacts; which programs execute; which jobs orchestrate; which copybooks define data; which DB2 tables are used; what are the root programs; what are the critical business capabilities; what are the operational dependencies, resilience risks, modernization candidates, recovery paths, single points of failure; which assets are business-critical and cloud-migration candidates.

Only after these are answered should parsing, metadata, graph, and modernization intelligence begin.
