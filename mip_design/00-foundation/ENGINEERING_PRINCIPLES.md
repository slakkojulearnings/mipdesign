# MIP Engineering Principles

> The eight principles every skill, prompt, parser, and query in MIP must honor.
> The canonical copy that the skills inherit lives at
> [`../03-skills/MIP_ENGINEERING_PRINCIPLES.md`](../03-skills/MIP_ENGINEERING_PRINCIPLES.md);
> this file is the narrative reference with rationale.

These exist so that behavior is **consistent** across the platform and the system is
**reliable, resilient, and able to understand the complete enterprise** — not just
isolated programs.

---

## 1. Evidence-First, Confidence-Aware

Every fact, relationship, and recommendation is backed by observable evidence and
carries a confidence signal. We do **not** silently refuse when evidence is partial —
we degrade gracefully and make uncertainty visible.

**The evidence envelope** (on every entity and edge):

| Field | Meaning |
|-------|---------|
| `source_evidence` | file + location (line / paragraph / statement) |
| `discovery_method` | static parse · AST · data-flow · semantic · runtime · inference |
| `confidence` | High / Medium / Low (or 0.0–1.0) |
| `validation_status` | Confirmed · Inferred · Needs Review |
| `discovered_at` | timestamp |

> This replaces the old absolutist rule *"Never assume. Never infer."* We **may**
> infer — but inference must be labeled, scored, and flagged. We never present
> inference as confirmed fact.

## 2. Resilience by Design (Graceful Degradation)

The platform keeps producing useful, honest output on imperfect input. It must
tolerate: missing/incomplete metadata, partial repositories, dynamic calls, late
binding, undocumented interfaces, legacy naming, partial source. On incomplete input:
produce the best evidence-based result, record the gap explicitly, lower confidence,
never fabricate.

## 3. Explainability & Auditability

Every recommendation is explainable; every inference is auditable. A reviewer can
trace any conclusion to its source evidence and discovery method. No black boxes.

## 4. System Thinking

Artifacts are analyzed as an interconnected system. Relationships are first-class —
the relationship is often more important than the node. Always consider
upstream/downstream reach and blast radius.

## 5. Graph-Ready Output

All assets and relationships are representable as nodes/edges for the knowledge graph,
using canonical names (see [`../01-metadata-model`](../01-metadata-model)) so downstream
layers consume output without rework.

## 6. Business-Context Awareness

Connect technical assets to business capabilities, domains, and criticality wherever
evidence allows. Modernization aligns with business outcomes, not technical boundaries.

## 7. Layered Intelligence

No single technique suffices. The strongest understanding combines AST + Control-Flow
+ Data-Flow + Knowledge Graph + Graph Algorithms + Semantic Intelligence + Runtime
Evidence + LLM Reasoning. Each skill produces output that feeds the next layer.

## 8. Scope Discipline

Each skill stays within its charter and collaborates through defined inputs/outputs
rather than duplicating others.

---

### How these are enforced
- **Metadata model** ([`../01-metadata-model`](../01-metadata-model)) makes the
  evidence envelope a required part of every entity and relationship.
- **Skills** ([`../03-skills`](../03-skills)) each declare which principles are
  load-bearing and which sibling skills they hand off to.
- **Prompts** ([`../04-prompts`](../04-prompts)) bake the confidence/resilience
  contract into their Constraints sections.
- **Tests** (reference implementation) assert that inferred/dynamic findings are
  emitted as `Needs Review`, never `Confirmed`.
