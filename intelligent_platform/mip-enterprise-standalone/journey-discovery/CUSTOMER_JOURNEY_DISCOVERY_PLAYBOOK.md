# Customer Journey Discovery Playbook
### For a non-COBOL analyst with a MIP database, the codebase, GitHub Copilot, and sparse SME input — no MCP required

This is a runbook. It takes you from *"I have all the technical facts in a database"* to
*"I have named, evidence-backed customer journeys an SME can confirm"* — without you reading COBOL.

**The core idea (read this once):**
> Code evidence anchors the **truth** (what runs). An ontology anchors the **meaning** (what the
> business calls it). Your docs/SME anchor it to **your org's words**. Copilot **maps** evidence →
> ontology. The SME **confirms**. Confidence = how much the three sources agree.

You don't read procedure logic — you read the **human-readable surface** (transaction codes, screen
labels, table names, business-rule statements, comments), which is exactly what the scripts pull out.

---

## The flow (six steps, all file-based — no MCP)

```
 DB ──(export_evidence.py)──► evidence packs ─┐
 docs/PPTs ──(prompt 01)──► glossary ─(check_freshness.py)─► relevant/obsolete ─┐
                                                                                 ├─►(prompt 02)► capability proposals
 LLM holds the ontology (BIAN/APQC) ────────────────────────────────────────────┘        │
                                                                                          (prompt 03)
 entity lifecycles ──────────────────────────────────────────────────────────────────────┴─► customer journeys
                                                                                                   │
                                                                                            SME confirms → final map
```

### Step 0 — Make sure the facts are in the DB
```powershell
python -m mip_intel.cli --db data\estate.db analyze "F:\path\to\source"
python -m mip_intel.cli --db data\estate.db validate
```

### Step 1 — Export evidence packs (DB → files Copilot can read)
```powershell
python journey-discovery\export_evidence.py --db data\estate.db --out journey-discovery\evidence
```
Produces, per **entry point** (every `TRANSACTION` and `JOB`): its screens, the program trace
(`STARTS_PROGRAM`/`EXECUTES`/`CALLS`…), tables read/written, and business rules — plus per
**entity** (`TABLE`/`FILE`) who writes vs reads it (the lifecycle), and a `glossary_seed.json`.
*This is your journey skeleton, straight from the graph — already reliable.*

### Step 2 — Mine the org vocabulary from the documents (Copilot)
In VS Code, attach your docs/PPTs/notes folder and run **`prompts/01-mine-glossary.prompt.md`**.
It writes `journey-discovery/glossary.json` — the capability/domain/journey terms your business
actually uses, and the assets each one names.

### Step 3 — Sort the docs automatically (relevant vs obsolete)
```powershell
python journey-discovery\check_freshness.py --db data\estate.db --glossary journey-discovery\glossary.json
```
Each glossary term is marked **relevant** (its programs still exist), **stale**, or **obsolete**
(its programs are gone). You keep the business's words but trust only what the code confirms — this
is how #5 (mixed relevant/obsolete docs) sorts itself.

### Step 4 — Map each evidence pack to a capability (Copilot + ontology)
Run **`prompts/02-map-capability.prompt.md`** on each pack. Copilot classifies it against the
industry ontology it already knows (**BIAN** for cards/banking, **APQC** otherwise), prefers your
*relevant* glossary words, cites every signal, scores confidence by agreement, and lists any
code↔doc **conflicts**. Output: `journey-discovery/proposals/<entry_point>.json`.

### Step 5 — Assemble end-to-end journeys (Copilot)
Run **`prompts/03-assemble-journey.prompt.md`**. It chains the proposals into journeys using the two
spines — **entry points** (the doors) and **entity lifecycles** (the business object's story) —
linked by screen flow, scheduler order, and data hand-offs. Output: a journey JSON + a plain-English
narrative + an explicit **"For SME review:"** question list per journey.

### Step 6 — SME confirms (the only path to "confirmed")
Walk the SME through each journey's review questions. They judge *business meaning only* — name,
step order, conflicts — never COBOL. Record the verdict. A journey is trustworthy only once a human
agrees **and** (later) its rules are behavior-tested (see the requirements/Java specs).

---

## Why this finally works for capability/domain naming
- The graph already gives the **structure** (entry → trace → data → rules) reliably.
- The thing that was missing was **naming**, and that is *inference* — so it's done by an ontology
  the LLM already holds, grounded in your evidence, in your org's words, confirmed by an SME.
- MIP's built-in `capability_naming.py` only had a **card-specific** pattern list (`CARD_PATTERNS`),
  which is why clusters came back "Needs Review." This playbook replaces that with
  ontology + glossary + evidence + SME — and Deliverable 3 (`CAPABILITY_ONTOLOGY_SPEC.md`) bakes the
  same idea back into the tool.

## The confidence ladder (so you trust the map correctly)
| Agreement | Status |
|---|---|
| code + ontology + relevant-glossary + SME-confirmed | `confirmed` |
| code + ontology + relevant-glossary | `inferred` (~0.8) |
| code + ontology only | `inferred` (~0.6) |
| code only / no clean match | `needs_review` (~0.4) — undocumented capability, ask SME |
| doc only, no live code | `obsolete` — excluded from the live map |

## Honesty rules (keep the map trustworthy)
- Every proposed name and journey step **cites a real screen/table/program/rule**. No citation → drop it.
- Unresolved/dynamic items stay visible in `open_questions` — never dropped to look clean.
- Nothing is `confirmed` until the SME agrees. The LLM proposes; the SME decides.
- A code↔doc conflict is recorded as a finding, not silently resolved.

## What you're building toward
These journeys are the entry point to the rest of MIP's modernization chain:
`ENRICHMENT_SPEC` (deeper facts) → `REQUIREMENTS_PIPELINE_SPEC` (confirmed BR/FR per journey step) →
`JAVA_IMPLEMENTATION_SPEC` (rebuild + prove equivalent). A confirmed journey becomes the scope unit
for everything after it.
