# Parser Architecture Review — MIP Enterprise (standalone)

> Strict review of the proposed parser architecture. Target tree: `mip-enterprise-standalone`
> (the sole canonical tree). Grounded in this tree's code + measured on real BankDemo COBOL.
> Date: 2026-06-22.

## Proposed architecture (what's being reviewed)
- `cobol_ast` is the **fast baseline** parser for **all** files.
- ANTLR4 is a **persistent deep-enrichment** parser (not UI-only) whose results **write back to
  SQLite** and improve the knowledge graph.
- Estates may have **200K+ extensionless files**.

## Current state (verified 2026-06-22 — none of this is implemented yet)
- **Still ANTLR-first**: `reference_parser.parse_cobol` runs `cobol_ast`, then tries ANTLR and
  returns `local-antlr4-full-grammar` on success; `cobol_ast` is only the fallback
  (`reference_parser.py:94-116`). ANTLR is on the synchronous critical path.
- **No enrichment tier**: `schema.sql` has no `enrichment`/`origin`/`supersede` constructs;
  `parser_result_cache` is a cache, not a re-runnable ledger. No `mip enrich` command.
- ANTLR facts are merged inline into the shared `asset`/`relationship` tables, tagged with a
  `parser_effective` attribute.

## Measured facts that drive every decision below
- `cobol_ast` (baseline): **0.28s / 3 files**, captures field_flows.
- ANTLR (full grammar): **96.8s / 3 files, and only 1 of 3 programs parsed** — the ProLeap grammar
  fails on the other two. ⇒ **ANTLR is ~340× slower AND partial-by-default** (it will fail on the
  majority of real COBOL). Both facts are non-negotiable design inputs.

---

## 1. Is the parser split correct?
**Yes — with two non-negotiable invariants.**
1. **Baseline is authoritative and self-complete.** Inventory, full graph, roots/clusters, and the
   service-candidate read-models must be 100% usable with enrichment OFF. Enrichment adds depth; it
   is never a dependency. Today ANTLR is on the critical path — invert it.
2. **Enrichment is additive by supersession, not duplication.** An ANTLR fact must *replace* the
   baseline fact of the same identity `(type, src, tgt)` (higher confidence, in place), never create
   a second edge. (You already had a double-extraction bug; at a tier boundary it returns.)

