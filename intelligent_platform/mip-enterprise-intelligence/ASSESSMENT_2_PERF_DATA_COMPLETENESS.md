# MIP Enterprise Intelligence — Assessment #2

> Date: 2026-06-20. Focus: the three practical problems raised after all phases completed —
> (1) scan speed, (2) parsed-but-unused data, (3) COBOL completeness — plus product
> recommendations. Method: direct code inspection of the scan + parse + extraction +
> persistence + UI paths. Companion to `CODE_REVIEW_ASSESSMENT.md`.

---

## Problem 1 — Scans take hours. How to make it fast WITHOUT losing information.

### Why it's slow (root causes, in order of impact)

**A. The ANTLR COBOL-85 parse runs in pure Python with default LL prediction.**
`cobol_antlr.parse` (`cobol_antlr.py:60-72`) builds a fresh lexer+parser per file and calls
`parser.startRule()` with ANTLR's **default prediction mode (adaptive LL with full
context)**. On a large/ambiguous grammar like ProLeap COBOL-85, full-LL prediction in the
pure-Python runtime is the single biggest cost — often 80%+ of wall-clock. Evidence: the
34-test suite (trivial 4-line programs) takes ~185s.

**B. Every file is parsed up to THREE times over.** In `reference_parser.parse_cobol`
(`reference_parser.py:88-109`), per file we run:
1. `cobol_ast.parse(text)` — the hand-written parser (raw_unit), ALWAYS.
2. `antlr_adapter.preprocess(text)` — once here…
3. `cobol_antlr.parse(text)` — which calls `antlr_adapter.preprocess(text)` AGAIN internally
   (`cobol_antlr.py:60`), then the expensive ANTLR parse.
So: 2× preprocess + 1× hand-parse + 1× full ANTLR parse for every member. The hand parse is
mostly used only as a fallback for a couple of fields.

**C. ThreadPoolExecutor gives ~no speedup for CPU-bound parsing.** Workers are threads
(`ingestion.py:331-343`); pure-Python ANTLR work can't run concurrently under the GIL, so
`max_workers=32` overlaps only the brief SQLite I/O, not the parse.

**D. `recompute_summaries` is O(assets) point queries, run twice.** Two `COUNT(*)` per asset
in a Python loop (`graph_service.py:372-381`) — ~400K queries at 200K assets — and
`api.analyze` calls it a second time (`api.py:53`).

**E. No incremental scan.** `resume` only suppresses the delete (`repositories.py:104`); the
tree is always re-walked, every file re-read + re-SHA'd + re-classified, and the graph
rebuilt. Only ANTLR parsing is cached (by sha256). A re-scan of an unchanged 200K estate
still pays full discovery + classification + summary cost.

**F. No SQLite write tuning + per-file commits.** `connect()` sets only
`PRAGMA foreign_keys=ON` (`repositories.py:76-88`) — no WAL, no `synchronous=NORMAL`. Each
worker commits the parse cache + scan issues per file → 200K+ fsync cycles, plus writer
contention.

**G. Whole estate held in memory.** All `ClassifiedMember` text + line tuples stay resident
through parse → extract → persist (`ingestion.py:160-243`).

### Fixes (ranked by speedup-per-effort)

1. **Two-stage SLL parsing (biggest single win, ~1 hr work).** In `cobol_antlr.parse`:
   set `parser._interp.predictionMode = PredictionMode.SLL` and a `BailErrorStrategy`; if it
   throws, reset the token stream and retry once with `PredictionMode.LL`. Typically 3–10×
   on the parse itself, with identical output for the (vast majority of) inputs SLL accepts.
2. **Real multi-core via `ProcessPoolExecutor`.** `parse_cobol` is pure data-in/data-out, so
   it is process-safe. Fan parsing out to processes (warm ONE parser per worker process and
   reuse it across files to keep the SLL DFA cache hot). Have each process RETURN the payload
   and write the cache from the main process — this simultaneously fixes the
   "database is locked"/no-WAL concurrency risk. Combined with #1 → the headline speedup
   (≈ cores × SLL factor).
