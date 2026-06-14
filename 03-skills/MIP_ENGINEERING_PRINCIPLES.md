# MIP Engineering Principles (Shared Skill Foundation)

Version: 1.0
Status: Canonical — referenced by every MIP skill

Every MIP skill inherits these principles. They exist so that Copilot behaves
consistently across the entire platform and so the system is **resilient,
explainable, and capable of understanding the complete enterprise** — not just
isolated programs.

A skill must never contradict these principles. Where a skill is silent, these
principles apply.

---

## 1. Evidence-First, Confidence-Aware

Every finding, relationship, and recommendation must be backed by observable
evidence and must carry a confidence signal. We do **not** silently refuse when
evidence is partial — we degrade gracefully and make uncertainty visible.

Every fact / edge / recommendation should carry:

- **Source Evidence** — file + location (line/paragraph/statement) the finding came from
- **Discovery Method** — how it was derived (static parse, AST, data-flow, semantic, runtime, inference)
- **Confidence Score** — High / Medium / Low (or 0.0–1.0)
- **Validation Status** — Confirmed / Inferred / Needs Review
- **Timestamp** — when it was discovered

> Replaces the old absolutist rule "Never assume. Never infer."
> We **may** infer — but inference must be labeled, scored, and flagged for review.
> We never present inference as confirmed fact.

## 2. Resilience by Design (Graceful Degradation)

The platform must keep producing useful, honest output when the input is
imperfect. Every skill must tolerate:

- Missing or incomplete metadata
- Incomplete / partial repositories
- Dynamic calls and late binding
- Undocumented interfaces
- Legacy / inconsistent naming conventions
- Partial source availability

When inputs are incomplete: produce the best evidence-based result, mark the
gaps explicitly (a "Missing Information" / "Gaps & Assumptions" section), lower
confidence accordingly, and never fabricate to fill a hole.

## 3. Explainability & Auditability

Every recommendation must be explainable and every inference auditable. A
reviewer must be able to trace any conclusion back to its source evidence and
discovery method. No black-box assertions.

## 4. System Thinking

Artifacts are analyzed as an interconnected system, never as isolated programs.
Relationships are first-class — the relationship is often more important than the
node. Always consider upstream/downstream reach, blast radius, and operational
context.

## 5. Graph-Ready Output

All discovered assets and relationships must be representable as nodes and edges
suitable for the MIP knowledge graph. Prefer canonical entity/relationship names
(see metadata-modeler) so downstream graph, lineage, and impact-analysis layers
can consume the output without rework.

## 6. Business-Context Awareness

Connect technical assets to business capabilities, domains, and criticality
wherever evidence allows. Modernization aligns with business outcomes, not
technical boundaries.

## 7. Layered Intelligence

No single technique is sufficient. The strongest understanding combines:
AST + Control-Flow + Data-Flow + Knowledge Graph + Graph Algorithms +
Semantic Intelligence + Runtime Evidence + LLM Reasoning. Skills should produce
output that feeds the next layer rather than treating their step as the end.

## 8. Scope Discipline

Each skill stays within its charter (see each skill's Constraints). Skills
collaborate through well-defined inputs/outputs rather than duplicating one
another's responsibilities.

---

### Standard Skill Format

Every skill document uses these sections:

`Purpose` · `Inputs` · `Outputs` · `Responsibilities` · `Constraints` ·
`Success Criteria` · `Examples` · `Review Checklist`

Plus, where relevant: `Principles Applied` (which of the 8 above are most load-bearing),
and `Collaborates With` (sibling skills it hands off to).
