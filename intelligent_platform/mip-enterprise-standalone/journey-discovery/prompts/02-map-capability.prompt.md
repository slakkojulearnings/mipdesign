---
mode: agent
description: Map one code-evidence pack to a domain / sub-domain / capability (ontology + glossary, cited)
---

# Step 2 — Propose a capability, anchored to an ontology, grounded in evidence

You are a mainframe modernization analyst. For the attached **evidence pack**
(`journey-discovery/evidence/entry_points/<X>.json`), propose what business capability it
represents — by triangulating **three sources** against one reference frame.

## The three sources
1. **Code evidence (ground truth)** — the attached evidence pack: entry point, screens,
   programs, tables read/written, business rules. This is what actually runs.
2. **Reference ontology (the standard vocabulary)** — classify against the industry capability
   model you know best for this estate:
   - Banking / cards → **BIAN** service domains (e.g. *Card Lifecycle Management, Card
     Authorization, Payment Execution, Customer Billing*).
   - Insurance → **ACORD**; Telecom → **eTOM**; otherwise → **APQC Process Classification
     Framework**.
   Use it to produce a **hierarchy**: `domain → sub_domain → capability`.
3. **Org vocabulary (their words)** — `journey-discovery/glossary_freshness.json`. Prefer a
   `relevant` term's wording over the standard label when they mean the same thing. Treat
   `obsolete` terms as evidence of past intent only.

## Read the human-readable signals (no COBOL knowledge needed)
Weight these, in order: transaction code & **screen field labels** → **table/column names** →
program-id naming convention → business-rule statements → comments. These name the business
far better than procedure logic.

## Output — one JSON object
```json
{
  "entry_point": "...",
  "domain": "...", "sub_domain": "...", "capability": "...",
  "capability_label_source": "ontology | glossary:<term> | blended",
  "journey_step": "the customer/operator action this performs, in plain words",
  "confidence": 0.0,
  "validation_status": "inferred",
  "evidence": [ {"signal": "screen field PAN/EXPIRY/ACTIVATE", "supports": "capability=Card Activation"} ],
  "ontology_match": {"framework": "BIAN", "node": "Card Lifecycle Management"},
  "glossary_match": {"term": "Card Onboarding", "status": "relevant"},
  "conflicts": ["code writes CARD_MASTER but the 2019 deck assigns this to 'Account Setup'"],
  "needs_sme": true
}
```

## Rules (the honesty contract)
- **Cite every claim** to a specific signal in the evidence pack. No citation → drop the claim.
- Set `confidence` by **agreement**: code+ontology+relevant-glossary ≈ 0.8; code+ontology only
  ≈ 0.6; code only / no clean match ≈ 0.4 and `needs_sme: true`.
- Never output `validation_status: confirmed` — only an SME does that (Step 4).
- Surface every code↔doc disagreement in `conflicts`. Mismatch is a finding, not an error.
- If the pack is mostly `needs_review`/unresolved, say so and lower confidence.

Write the result to `journey-discovery/proposals/<entry_point>.json`. Repeat per evidence pack.
