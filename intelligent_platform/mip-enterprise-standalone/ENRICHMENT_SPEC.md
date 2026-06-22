# Enrichment Spec v2 — Persistent ANTLR Deep-Enrichment (implementation target)

> Target tree: `mip-enterprise-standalone` (sole canonical tree). Supersedes v1.
> Status: **NOT implemented** (verified 2026-06-22 — still ANTLR-first, no ledger, no `enrich`).
> Reviewed and agreed by Claude + Codex. This is the buildable target.

### Changelog from v1 (the corrections we agreed on)
- **Two-layer ledger** instead of one content-keyed table: a content **artifact cache** + a
  run/member **materialization status** (graph facts are run- and member-scoped).
- **`relationship_id` must exclude attributes** (root cause; see §3) — prerequisite for supersession.
- **Baseline keeps the COPY/REPLACING preprocessor** (do not drop COPY expansion when removing ANTLR).
- **Subprocess-per-file timeout with terminate**, not a plain `ProcessPoolExecutor` (running futures
  aren't reliably killable).
- **Per-fact confidence** (parser confidence is a *ceiling*, not the value).
- **`enrichment_job` history** + **`enrichment_fact_source`** (preserve baseline evidence; never
  overwrite history silently).
- **Bounded copybook layout** and **missing facts** reframed from "later/optional" to **scoped
  milestone steps** that gate decision-grade output.

---

## ⚠️ DECISION-GRADE STATEMENT (must be honored in code and UI)

- **The two-tier parser architecture (Phases 1–2 below) can ship first.** It makes scans fast,
  durable, and incrementally enrichable.
- **The modernization / Java-decomposition output is NOT decision-grade** until **interface
  contracts (CALL USING + LINKAGE)**, **CICS COMMAREA / channel / container contracts**, **DB2 /
  dataset identity normalization**, and the **bounded copybook layout** are implemented (Phases 3–4).
- Until then, `domain_contexts`, `service_candidates`, and `roadmap` MUST be stamped
  `decision_grade = false`, `validation_status = needs_review`, and carry the banner:
  *"Structural map only — service interfaces and data ownership are not yet extracted; not for
  cutover/decomposition decisions."* This prevents the platform from looking more certain than it is.

---

## 0. Model in one paragraph
The **baseline** (`preprocess` + `cobol_ast`) parses **every** file during `analyze` and is the
authoritative graph. **Enrichment** (ANTLR full grammar) runs **out-of-band** via `mip enrich`: it
parses pending/stale members (priority-ordered, bounded, resumable) in **terminable subprocesses**,
**caches the parse artifact by content**, **materializes** facts into the run's graph by
**supersession** (replace the baseline fact of the same identity, never duplicate), and records
**job history + per-fact source**. Re-running enrichment yields an identical graph. Coverage
(baseline-only vs enriched vs failed) and decision-grade status are first-class, surfaced metrics.

---

## 1. Implementation roadmap (agreed sequence)

### Phase 1 — Foundation (prerequisites; must be stable before any write-back)
1. **Remove ANTLR from synchronous `analyze`.** Split `parse_cobol` (baseline-only) and
   `parse_cobol_deep` (ANTLR). §5.
2. **Keep COPY/REPLACING preprocessor in baseline** — baseline = `preprocess(text, resolver)` →
   `cobol_ast`, not raw `cobol_ast`. §5.
3. **Fix `relationship_id` to exclude attributes** + declared per-type discriminator. §3.
4. **Two-layer enrichment model**: `enrichment_artifact_cache` (content) +
   `enrichment_member_status` (run/member). §2.
5. **Job history + fact-source tracking**: `enrichment_job`, `enrichment_fact_source`. §2.
   *Acceptance:* `analyze` makes zero ANTLR calls; relationship ids are attribute-independent;
   ledger tables exist; full baseline graph + service-candidates work with enrichment OFF.

### Phase 2 — Persistent ANTLR enrichment
6. **`mip enrich`** command. §6.
7. **Subprocess-per-file timeout** (reuse the existing `mp.Process`+queue+terminate pattern), not
   `ProcessPoolExecutor`. §6.
8. **Persist** ANTLR AST, diagnostics, extracted facts, status, timestamps (artifact cache). §2/§6.
9. **Idempotent supersession write-back**. §4.
10. **CLI/UI parser status + enrichment coverage rollup**. §9.
    *Acceptance:* enrich ×2 → identical graph; deep CALL edge replaces (not duplicates) the baseline
    edge; stale detection re-enriches only changed members; tier failure leaves baseline intact.

### Phase 3 — Bounded copybook layout redesign (same milestone, separate step)
11. Model **copybook layout once**; **per-include-site expansion** separately; field identity =
    `program + copy-line + copybook + replacement-map + field`; **prevent field-node explosion**. §7.
    *Acceptance:* a copybook included by N programs does NOT create N× field nodes; per-site
    REPLACING differences are distinct; two programs with different REPLACING are not falsely coupled.

### Phase 4 — Decision-grade decomposition gates
12. **CALL USING + LINKAGE** interface contracts.
13. **CICS COMMAREA / channel / container** contracts.
14. **DB2 / dataset identity normalization** (JCL DSN = IMS/VSAM cluster = COBOL FD → one node).
15. **Flip `decision_grade` to true** only when 11–14 exist; until then downgrade service-candidate
    confidence + show the banner. §9.

---

## 2. Schema additions (Phase 1 & 2)

```sql
-- Content-keyed parse artifact cache (run-INDEPENDENT). Caches the expensive ANTLR parse RESULT.
CREATE TABLE IF NOT EXISTS enrichment_artifact_cache (
    artifact_id          TEXT PRIMARY KEY,   -- stable_id(source_sha256, parser_version, grammar_dialect, resolver_fingerprint)
    source_sha256        TEXT NOT NULL,
    parser_version       TEXT NOT NULL,
    grammar_dialect      TEXT NOT NULL DEFAULT 'ibm-enterprise-cobol',
    resolver_fingerprint TEXT NOT NULL,
    parse_status         TEXT NOT NULL,      -- parsed | failed | unsupported
    ast_json             TEXT,               -- deep AST / canonical payload (reusable across runs)
    diagnostics_json     TEXT NOT NULL DEFAULT '{}',  -- ANTLR errors, partial-parse notes
    fact_count           INTEGER NOT NULL DEFAULT 0,
    parser_confidence    REAL NOT NULL DEFAULT 0,
    elapsed_ms           REAL NOT NULL DEFAULT 0,
    created_at           TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_enrich_artifact_sha ON enrichment_artifact_cache(source_sha256);

-- Run/member materialization status (run-SCOPED). Did this member's deep facts land in THIS run's graph?
CREATE TABLE IF NOT EXISTS enrichment_member_status (
    run_id           TEXT NOT NULL REFERENCES run_manifest(run_id) ON DELETE CASCADE,
    member_id        TEXT NOT NULL,
    source_sha256    TEXT NOT NULL,
    artifact_id      TEXT,               -- which cached parse was used
    state            TEXT NOT NULL,      -- pending | materialized | failed | unsupported | stale | skipped
    priority         INTEGER NOT NULL DEFAULT 0,
    attempts         INTEGER NOT NULL DEFAULT 0,
    last_error       TEXT,
    materialized_at  TEXT,
    updated_at       TEXT NOT NULL,
    PRIMARY KEY (run_id, member_id)
);
CREATE INDEX IF NOT EXISTS idx_enrich_member_state ON enrichment_member_status(run_id, state, priority DESC);

-- Enrichment job history (audit + resumability).
CREATE TABLE IF NOT EXISTS enrichment_job (
    job_id          TEXT PRIMARY KEY,
    run_id          TEXT NOT NULL REFERENCES run_manifest(run_id) ON DELETE CASCADE,
    started_at      TEXT NOT NULL,
    finished_at     TEXT,
    status          TEXT NOT NULL,       -- RUNNING | COMPLETED | FAILED | CANCELLED
    selected_count  INTEGER NOT NULL DEFAULT 0,
    enriched_count  INTEGER NOT NULL DEFAULT 0,
    failed_count    INTEGER NOT NULL DEFAULT 0,
    skipped_count   INTEGER NOT NULL DEFAULT 0,
    config_json     TEXT NOT NULL DEFAULT '{}'
);

-- Per-fact provenance: a fact may have BOTH baseline and enrichment sources (preserve history).
CREATE TABLE IF NOT EXISTS enrichment_fact_source (
    fact_source_id   TEXT PRIMARY KEY,   -- stable_id(run_id, entity_kind, entity_id, origin)
    run_id           TEXT NOT NULL REFERENCES run_manifest(run_id) ON DELETE CASCADE,
    entity_kind      TEXT NOT NULL,      -- ASSET | RELATIONSHIP
    entity_id        TEXT NOT NULL,
    origin           TEXT NOT NULL,      -- baseline | enrichment
    source_member_id TEXT NOT NULL,
    evidence_id      TEXT,
    parser_tier      TEXT NOT NULL,      -- cobol_ast | antlr-full | regex
    confidence       REAL NOT NULL,
    created_at       TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_fact_source_entity ON enrichment_fact_source(run_id, entity_kind, entity_id);

-- Fast-filter provenance on the graph rows themselves (add to table defs; migrate with ALTER if missing).
ALTER TABLE asset        ADD COLUMN origin TEXT NOT NULL DEFAULT 'baseline';   -- baseline | enrichment
ALTER TABLE asset        ADD COLUMN enriched_by_member TEXT;
ALTER TABLE relationship ADD COLUMN origin TEXT NOT NULL DEFAULT 'baseline';
ALTER TABLE relationship ADD COLUMN enriched_by_member TEXT;
```

**Stale rule:** a member is `stale`/`pending` when its current `source_sha256` has no
`enrichment_artifact_cache` row whose `(parser_version, grammar_dialect, resolver_fingerprint)`
matches the current engine config, OR `enrichment_member_status.state != 'materialized'`. Bumping
`PARSER_VERSION`/dialect invalidates and re-enriches automatically.

## 3. Relationship identity fix (Phase 1 — prerequisite)
`relationship_id` currently salts the hash with `self.attributes` (`models.py:91`), so the same
logical edge with richer ANTLR attributes becomes a *different* edge → supersession can't find the
baseline edge. Fix:

```python
# models.py
@property
def relationship_id(self) -> str:
    return stable_id(self.run_id, "relationship", self.relationship_type,
                     self.source_asset_id, self.target_asset_id, self._discriminator())

def _discriminator(self) -> str:
    # Empty for supersedable single-instance edges (CALLS, READS_TABLE, USES_COPYBOOK, ...).
    # For edge types that legitimately carry multiplicity (e.g. FLOWS_TO between the same two
    # fields on different lines/kinds), return a DECLARED, order-independent key (e.g. f"{kind}:{line}")
    # — NEVER the whole attributes dict.
    return _DISCRIMINATOR.get(self.relationship_type, "")

@property
def fact_hash(self) -> str:           # diagnostics only, NOT identity
    return stable_id(json.dumps(self.attributes, sort_keys=True))
```
This is more precise than "drop all attributes" (which over-collapses multiplicity edges) and fixes
the old attribute-salted-id bug (Assessment #1 finding `sql-4`). **Migration:** bump
`schema_version`; ids regenerate on the next full scan — document that enabling enrichment requires
one fresh baseline scan (or a re-key migration).

## 4. Supersession write-back (Phase 2) — the algorithm
For each member `M` whose artifact `parse_status='parsed'`, run inside a **single DB writer**:
```
1. PURGE prior enrichment for M (idempotent re-enrichment):
     DELETE FROM relationship      WHERE run_id=? AND origin='enrichment' AND enriched_by_member=?
     DELETE FROM asset             WHERE run_id=? AND origin='enrichment' AND enriched_by_member=?
     DELETE FROM enrichment_fact_source WHERE run_id=? AND origin='enrichment' AND source_member_id=?
2. For each deep fact, identity = relationship_id (now attribute-independent, §3).
3. If a row with that identity exists (baseline or prior):
     UPDATE in place -> origin='enrichment', enriched_by_member=M,
       confidence = min(fact_confidence, parser_confidence_cap), richer attributes_json,
       validation_status (honest: 'confirmed' only if directly observed).
   Else INSERT a new enrichment row.
4. INVARIANT: never two live rows of the same identity (enforced by ON CONFLICT DO UPDATE).
5. APPEND an enrichment_fact_source row (origin='enrichment', tier='antlr-full', confidence,
   evidence_id) — do NOT delete the baseline fact_source row. History is preserved; the live edge is
   the enriched one, but its baseline provenance remains queryable.
6. Update enrichment_member_status(run, M) -> state='materialized', materialized_at, artifact_id.
```
Idempotency: enrich ×2 ⇒ identical `asset`/`relationship`/`evidence` rows.

## 5. Baseline-first parser ordering (Phase 1)
`reference_parser.parse_cobol(text, resolver)` becomes **baseline-only**, preserving COPY expansion:
```python
def parse_cobol(text, resolver=None):           # BASELINE — runs in analyze, no ANTLR
    raw_unit = cobol_ast.parse(text)            # copies-from-raw + fallback fields
    expanded = antlr_adapter.preprocess(text, resolver=resolver)   # KEEP COPY/REPLACING expansion
    expanded_unit = cobol_ast.parse(expanded)
    return _unit_payload(raw_unit, expanded_unit, text, expanded, {"effective": "baseline-cobol_ast"}, resolver)

def parse_cobol_deep(text, resolver=None):      # ENRICHMENT — only mip enrich calls this
    ...                                         # the current ANTLR full-grammar path (former lines 103-116)
```
`analyze` calls `parse_cobol` only ⇒ zero ANTLR on the scan path.

## 6. `mip enrich` contract (Phase 2)
```
mip --db DB enrich [--run-id ID] [--changed-only] [--top-N 5000]
                   [--max-workers 8] [--timeout 20] [--priority roots|degree|changed|none]
```
- **Select** members where `enrichment_member_status` ∈ {pending, stale} (or sha-changed with
  `--changed-only`), ordered by priority (roots → high node-degree → changed), capped at `--top-N`.
- **Parse** via `parse_cobol_deep` in **terminable subprocess workers** — one file per subprocess (or
  `max_tasks_per_child=1`), with a hard timeout that **terminates the process** on overrun (reuse the
  existing `mp.Process`+queue+terminate / `parallel_backend="hard-timeout-process"` pattern). On
  overrun/exception: `state='failed'`, write `scan_issue`, job continues.
- **Cache** the parse artifact (AST + diagnostics) in `enrichment_artifact_cache` keyed by content.
- **Write back** via §4 from a **single writer** under WAL (collect worker payloads, write in main).
- **Resumable**: re-run continues from pending/stale; `materialized` skipped. Open an `enrichment_job`
  row; finalize counts on completion.
- **Closed-loop reclassification**: if an `UNKNOWN_TEXT` member parses cleanly as COBOL, emit a
  `discovery_correction` so baseline reclassifies it next scan.

## 7. Bounded copybook layout (Phase 3) — kills field-node explosion
**Problem:** today every program that COPYs a copybook instantiates a node per field
(measured 17,578 assets / 19,106 `DECLARES_COPYBOOK_FIELD` edges for 12 programs → billions at scale).
**Model:**
```
Copybook (1)  --DECLARES_FIELD-->  Field          # fields belong to the copybook, defined ONCE
Program       --USES_COPYBOOK-->   Copybook
Program       --HAS_COPY_SITE-->   CopyExpansionSite { program, copy_line, copybook, replacement_map_hash }
CopyExpansionSite --FIELD_OVERRIDE--> Field        # ONLY when REPLACING actually changes a field
```
- A program referencing a copybook does **not** create per-program field nodes — fields are resolved
  via the copybook. Program-local (non-copybook) data items stay program-scoped.
- Per-include-site identity = `program + copy-line + copybook + replacement-map + field`, so two
  programs with different `REPLACING` are **not** falsely coupled, and only actual overrides
  materialize extra nodes.
- Field-level lineage (`FLOWS_TO`) references `(copybook, field)` + site context, not a per-program
  field node.
- **Result:** node count ≈ unique copybook fields + program-local fields + (small) expansion sites —
  not fields × programs.

## 8. Per-fact confidence (Phase 2)
Each extracted fact carries **its own** confidence + validation_status. `parser_confidence_cap`
(full-grammar 0.95) is a **ceiling** applied as `min(fact_confidence, cap)`. A directly-parsed SQL
table edge is high; *inferred* business intent derived from it is lower and `inferred`/`needs_review`.
Never stamp inference as `confirmed`.

## 9. Parser status, coverage rollup & the decision-grade gate (Phases 2 & 4)
- **Estate coverage rollup** in `validate`/`coverage` + UI: `{members, baseline_only_pct,
  enriched_pct, failed_pct, unsupported_pct, by_artifact_type:{...}}` (derive from
  `enrichment_member_status` ⋈ `source_member`).
- **Decision-grade flag** on modernization outputs:
  `decision_grade = interface_contracts_present AND commarea_contracts_present
                    AND dataset_identity_normalized AND bounded_copybook_layout`.
  Until true, `domain_contexts`/`service_candidates`/`roadmap` carry `decision_grade=false`,
  `validation_status='needs_review'`, and the banner from the top of this doc.

## 10. Test gate (must pass before production)
| Test | Asserts |
|---|---|
| Zero ANTLR in analyze | scan makes no `parse_cobol_deep` calls |
| Baseline keeps COPY expansion | baseline resolves `COPY ... REPLACING` (no ANTLR) |
| relationship_id attribute-independent | same (type,src,tgt), different attrs → same id |
| Baseline-only completeness | full graph + roots + service-candidates with enrichment OFF |
| Enrichment idempotency | enrich ×2 → identical rows, zero dup edges |
| Supersession | deep CALL edge replaces (not duplicates) baseline edge; baseline fact_source preserved |
| Stale detection | bump `PARSER_VERSION` → only affected members re-enriched |
| Tier isolation | deep timeout/failure on file X → baseline-X intact, job completes |
| Subprocess kill | a non-terminating parse is terminated at `--timeout`, core freed |
| Concurrency | N workers + WAL → no "database is locked", no lost writes |
| Copybook layout bound | copybook in N programs → no N× field nodes |
| Per-site COPY REPLACING | two programs, same copybook, different REPLACING → distinct, uncoupled |
| Coverage honesty | baseline-only context flagged / down-confidence in service-candidates |
| Decision-grade gate | service-candidates `decision_grade=false` until Phase 4 facts exist |
| Real-estate scorecard | precision/recall on hand-labeled BankDemo ≥ agreed threshold |
| Scale smoke | baseline 200K memory/time in budget; enrich top-N within nightly window |
