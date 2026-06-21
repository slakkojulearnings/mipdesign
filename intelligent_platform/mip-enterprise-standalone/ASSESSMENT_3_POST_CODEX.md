# MIP Enterprise Intelligence — Assessment #3 (post-Codex phases 1–6)

> Date: 2026-06-21. Method: direct code inspection of the current `mip-enterprise-intelligence`
> tree + an empirical timed scan of real BankDemo COBOL (12 programs + copybooks). Companion
> to `CODE_REVIEW_ASSESSMENT.md` (#1) and `ASSESSMENT_2_PERF_DATA_COMPLETENESS.md` (#2).

## Verdict in one line

Codex fixed **essentially every correctness/robustness finding** from #1 and #2 — this is a
large, real quality leap — **but the core performance/scale problem is still unsolved, and
the new deep-extraction features made scale *worse*.** One targeted change (proven 1,170×
below) would fix the speed problem.

## What got fixed (verified — code + empirical)

| Finding (from #1/#2) | Status | Evidence |
|---|---|---|
| `INSERT OR REPLACE` cascade-deletes edges | ✅ fixed | `ON CONFLICT DO UPDATE` for asset/relationship (repositories.py:235,277) |
| Target-only assets have no evidence → `validate` fails | ✅ fixed | `asset_evidence` map (ingestion.py:827-851); empirical: **validate=passed, 0 of 17,578 assets without evidence** |
| Double-extraction (edges emitted twice, laundered to confirmed/1.0) | ✅ fixed | regex pass gated `if "CALLS" not in parser_rel_types` (ingestion.py:2347); empirical: **0 duplicate CALLS edges** |
| No WAL / busy_timeout | ✅ fixed | repositories.py:81-83 |
| N+1 in recompute_summaries | ✅ fixed | `GROUP BY` (graph_service.py:676-685) |
| No hard parse timeout | ✅ added | process-based hard timeout (ingestion.py:1568-1576) |
| Threads don't parallelize | ✅ addressed | `ProcessPoolExecutor` (ingestion.py:709) |
| field_flows discarded | ✅ fixed | real `FLOWS_TO` edges + `data_lineage` attr (ingestion.py:2474) |
| No control flow | ✅ added | `PERFORMS`/`BRANCHES_TO`/`CONTAINS_PARAGRAPH` (`_control_flow_relationships`) |
| Shallow data items | ✅ added | REDEFINES/OCCURS/88-level/usage/value |
| Parsed data not in UI | ✅ addressed | new Control/Data graph filters + `QualityView`/scorecards (main.jsx) |
| No precision/recall harness | ✅ added | `scorecards.py` (expected vs forbidden members/nodes/edges) |

Remaining minor: `review_items_are_visible` still hardcoded `passed=True` (api.py:138);
34 duplicate `DECLARES_COPYBOOK_FIELD` edge-groups (a small dedup gap in copybook expansion).

## What is NOT fixed — the core problem (empirical)

Timed scan, 12 real BankDemo programs + copybooks, config `{max_workers:4,
parse_timeout_seconds:15}`:

```
ANTLR-first scan (current code):   328.2s,  all 12 programs TIMED OUT -> parse-error,
                                   0 calls / 0 field_flows from the programs themselves.
cobol_ast (fast hand parser) ONLY: 0.28s for the same 12 files, 21 field_flows captured.
                                   => ~1,170x faster AND more program data.
```

### Root cause (proven)
`parse_cobol` still tries the pure-Python ANTLR ProLeap grammar **first** (~57–112s/file on
real COBOL) and only falls back to the fast `cobol_ast` parser **after** ANTLR fails. So:
- With a hard timeout (15s), the timeout kills the slow ANTLR attempt **before** the fast
  fallback can run → every program becomes `parse-error` → **fast but empty**.
- Without a timeout, each program takes 57–112s → a 200K-file estate ≈ **months** →
  **complete but unusably slow**.

The hard timeout makes scans *complete* instead of hanging (good), but it does not make them
*useful*: you get nothing from the programs. The fix Codex applied treats the symptom.

### The fix (one change, 1,170× proven)
**Reorder the parser: run `cobol_ast` FIRST for the bulk scan** (0.023s/file, captures
calls/field_flows/CICS/copybook) and invoke the ANTLR full grammar **only on-demand** for a
single program's deep AST. This is exactly recommendation #2 from Assessment #2, now proven
empirically. Alternatively, replace the pure-Python ANTLR runtime with a compiled parser
(ProLeap is Java — run as a sidecar) — the *runtime* is the bottleneck, not the grammar.

## New problem introduced — graph explosion at the field level

The scan produced **17,578 assets and 19,106 `DECLARES_COPYBOOK_FIELD` edges for just 12
programs.** Field-level nodes (one asset per copybook field per program, plus `FLOWS_TO`
field nodes) are unbounded: at estate scale this is **billions of field assets**, directly
contradicting the platform's own "bounded graph / don't materialize the full graph" design
and the honest-scale principle. Recommendations:
- Bound copybook-field expansion (don't create a FIELD asset per field per including program;
  model the copybook layout once and reference it), and/or make field-level lineage an
  opt-in/on-demand depth rather than a default of every bulk scan.
- Report the field-node count in scan stats so the explosion is visible, not silent.

## Structural / process notes

- **Defaults are wrong for safety**: `parse_timeout_seconds=0` (no timeout) and
  `max_workers=1` (ingestion.py:107-109). A naive `mip analyze <estate>` therefore runs
  serial with no timeout — i.e. the months-long path. Make a bounded, parallel, fast config
  the default.
- **Scope explosion**: +4,902 uncommitted lines on top of the phases-1-5 commit;
  `ingestion.py` is now ~5,000 lines (was ~2,000). It is a god-module and should be split
  along its existing seams before it grows further.
- **Three near-duplicate copies** now exist outside the app: `mip-enterprise-standalone`,
  `-deep-parser`, `-phase1-6`. Pick ONE canonical tree; divergent copies will rot and
  contradict each other. Decide what's a build artifact vs. source of truth.

## Bottom line

The correctness and feature work is genuinely strong — the trust-breakers are gone, `validate`
passes honestly, lineage/control-flow/data semantics are captured, and there's a real
precision/recall harness. Ship-blocker now is singular and clear: **the bulk scan must stop
parsing with pure-Python ANTLR first.** Reorder to hand-parser-first (proven 1,170×) and bound
field-level node creation, and the platform finally matches its "very large estate" framing.