3. **Stop the redundant per-file work.** Preprocess once and pass the expanded text into the
   ANTLR parse (don't preprocess twice). Only run `cobol_ast.parse` when ANTLR fails or for
   the specific fallback fields you actually need — don't double-parse on the happy path.
4. **True incremental scan.** Before classify/parse, look up existing `source_member` by
   path; if `sha256` is unchanged, skip re-read/re-classify/re-parse/re-persist for that
   member. Makes re-scan cost proportional to *changed* files (turns hours into seconds on
   stable estates).
5. **`recompute_summaries` → 2 `GROUP BY` queries** instead of 400K, and call it once (drop
   the duplicate call in `api.analyze`).
6. **SQLite tuning:** `PRAGMA journal_mode=WAL; synchronous=NORMAL; busy_timeout=10000` at
   init; batch parse-cache/issue writes with `executemany`.
7. **Batch the pipeline** (the `batch_size` config already exists): classify → parse →
   persist a batch, then drop its text. Peak RAM becomes O(batch), not O(estate).

### Recommended architecture: a two-tier "fast inventory now, deep facts in the background"

To get *speed AND completeness*, split the scan into tiers so the UI is usable in minutes
while nothing is lost:
- **Tier 1 (fast, minutes):** inventory + classification + the cheap relationship facts
  (CALL/COPY/EXEC/JCL/SQL via the lighter pass). Persist + serve immediately.
- **Tier 2 (deep, background):** full ANTLR AST + field-level lineage + control flow,
  written incrementally so dashboards "fill in" and the parse cache makes the next run cheap.
This directly answers "data is fuel": you capture *everything*, just not all on the critical
path. Mark Tier-2-pending facts `needs_review` until the deep pass confirms them.

---

## Problem 2 — Parsed data isn't fully utilized / surfaced in the UI.

You're right. The extractor produces far more than the platform persists or shows.

### Confirmed: high-value data computed then DISCARDED

- **Field-level data lineage (`field_flows`).** `cobol_ast` computes every `MOVE A TO B` and
  EXEC SQL host-var↔column flow (its docstring calls this a headline capability). But
  `_asset_for_member` keeps only `field_flow_count` (`ingestion.py:1017`) — the flows are
  **never persisted as edges, never queryable, never surfaced**. This is the most valuable
  signal in the pipeline and it is thrown away. **Fix: persist as `FLOWS_TO`
  (field→field) and `MAPS_TO` (host-var↔column) relationships, and add a "Data lineage"
  view.** This alone is a major product upgrade.

### Confirmed: rich data persisted but NOT shown in the UI

Grepping `main.jsx` for the parsed fields, the only place any of this appears is one line
showing `complexity` + parser name (`main.jsx:648`). The following are stored (in asset/edge
attributes) but invisible to users:
- **DB2 structure** — `columns`, `primary_key`, index `unique`/`columns` on
  DEFINES_TABLE/INDEXES_TABLE edges (Phase-2). No table/column detail view.
- **`data_items`** (the data dictionary: level/name/PIC) — buried in `ast_tree`, only a
  *count* surfaced; no searchable field catalog, no "where is field X used".
- **`copy_resolution`** (which copybooks resolved vs missing) — stored, not shown; this is
  prime "review gap" UI.
- **`dialect_profile`** (CICS/DB2/multi-entry/format signals) — stored, not shown.
- **`copy_replacing`** pairs — stored, not shown.
- **VSAM `organization`/`record_key`/`access`** (Phase-2) on USES_DATASET — stored, not shown.

### Recommendation
Run a deliberate "extraction inventory → API → UI" audit: list every field the parser
emits, mark each as {persisted? queryable? surfaced?}, and close the gaps. Priorities:
(1) persist + visualize `field_flows` as lineage; (2) a Program detail panel that renders
ast_summary + copy_resolution + dialect_profile; (3) a Table/Data-dictionary view rendering
DB2 columns/PK/indexes and COBOL data_items; (4) surface VSAM file attributes on dataset edges.

---

## Problem 3 — What's still missing to capture COMPLETE COBOL information.

Current extraction (good for v0.1): program_id, divisions, paragraphs (as a flat list),
data_items (level/name/PIC), calls (static/dynamic/resolved), copies, SQL (op/table),
CICS edges, field_flows (computed, discarded), counts, complexity; JCL (EXEC PGM/PROC, DSN)
and CICS/CSD/scheduler via regex.

### The gaps that matter most for "complete understanding" and modernization

**1. Intra-program control flow (PERFORM / GO TO → paragraph/section).** Paragraphs are
captured as a *set*, with no edges. Without a PERFORMS/flow graph you can't find dead
paragraphs, extract the real execution order, or recover business logic. **High value.**

**2. CALL … USING parameter lists (the interface contract).** What data crosses each call
boundary is not captured — yet that is exactly what defines a service boundary. Pair with
**LINKAGE SECTION** on the callee side to reconstruct the contract. **High value for the
modernization layer.**

**3. Data-structure semantics.** REDEFINES (overlays), OCCURS (arrays/tables + DEPENDING ON),
**level-88 condition names** (business-rule flags), level-66 RENAMES, COMP/COMP-3 usage,
group→elementary hierarchy. Today only level+name+PIC, and only a count downstream.

**4. Copybook field expansion.** Copybooks are linked (USES_COPYBOOK) but the record layout /
fields they contribute to each program are not modeled — so cross-program data sharing via
shared copybooks is invisible.

**5. DB2 depth.** Cursors (DECLARE/OPEN/FETCH/CLOSE), WHERE/JOIN column-level lineage, full
host-variable binding, DCLGEN↔table linkage. (README already lists this as a gap.)

**6. CICS depth.** COMMAREA / CHANNEL / CONTAINER **data contracts** passed on LINK/XCTL/START;
TS/TD queues; HANDLE CONDITION; file control via CICS. Edges exist; the data passed does not.

**7. File I/O semantics.** FD record layout, OPEN modes (INPUT/OUTPUT/I-O/EXTEND), READ/WRITE/
REWRITE/DELETE/START with KEY, and exception handlers (AT END, INVALID KEY). VSAM SELECT/ASSIGN
is captured; the I/O verbs + record structure are shallow.

**8. Decision & transformation logic.** EVALUATE/IF structure and COMPUTE/arithmetic — the
actual business rules. Only an aggregate `complexity` number is kept; the logic is not
extracted (this is what `legacy-rewrite-engineer` ultimately needs).

**9. JCL depth.** STEP modeling, DD-name→dataset binding, PROC expansion + symbolic
substitution, GDG, COND / IF-THEN, RETURN-CODE flow. Today: regex EXEC PGM + DSN only — so
the batch data-flow graph is incomplete.

**10. Statement ordering / SECTIONs / SORT-MERGE.** Procedure order isn't modeled; SORT/MERGE
and their work files aren't tracked.

### Suggested sequencing (capability, not phase)
1. Persist `field_flows` (already computed) → instant lineage win.
2. PERFORM/GO-TO control-flow edges + CALL USING / LINKAGE contracts.
3. Data-structure semantics (88-levels, REDEFINES, OCCURS) + copybook field expansion.
4. DB2/CICS/File-I/O depth.
5. Structured JCL parser (replace regex) for the full batch graph.
6. Decision/transform extraction for business-rule recovery.

---

## Product-level recommendations (beyond the three problems)

- **Add a precision/recall harness** against a labeled estate (BankDemo is a good candidate).
  CLAUDE.md mandates ground-truth metrics; today phase tests assert presence on tiny fixtures.
  This is how you'll prove "complete information" claims honestly.
- **Fix the flagship correctness issues first** (see Assessment #1): missing evidence on
  target-only assets (breaks `validate`), double-extraction (inflates the graph), and the
  `INSERT OR REPLACE` cascade. These undermine trust in every downstream number.
- **Make "what we did NOT capture" a first-class output.** A coverage report per program
  (parser mode, unresolved copies, dynamic calls, Tier-2-pending) turns the honesty principle
  into a feature reviewers can act on.
- **Split `ingestion.py`** (~2,000 lines) along its existing function seams as deep parsing
  grows — classification / parse-orchestration / extraction / persistence.
