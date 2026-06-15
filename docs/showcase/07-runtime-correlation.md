# 7. Runtime Evidence Correlation

**Business value.** Reading the code tells you what *can* happen; production logs tell
you what *actually* happens. MIP combines the two. It reconciles the static map against
real runtime data (how often each program ran, when, for how long) to confirm dead code,
catch hidden dynamic calls, and rank true business-criticality by real usage — not just
code structure. This is where guesswork is replaced by operational fact.

## What MIP does

MIP loads runtime metrics (here from SMF batch records + the CICS monitor for May 2026)
and correlates them with the static model. It produces three things:

1. **Reconciliation** — where static and runtime evidence agree or disagree.
2. **Per-entity metrics** — execution frequency, last run, average elapsed time.
3. **Runtime-weighted criticality** — combining structural centrality with real usage.

## Real sample output

**Reconciliation** (`/api/runtime`, window `2026-05`):

```json
"confirmed-dead": [
  { "program": "DEADPROG", "exec_count": 0, "confidence": 0.85, "validation_status": "inferred",
    "reason": "Statically unreachable AND not executed in 2026-05. Static + runtime evidence agree — dead-code confidence raised." }
],
"static-miss": [
  { "program": "INTRATE1", "exec_count": 480000, "known_as_dynamic_target": true,
    "confidence": 0.9, "validation_status": "needs_review",
    "reason": "Ran 480000 time(s) ... appears only as an unresolved/dynamic CALL target; runtime CONFIRMS the dynamic call actually fires." }
]
```

**Runtime-weighted criticality** (top of the ranked list):

```json
[
  { "program": "AUTHVAL",  "exec_count": 4820500, "pagerank": 0.0697, "runtime_criticality": 0.8596 },
  { "program": "AUTHTRAN", "exec_count": 4820500, "pagerank": 0.0377, "runtime_criticality": 0.6945 },
  { "program": "STMTFMT",  "exec_count": 215000,  "pagerank": 0.0969, "runtime_criticality": 0.5223 },
  { "program": "PAYUPD",   "exec_count": 18400,   "pagerank": 0.0969, "runtime_criticality": 0.5019 }
]
```

## What this means

- **`DEADPROG` is now confirmed dead** — static analysis *and* zero runtime executions
  agree, so MIP raises its dead-code confidence to 0.85. Still flagged for review, but
  now with two independent lines of evidence behind a decommission decision.
- **`INTRATE1` was a hidden dynamic call** — invisible to many static tools, but it ran
  **480,000 times**. MIP had already kept it as an *inferred* edge (see
  [02-parsing-and-ast.md](02-parsing-and-ast.md)); runtime **confirms the dynamic call
  really fires** and flags the gap as `needs_review`. Nothing slipped through.
- **True criticality is usage-aware.** Pure code structure ranked statement-formatting
  highest; once real volume is folded in, the **online authorization path
  (`AUTHVAL`, `AUTHTRAN`) rises to the top** — 4.8 million executions/month make it the
  most business-critical code to protect. That is the kind of insight only the
  static + runtime combination can give.
