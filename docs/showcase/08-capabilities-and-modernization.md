# 8. Business Capabilities & Evidence-Based Modernization

**Business value.** Leadership thinks in business capabilities — *Authorization,
Payments, Statements* — not in program names. MIP groups the technical assets into
inferred business capabilities, then uses its evidence (blast radius + criticality) to
recommend a **safe, incremental** modernization order: extract the lowest-risk pieces
first, leave the dangerous ones for later. No big-bang rewrite.

## What MIP does

Starting from each root program and its confirmed call-closure, MIP infers a business
capability, names it from naming conventions, and lists its programs, jobs, data tables
and shared structures. Capabilities are explicitly **inferred** (confidence 0.5, review
recommended) — a starting map for the business to validate, not a final org chart.

## Real sample output

**Inferred capabilities (`/api/capabilities`)** — 5 found:

```json
[
  { "capability": "Authorization", "root": "AUTHTRAN", "confidence": 0.5, "validation_status": "inferred",
    "programs": ["AUTHTRAN","AUTHVAL"], "tables": ["AUTHLOG","CARDFILE"], "jobs": [],
    "reason": "Inferred from root driver AUTHTRAN and its confirmed call-closure; capability name derived from naming conventions — review recommended." },
  { "capability": "Card Posting", "root": "CRDPOST", "confidence": 0.5, "validation_status": "inferred",
    "programs": ["BALUPD","CRDPOST","CRDVAL"], "tables": ["CARD_MASTER"], "jobs": ["DAILYCRD"] },
  { "capability": "Interest",  "root": "INTDRV",  "programs": ["INTCOMP","INTDRV"],  "jobs": ["INTCALC"] },
  { "capability": "Payment",   "root": "PAYDRV",  "programs": ["PAYDRV","PAYUPD"],   "jobs": ["PAYPROC"], "tables": ["ACCT_MASTER","PAYMENT"] },
  { "capability": "Statement", "root": "STMTDRV", "programs": ["STMTDRV","STMTFMT"], "jobs": ["STMTGEN"], "tables": ["CARD_MASTER"] }
]
```

(Each entry above carries `"confidence": 0.5, "validation_status": "inferred"` and the
same "review recommended" reason.)

## How this drives an evidence-based modernization plan

MIP doesn't just describe the estate — it sequences the work, each step justified by
captured evidence from the other documents:

1. **Start with the lowest blast radius.** `CRDVAL` impacts only `CRDPOST` and the
   `DAILYCRD` job (blast-radius score **2.0**, all confirmed) — a small, well-bounded,
   low-risk first extraction. Contrast the `CARD_MASTER` table at score **5.0**: shared
   across Card Posting and Statement, so it moves late and carefully.
2. **Protect the busiest path.** The runtime-weighted ranking puts **Authorization
   (`AUTHVAL`/`AUTHTRAN`, 4.8M runs/month)** at the top — modernize it with the most
   testing and the least disruption, not first.
3. **Decommission what's truly dead.** `DEADPROG` is confirmed dead by static + runtime
   evidence — remove it from scope entirely (see [07](07-runtime-correlation.md)).
4. **Use capabilities as candidate service boundaries.** The 5 capabilities map cleanly
   onto the 3 detected communities ([03](03-knowledge-graph.md)) — a defensible
   first cut at microservice / domain boundaries, to be confirmed with the business.

## What this means

- Leadership gets a **capability-level view** of a code estate, with the data and jobs
  each capability owns.
- The modernization order is **driven by evidence** — blast radius and real usage — so
  the riskiest changes are deliberately sequenced last.
- Because capabilities are honestly **inferred (0.5)**, they are presented as a draft for
  business validation, keeping MIP's core promise: never present inference as fact.
