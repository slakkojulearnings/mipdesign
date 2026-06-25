---
mode: agent
description: Chain capability proposals + entity lifecycles into end-to-end customer journeys (cited)
---

# Step 3 — Assemble the end-to-end customer journeys

You are a customer-journey analyst. Using the capability proposals
(`journey-discovery/proposals/*.json`) and the entity-lifecycle packs
(`journey-discovery/evidence/entities/*.json`), reconstruct the **customer journeys** — the
ordered sequences of business steps a customer or operator moves through.

## How to chain steps into a journey (two spines)
1. **Entry-point spine** — each proposal is one *step* (a transaction/screen the customer uses,
   or a job that runs on their behalf). Link steps that:
   - share a screen→screen flow (online), or
   - are connected by scheduler order (one JOB triggers another), or
   - **hand off data**: one step `WRITES` an entity that the next step `READS`
     (use the entity packs' `written_by` / `read_by` to find the handoff).
2. **Entity-lifecycle spine** — for each core business entity (e.g. CARD_MASTER, ACCOUNT,
   STATEMENT), order the steps by its lifecycle: created → updated → read → closed. This is the
   business object's own story and usually reveals the journey backbone.

Cross the two: *a journey is a path through business entities, entered via touchpoints.*

## Output — one JSON per journey, plus a short narrative
```json
{
  "journey": "Activate my new card",
  "domain": "Cards & Payments", "capability": "Card Lifecycle Management",
  "actor": "cardholder",
  "trigger": "TRANSACTION CARDACT (screen CARDACT)",
  "steps": [
    {"seq": 1, "step": "Validate card details", "entry_point": "CARDACT",
     "programs": ["CRDACT01","CRDVAL"], "data": ["CARD_MASTER (read)"],
     "rules": ["expiry must be valid"], "citations": ["CRDACT01:CALLS CRDVAL"], "confidence": 0.8},
    {"seq": 2, "step": "Set card active", "entry_point": "CARDACT",
     "data": ["CARD_MASTER.status (write)"], "confidence": 0.8}
  ],
  "data_handoffs": ["writes CARD_MASTER -> read by BILLGEN (Billing journey)"],
  "downstream_journeys": ["First transaction", "Statement & billing"],
  "confidence": 0.7,
  "validation_status": "inferred",
  "open_questions": ["Is the dynamic call WS-RATE-PGM part of this journey? unresolved — ask SME"]
}
```

Then write a 3–5 sentence **plain-English narrative** of the journey for a non-technical reader.

## Rules
- Every step cites a real program / screen / table / rule from the evidence. No invented steps.
- Keep unresolved/`needs_review` items visible in `open_questions` — never drop them to look clean.
- `confidence` reflects the weakest link in the chain; `validation_status` stays `inferred` until
  an SME confirms the journey name and sequence.
- End each journey with **"For SME review:"** listing the exact yes/no questions a business expert
  must confirm (journey name, step order, any conflict from the proposals).