## 2. Is the persistent enrichment schema sufficient?
**No — it doesn't exist, and `parser_result_cache` is not a substitute.** You need a **ledger**
(`enrichment_status`) that is content-keyed (sha256 + parser_version + grammar_dialect +
resolver_fingerprint), with a `state` (pending|enriched|failed|unsupported|stale|skipped),
stale-detection, and idempotent write-back via an `origin = baseline|enrichment` provenance column.
See `ENRICHMENT_SPEC.md` for exact DDL. Without this you cannot enrich a 200K estate incrementally
(you'd re-pay ~96s/file every scan) and cannot re-run enrichment idempotently.

## 3. Missing COBOL/DB2/CICS/IMS/JCL facts
(Phase 7–10 already added DB2 column-level lineage + host-var bindings — good.) Still missing/thin:
- **COBOL:** `CALL ... USING` / `LINKAGE` **interface contracts** (defines the Java service
  interface — highest-value gap); data **geometry** (offsets, COMP-3, REDEFINES overlap,
  OCCURS-DEPENDING controlling field); 88-level condition names → business rules.
- **DB2:** cursor lifecycle (DECLARE/OPEN/FETCH/CLOSE); dynamic-SQL value provenance.
- **CICS:** **COMMAREA / channel-container data contracts** on LINK/XCTL/START (inter-module data
  interface, as important as CALL USING for decomposition); screen flow.
- **IMS:** DL/I function-code read/write intent; PROCOPT decode; positional PCB binding; SSA target.
- **JCL:** symbolic/PROC resolution; **ddname↔DSN reconciliation**; COND/RC flow; GDG normalization;
  scheduler cross-job triggers.
- **Cross-domain (break decomposition):** **dataset identity normalization** (JCL DSN = IMS/VSAM
  cluster = COBOL FD must be ONE node); dynamic-target resolution via compiler/link-edit listings;
  async MQ-trigger → transaction.

## 4. Risks: COPY REPLACING, dialects, generated code, extensionless
- **COPY REPLACING — correctness ship blocker.** The same copybook yields *different fields per
  including program* via per-site REPLACING. If enrichment treats copybook fields as one shared
  identity ⇒ **false cross-program field equivalence ⇒ false shared-data coupling ⇒ wrong service
  boundaries.** Capture the expansion site + substitutions per include; never merge fields across
  sites by name alone.
- **Dialects — coverage ship blocker.** ProLeap fails on 2/3 real programs here. Enrichment is
  sparse and uneven; track and surface it, never assume. A context must not "look cohesive" because
  its deep edges weren't extracted.
- **Generated code.** High volume, low insight, can dominate ANTLR time. Add a deprioritize/skip
  policy + flag.
- **Extensionless (200K).** Classification recall caps everything downstream. Add **closed-loop
  reclassification**: when ANTLR parses an `UNKNOWN_TEXT` member as COBOL, write a
  `discovery_correction` back (today only COPY-name promotion exists). Widen codepage detection
  beyond cp037 and flag low-confidence decodes.

## 5. Is CLI/UI parse status enough?
**No.** You have per-asset `coverage` + `parser_effective` + `scan_file_telemetry` — good primitives,
not the two-tier honesty surface. Add an **estate-level enrichment coverage rollup**: % baseline-only
vs % deep-enriched vs % failed/unsupported, by artifact type, in `validate`/`coverage` and the UI.
Every enrichment-derived fact carries tier + confidence so no one mistakes a baseline-only program
for a fully-understood one.

## 6. Required tests before production
- **Real estate, not fixtures**: precision/recall via `scorecards` against hand-labeled BankDemo (+
  one larger corpus).
- **Enrichment idempotency** (enrich ×2 ⇒ identical graph, zero dup edges).
- **Stale detection** (bump sha or parser_version ⇒ only affected members re-enriched).
- **Tier isolation** (enrichment timeout/failure on file X leaves baseline-X intact, scan COMPLETE).
- **Baseline completeness** (full graph + service-candidates with enrichment OFF).
- **Supersession/merge** (ANTLR edge replaces, not duplicates, the baseline edge of same identity).
- **Concurrency** (N enrichment workers + WAL ⇒ no "database is locked", no lost writes).
- **Scale** (200K baseline memory+time; enrichment throughput/night).
- **COPY REPLACING per-site divergence** (two programs, same copybook, different REPLACING ⇒ distinct
  field sets).
- **Extensionless recall** + closed-loop reclassification.

## 7. Performance risks & mitigation
- **Baseline (~0.02–0.1s/file × 200K ≈ minutes–low hours): feasible.** Watch:
  whole-estate-in-memory (batch/stream), and **field-node explosion** (measured 17,578 assets /
  19,106 `DECLARES_COPYBOOK_FIELD` for *12* programs → billions at scale). **Bound copybook-field
  expansion** (model a layout once, reference it) or it sinks the graph.
- **ANTLR enrichment (30–100s/file, ⅓ success): never synchronous, never on the scan path.**
  Out-of-band ProcessPool, hard per-file timeout, concurrency cap, **incremental via the ledger**,
  resumable, **priority-ordered** (roots / high-degree / changed first — you'll never finish all
  200K). Single DB writer or batched `executemany` under WAL.
- **State the honest ceilings**: name the SQLite→Postgres trigger and NetworkX node/edge limit
  before claiming 200K. (`storage.py` already raises `NotImplementedError` for Postgres — keep that
  honesty; publish the number where SQLite stops being enough.)

## 8. Correctness gaps that mislead modernization / Java decomposition
1. **Partial enrichment treated as complete** → a context looks cohesive only because deep edges are
   missing. The DDD read-model must downgrade confidence when members are baseline-only.
2. **Dynamic calls under-resolved** → blast radius under-reported where risk is highest. Keep+flag
   with candidate sets + value provenance.
3. **Dataset identity fragmentation** → one file becomes 3 nodes → wrong data ownership → wrong
   decomposition.
4. **Per-site COPY REPLACING false equivalence** → phantom shared-data coupling.
5. **Inferred shown as confirmed / confidence not capped per tier** → trust laundering.
6. **Enrichment edges duplicating baseline edges** → inflated coupling → wrong centrality/clustering.

---

## Ship blockers (must fix before production)
1. Baseline authoritative & complete; ANTLR strictly off the critical path (today: ANTLR-first).
2. Persistent, content-keyed, stale-aware, idempotent enrichment ledger (missing; `parser_result_cache` ≠ ledger).
3. Merge by supersession, never duplicate, at the tier boundary.
4. Partial-by-default coverage tracked + surfaced; modernization read-models downgrade confidence for baseline-only members.
5. Field-node explosion bounded.
6. COPY REPLACING per-site field identity correctness.
7. Real-estate precision/recall gate (scorecards on labeled ground truth) — not fixture-only green.

Items in §3 (missing facts) and §5 (status rollup) are high-value but incremental. The seven above
are where a wrong design **silently corrupts the Java-decomposition output**. See `ENRICHMENT_SPEC.md`
for the concrete schema + merge + command contract that closes ship blockers 1–4.
