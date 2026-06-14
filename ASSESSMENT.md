# Assessment of the MIP Repo (3 parts)

> The three assessments produced while reviewing the original `mip_structure` repo,
> consolidated here. They are the *why* behind `mip_design/`: this folder keeps what
> went well and fixes what didn't.

---

## Assessment 1 — Skills registry & V2 prompt library (the wave2 review)

**What I reviewed:** the 9 wave2 skills, the strategy files, and the V2 prompt library
(Discovery + Knowledge-Graph parts in full).

**Core finding:** the **prompts had evolved to V2/V3** (resilience-oriented, multi-layer
intelligence, evidence + confidence) while the **skills were still V1** (thin, "facts
only"). The skills *under-powered* the prompts instead of underpinning them.

**The most important issue:** the skills' constraints said *"Never assume. Never
infer."* — which directly **contradicted** the V2 graph prompts, where the system must
*tolerate* missing metadata, partial source, and dynamic calls and apply **confidence
scoring** instead of refusing. Brittle absolutism vs. required graceful degradation.

**Gaps with no owning skill:** resilience/operational-risk, confidence scoring,
AST/CFG/DFG, graph algorithms, business-capability/boundary detection, sensitive-data /
PII / compliance, impact/blast-radius, dead-code.

**What was done (in wave2, now consolidated here):** added shared engineering
principles; rewrote all 9 skills to the confidence/resilience model; added 3 new skills
(resilience-engineer, security-compliance-analyst, business-capability-analyst); fixed
the "never infer" contradiction across the board. → see [`03-skills/`](03-skills/).

---

## Assessment 2 — The whole repo (strengths & six concerns)

**Strengths.** The core thesis — *understand before transform* — is correct and
differentiated. The layered pipeline (Inventory → Metadata → Graph → Reasoning →
Copilot → Modernization) is coherent and **internally consistent across ~50 documents**.
Maturity discipline ("don't jump to the Copilot layer") is rare and right. The wave3
metadata model + SQLite schema are genuinely implementation-ready.

**Six concerns.**
1. **Zero running code** — everything was `.md`/`.pdf`; the spine was never executed.
2. **The hard algorithms were asserted, not specified** (impact, lineage, confidence
   aggregation, clustering).
3. **The AST — central to the idea — was the least-specified artifact**; dynamic
   `CALL` resolution (which breaks call graphs) named but unsolved.
4. **Scale rhetoric outran the tooling** (NetworkX "10M edges").
5. **No ground-truth / validation** — "confidence" was itself unvalidated.
6. **The repo had a knowledge-sprawl problem** — skills/prompts in 4+ places — ironic
   for this product.

**How `mip_design/` answers each:** (1) a runnable, tested v0.1 spine
([`reference-implementation/`](reference-implementation/)); (2) concrete pseudocode
([`02-algorithms/`](02-algorithms/)); (3) explicit parser strategy + AST node shape +
dynamic-call handling ([`00-foundation/ARCHITECTURE.md`](00-foundation/ARCHITECTURE.md));
(4) an honest scale plan with a named trigger + target; (5) a ground-truth corpus with
precision/recall; (6) a single source of truth (this folder).

---

## Assessment 3 — The thought-process evolution

The idea grew in three stages — and grew *well*:

| Stage | The idea | Where it lives now |
|------:|----------|--------------------|
| **1 — Seed** | understand code → find the **root/driver** COBOL program (via JCL `EXEC PGM=`) | realized & tested in [`reference-implementation/`](reference-implementation/) (`mip roots`, "which jobs execute X") |
| **2 — Expansion** | from the driver, build **call graph + AST** and recover **related programs & business capabilities** | call/USES/READS/WRITES edges built today; AST + capability clustering specified in [`02-algorithms/`](02-algorithms/) & [`00-foundation/ARCHITECTURE.md`](00-foundation/ARCHITECTURE.md) |
| **3 — Ambition** | a more-intelligent platform for **any organization** (universal problem) | tech-agnostic model + per-tenant plan ([`00-foundation/ARCHITECTURE.md`](00-foundation/ARCHITECTURE.md)); skills & prompt library ([`03-skills/`](03-skills/), [`04-prompts/`](04-prompts/)) |

**One-line verdict:** *the thinking evolved in exactly the right direction and is
remarkably consistent — but execution lagged the vision by a full stage at every step.*

**What went well:** the founding instinct never wavered; the root-driver entry vector
was the right thread to pull; maturity discipline held; the V2 prompt library is
measurable; the metadata model/schema were implementation-ready.

**What to improve:** build before expanding scope; specify the hard algorithms; pin the
AST/parser; be honest about scale; add ground truth; kill the duplication.

**The fix, applied:** `mip_design/` lets *build catch up to design*. The spine now runs
and is measured, so every later layer (graph algorithms, real AST, lineage, capability
clustering, LLM Q&A) is **incremental on a proven base** rather than speculative.
