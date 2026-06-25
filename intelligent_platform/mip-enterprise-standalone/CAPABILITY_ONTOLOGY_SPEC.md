# Capability & Journey Naming Spec — ontology-anchored, evidence-grounded, SME-confirmed (build target)

> Target tree: `mip-enterprise-standalone`. Replaces the hardcoded card-only `CARD_PATTERNS` in
> `capability_naming.py` with a domain-agnostic engine: **ontology + org glossary + code evidence,
> with confidence = how much the three agree, confirmed only by an SME.** Bakes the
> `journey-discovery/` playbook back into the product. Same buildable style as `ENRICHMENT_SPEC.md`.
> Status: **NOT implemented.** Date: 2026-06-25.

## ⚠️ Governing principle
Naming a capability is **inference, not extraction.** So: the code evidence is ground truth; the
ontology supplies the standard vocabulary; the glossary supplies the org's words; an LLM may propose;
**only an SME sets `confirmed`.** `confidence` is the *agreement* across sources — never a fixed
guess.

## 0. The problem this fixes
`capability_naming.py` scores clusters against `CARD_PATTERNS` — a hand-written **card-only** tuple.
On any non-card estate, clusters fall back to *"Needs Review"* at ~0.25. The mechanism (score a
cluster's profile against patterns) is fine; the **patterns must come from a pluggable ontology +
the mined org glossary**, not a hardcoded card list.

## 1. The three sources (one reference frame)
- **Code evidence** — cluster/entry-point facts already in the graph (drivers, programs, tables
  read/written, screens, business rules). *What runs.*
- **Ontology** — an industry capability model (BIAN / APQC / ACORD / eTOM / custom) loaded as config;
  the LLM also holds these natively. *Standard `domain → sub_domain → capability` vocabulary.*
- **Org glossary** — terms mined from SME docs/PPTs (see `journey-discovery/prompts/01`), each
  freshness-checked against the DB (`relevant` / `stale` / `obsolete`). *The org's own words.*

## 2. Schema additions
```sql
CREATE TABLE IF NOT EXISTS capability_ontology (        -- pluggable; replaces hardcoded CARD_PATTERNS
    node_id      TEXT PRIMARY KEY,     -- stable_id(framework, domain, sub_domain, capability)
    framework    TEXT NOT NULL,        -- BIAN | APQC | ACORD | eTOM | custom
    domain       TEXT NOT NULL,
    sub_domain   TEXT,
    capability   TEXT NOT NULL,
    signals_json TEXT NOT NULL DEFAULT '{}',  -- {table_hints:[], tx_prefixes:[], field_hints:[], program_hints:[], rel_hints:[]}
    source       TEXT NOT NULL DEFAULT 'framework'       -- framework | glossary | merged
);

CREATE TABLE IF NOT EXISTS glossary_term (              -- mined from docs, freshness-checked
    term_id        TEXT PRIMARY KEY,
    term           TEXT NOT NULL,
    kind           TEXT NOT NULL,       -- domain | sub_domain | capability | journey
    definition     TEXT,
    named_assets_json TEXT NOT NULL DEFAULT '[]',
    source_doc     TEXT,
    freshness      REAL NOT NULL DEFAULT 0,
    status         TEXT NOT NULL        -- relevant | stale | obsolete
);

CREATE TABLE IF NOT EXISTS capability_proposal (
    proposal_id    TEXT PRIMARY KEY,    -- stable_id(run_id, subject_kind, subject_id)
    run_id         TEXT NOT NULL REFERENCES run_manifest(run_id) ON DELETE CASCADE,
    subject_kind   TEXT NOT NULL,       -- cluster | entry_point
    subject_id     TEXT NOT NULL,
    domain         TEXT, sub_domain TEXT, capability TEXT,
    label_source   TEXT NOT NULL,       -- ontology | glossary:<term> | blended | llm
    ontology_node  TEXT, glossary_term TEXT,
    confidence     REAL NOT NULL,
    validation_status TEXT NOT NULL,    -- inferred | needs_review | confirmed
    citations_json TEXT NOT NULL DEFAULT '[]',
    conflicts_json TEXT NOT NULL DEFAULT '[]',
    created_at     TEXT NOT NULL, updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS journey (
    journey_id     TEXT PRIMARY KEY,
    run_id         TEXT NOT NULL REFERENCES run_manifest(run_id) ON DELETE CASCADE,
    name           TEXT NOT NULL, domain TEXT, capability TEXT, actor TEXT, trigger TEXT,
    steps_json     TEXT NOT NULL DEFAULT '[]',     -- ordered steps, each with citations
    confidence     REAL NOT NULL,
    validation_status TEXT NOT NULL,
    citations_json TEXT NOT NULL DEFAULT '[]',
    open_questions_json TEXT NOT NULL DEFAULT '[]',
    created_at     TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS capability_review (         -- SME verdict (modeled on requirement_review)
    review_id    TEXT PRIMARY KEY,
    subject_id   TEXT NOT NULL,         -- proposal_id | journey_id
    subject_kind TEXT NOT NULL,         -- capability | journey
    verdict      TEXT NOT NULL,         -- accepted | renamed | rejected
    final_name   TEXT, reviewer TEXT NOT NULL, reason TEXT NOT NULL DEFAULT '',
    reviewed_at  TEXT NOT NULL
);
```

## 3. The naming engine (replaces `CARD_PATTERNS` scoring)
Keep `capability_naming.py`'s profile-scoring **mechanism**; change where the patterns come from and
how confidence is set.
```
for each cluster / entry-point:
  e = evidence_match(cluster_profile, capability_ontology.signals)   # best ontology node
  g = glossary_match(cluster_profile, glossary_term WHERE status='relevant')
  if max(e.score, g.score) < THRESHOLD and llm_enabled:
      p = grounded_llm_propose(evidence_pack, ontology, glossary)    # cite-or-downgrade (llm_insights pattern)
  label = blend(e, g, p)                                             # prefer relevant-glossary wording
  confidence = agreement(e, g, p)                                    # see §4
  conflicts = where code-derived owner != glossary owner
  write capability_proposal(domain, sub_domain, capability, label_source, confidence,
                            validation_status='inferred'|'needs_review', citations, conflicts)
```
- **Offline default:** no LLM endpoint ⇒ ontology+glossary scoring only; a no-match stays
  `needs_review` — never fabricated.
- LLM output with no citation ⇒ `needs_review`, confidence ≤ 0.4 (same guard as `llm_insights`).

## 4. Confidence = agreement (the trust ladder)
| Sources agreeing | confidence | status |
|---|---|---|
| code + ontology + relevant glossary + **SME** | — | `confirmed` |
| code + ontology + relevant glossary | ~0.8 | `inferred` |
| code + ontology only | ~0.6 | `inferred` |
| code only / no clean match | ~0.4 | `needs_review` (undocumented capability) |
| glossary/doc only, no live code | — | excluded (`obsolete`) |

## 5. SME confirmation gate
Only a `capability_review` (`accepted`/`renamed`) flips a proposal or journey to `confirmed` and sets
its `final_name`; `rejected` is retained (audit) and excluded from the published map. Mirrors
`requirement_review`. **No auto-promotion to `confirmed`.**

## 6. Journeys
`journey` rows are assembled from confirmed/inferred proposals chained by the two spines (entry-point
flow + entity-lifecycle data hand-offs), exactly as `journey-discovery/prompts/03`. Each step carries
citations; `open_questions` keeps unresolved/dynamic items visible.

## 7. CLI / API surface
```
mip --db DB ontology-load   --framework BIAN [--file ontology.json]     # seed/merge the ontology
mip --db DB glossary-load   --file glossary.json                        # load + freshness-check docs glossary
mip --db DB capabilities    [--limit N]                                 # propose (ontology+glossary+evidence)
mip --db DB capabilities-review <proposal_id> --verdict accepted|renamed|rejected --reviewer NAME [--name "..."]
mip --db DB journeys        [--limit N]                                 # assemble journeys
mip --db DB journeys-export [--format md|json]                          # the customer-journey map
```
API: `GET /capabilities`, `POST /capabilities/{id}/review`, `GET /journeys`, `GET /journeys/export`,
`POST /ontology/load`, `POST /glossary/load` — same `IntelligenceApi` facade.

## 8. Coverage & honesty
- `journeys-export` and a coverage rollup report: % of clusters/entry-points with a `confirmed`
  capability, the `needs_review` (undocumented) list, the `obsolete` glossary terms, and every
  recorded code↔doc `conflict`. Prove coverage; don't claim it.
- Replace `domain_architecture.py`'s use of the card name with the `capability_proposal` label, so
  service candidates inherit the ontology-anchored, SME-confirmable name + confidence.

## 9. Test gate
| Test | Asserts |
|---|---|
| No hardcoded ontology | scoring reads `capability_ontology`; `CARD_PATTERNS` removed or demoted to a sample config |
| Non-card estate names | a non-card cluster gets a real domain→sub_domain→capability (not "Needs Review") when ontology+glossary match |
| Agreement confidence | confidence rises with source agreement; code-only stays `needs_review` |
| Glossary freshness | an `obsolete` term never names a live capability; a `relevant` term's wording wins |
| Conflict surfaced | code↔doc disagreement is persisted in `conflicts_json`, not silently resolved |
| LLM guard | uncited LLM proposal ⇒ `needs_review`, ≤0.4; offline ⇒ no LLM, no fabrication |
| Confirm gate | only a `capability_review` sets `confirmed`; reviewer recorded |
| Journey chaining | journeys chain via screen flow + data hand-offs; unresolved items kept in `open_questions` |
| Traceability | every proposal/journey step cites a real asset/relationship/evidence |

## 10. Out of scope
The ontology *content* itself (ship a small BIAN/APQC starter `ontology.json` + let the LLM expand
it) and the doc-mining step (that's `journey-discovery/prompts/01` — this spec only ingests its
output via `glossary-load`).
```
journey-discovery/ (do it now, by hand + Copilot)  ──►  CAPABILITY_ONTOLOGY_SPEC (bake it into MIP)
```
