# MIP App — UX Showcase (Apple-style)

How the app looks and the **desired output** on each screen, using the bundled
card-processing estate (`source_mf_code/`). The design language is Apple-inspired:
light `#f5f5f7` canvas, white cards with soft shadows, SF system typography, pill
controls, restrained Apple-blue accent, generous spacing.

> These are layout mockups of the real screens; run the app (`app/README.md`) to use them.

---

## Shell

```
┌────────────┬──────────────────────────────────────────────────────────────┐
│ MIP        │                                          [ ↻ Rescan source ]  │
│ Mainframe… │                                                              │
│            │   <page content>                                             │
│ Dashboard  │                                                              │
│ Programs   │                                                              │
│ Capabilit… │                                                              │
│ Jobs       │                                                              │
│ Call Graph │                                                              │
│ Root Progs │                                                              │
│ Dead Code  │                                                              │
│ Query      │                                                              │
│ Q&A Log    │                                                              │
│            │                                                              │
│ source     │                                                              │
│ …/source_… │                                                              │
└────────────┴──────────────────────────────────────────────────────────────┘
```
Translucent sidebar (blurred), active item is an Apple-blue pill.

## Dashboard
```
Discovery Dashboard
Evidence-based inventory of the scanned mainframe estate.

┌ 20 ┐ ┌ 10 ┐ ┌ 4 ┐ ┌ 24 ┐ ┌ 4 ┐ ┌ 1 ┐ ┌ 1 ┐
 Artifacts Programs Jobs  Rel'ns Roots Dead  Needs-review
                                   (green)(red) (amber)

┌────────────── most depended-on ─┐ ┌ needs-review (dynamic) ┐ ┌ dead-code ┐
│ CRDVAL  ×1 callers               │ │ 0 edge(s)              │ │ 1         │
└──────────────────────────────────┘ └────────────────────────┘ └───────────┘
```
Each tile is a white rounded card with a colored top accent.

## Programs
```
Programs · 10 discovered. Click a row for dependencies, callers, and source.
┌──────────┬──────┬─────┬────────┬───────────┬────────────┐
│ Program  │ Lang │ LOC │ Calls→ │ ←Called by│ Flags      │
├──────────┼──────┼─────┼────────┼───────────┼────────────┤
│ CRDPOST  │ cobol│ 15  │ 2      │ 0         │ ◍ root     │
│ DEADPROG │ cobol│ 12  │ 0      │ 0         │ ◍ dead     │
│ PAYUPD   │ cobol│ 16  │ 0      │ 1         │            │
└──────────┴──────┴─────┴────────┴───────────┴────────────┘
```

## Program detail — `INTDRV` (everything in one place)
```
← Programs
INTDRV   [ Interest ]

┌ Complexity 1 ┐ ┌ Fan-out 3 ┐ ┌ Fan-in 1 ┐ ┌ Run by jobs 1 ┐

Profile
  Capability  Interest      Run by jobs   INTCALC
  Calls       INTCOMP   INTRATE1 ⚠        (INTRATE1 = inferred, resolved dynamic call)
  Copybooks   ACCTREC

Structure / AST
  1  cyclomatic (proxy)        1 paragraph · 3 divisions
  ▸ IDENTIFICATION DIVISION
  ▸ DATA DIVISION
  ▸ PROCEDURE DIVISION
     └ 0000-MAIN

Impact / blast radius      [ Analyze ]   NetworkX — what breaks if this changes
  score 2 · impacted 2 · depends-on 2 · via needs-review 0
  Impacted:  INTCALC ·1   (job that runs it)

Field-level data lineage   [ Trace ]     grammar parser — MOVE + SQL host-var ↔ column
  (INTDRV has no SQL/MOVE field flows; see STMTDRV/PAYUPD below)

Source  [ View ]  COBOL/INTDRV
```

### Field lineage — `STMTDRV` (read) and `PAYUPD` (write)
```
STMTDRV
  CARD_MASTER.CARD_NUMBER      → CARD-NUMBER    [sql-read]   COBOL/STMTDRV:12
  CARD_MASTER.CURRENT_BALANCE  → CARD-BALANCE   [sql-read]   COBOL/STMTDRV:12
PAYUPD
  PAY-CARD-NUMBER → PAYMENT.CARD_NUMBER   [sql-write]  COBOL/PAYUPD:11
  PAY-AMOUNT      → PAYMENT.PAY_AMOUNT     [sql-write]  COBOL/PAYUPD:11
```

## Capabilities
```
Business Capabilities

Structural communities — Louvain     3 domains · modularity 0.448
┌ Card / Statement  (community 0) ┐ ┌ Interest / Balance (1) ┐ ┌ Payment / Update (2) ┐
│ CRDPOST CRDVAL DEADPROG          │ │ BALUPD INTCOMP INTDRV  │ │ PAYDRV PAYUPD        │
│ STMTDRV STMTFMT                  │ │ WS-RATE-PGM            │ │                      │
└──────────────────────────────────┘ └────────────────────────┘ └──────────────────────┘

Capability map (root-driven)
┌ Card Posting [inferred·0.5] ┐  entry: CRDPOST · DAILYCRD
│ CRDPOST — Card Posting       │  Data: CARD_MASTER   Shared: CARDREC ACCTREC
│ CRDVAL  — Card Validation    │
│ BALUPD  — Balance Update     │
└──────────────────────────────┘   … Payment · Statement · Interest …
```

## Call & Execution Graph (two-pane, click for detail)
```
┌ Nodes/Edges 15/10 ┐ ┌ Roots 4 ┐ ┌ Dead 1 ┐ ┌ Dynamic 0 ┐ ┌ Most depended-on CRDVAL ×1 ┐

 ● Job   ● Root   ● Program   ● Dead   – – dynamic
┌──────────────── graph ─────────────────┐ ┌──── detail (on click) ─────┐
│ DAILYCRD → CRDPOST → CRDVAL             │ │ CRDPOST                    │
│                    ↘ BALUPD             │ │ program · root · community 0│
│ PAYPROC  → PAYDRV  → PAYUPD             │ │ Capability: Card Posting    │
│ INTCALC  → INTDRV  → INTCOMP            │ │ Calls: CRDVAL BALUPD        │
│                    ⇢ INTRATE1 (resolved)│ │ Structure: 0000-MAIN …      │
└─────────────────────────────────────────┘ └─────────────────────────────┘
Click a node → full profile + AST. Click an edge → its evidence + confidence.
```

## Query Console (answer + reasoning + full profile)
```
Query Console
[ which jobs execute CRDPOST                          ] ( Ask )
 chips: which jobs execute CRDPOST · what does PAYUPD write · tell me everything about INTDRV …

Answer (jobs_executing)
  • DAILYCRD

Why — reasoning trace  (logged to question_log.md)
  Thought process
   1. Routed to intent "jobs_executing".
   2. Identified program token: CRDPOST.
   3. Looked up job_step rows whose EXEC PGM= names it (EXECUTES edges).
  Evidence
   DAILYCRD EXECUTES CRDPOST — JCL/DAILYCRD:5 (confirmed, conf 1.0)
  Reason  CRDPOST is named in EXEC PGM= of 1 job step; confirmed EXECUTES edge.

Complete profile — CRDPOST  [ Card Posting ]
  … capability, run-by-jobs, calls/uses/reads/writes, callers, AST …
```

## Q&A Log
```
Q&A Log · every question recorded to question_log.md with reasoning + evidence (newest first).
[ ↻ Refresh ]  [ View raw question_log.md ]

┌ which jobs execute CRDPOST              2026-06-14T… ┐
│ [jobs_executing]  program: CRDPOST                   │
│ Thought process · Evidence · Reason  (full trace)    │
└──────────────────────────────────────────────────────┘
```

---

### The through-line
Every screen shows **evidence + confidence**, and anything inferred (a resolved dynamic
call, a Louvain community, a capability label) is badged so it's never mistaken for
fact. That honesty — surfaced cleanly in an Apple-calm UI — is the product.
