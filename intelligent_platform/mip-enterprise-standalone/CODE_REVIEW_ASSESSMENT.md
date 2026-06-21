# MIP Enterprise Intelligence — Code Review (Assessment #1)

> Date: 2026-06-20. Reviewer: Claude (Opus 4.8). Method: 10-dimension multi-agent
> review; the verification stage and 2 dimensions were cut short by an org spend
> limit, so every critical/high finding below was **personally re-verified against
> the current code**. Verification status is tagged per finding.
>
> Ground truth: `pytest` → **34 passed (exit 0) in 185s**.

## Bottom line

Genuinely good work for a v0.1, and noticeably more principled than most "AI mainframe
modernization" code: the evidence+confidence envelope is real and threaded everywhere,
the parser's dynamic-call discipline and confidence-capping are textbook-correct, and the
read-side (bounded graph slices) honestly delivers its promise.

But the **write/scale/concurrency side does not yet back the "production-direction,
200K-file" framing**, and there is **one flagship principle gap**: the platform's own
`validate` gate fails on any realistic scan, and no test catches it. Defects are
concentrated and fixable — most are 5–30 line changes, and in two cases the correct
pattern already exists elsewhere in the same file.

The thinking is production-grade; the durability isn't yet — and the docs currently
oversell in one direction and undersell in another.

---

## Confirmed findings (verified against current code)

### Ship-blockers / High

**1. Every COBOL call/SQL/file fact is extracted twice — and the duplicate is laundered to `confirmed`/1.0.**
The ANTLR `analysis` block emits CALLS/READS_TABLE/WRITES_TABLE edges, then an
**unconditional** regex pass at `ingestion.py:1221-1285` emits the same edges again. The
dedup key includes the attributes JSON (`ingestion.py:1746-1747`); parser edges carry
`{"parser_effective":...}` and regex edges carry `{}`, so both survive. The regex copy
uses `_found` defaults — `confidence=1.0, validation_status="confirmed"`
(`ingestion.py:1880-1884`) — so a call the parser correctly capped/flagged reappears as a
confirmed fact. Double-counts node degree, heatmap weights, relationship totals.
Fix: gate the regex pass on `if not analysis:` (degrade-only), or exclude rel-types the
parser already produced. (Verified.)

**2. Target-only assets carry no evidence -> `validate` fails on every real scan.**
In `_persist_graph`, evidence is built only `if asset.member_id:` (`ingestion.py:438-449`).
Tables, called programs, datasets, and `UNRESOLVED` dynamic targets have no `member_id`,
so they persist with zero evidence rows — and `api.validate`'s `assets_have_evidence`
check (`api.py:76-81`) counts exactly those. Passes today only because the demo seed
attaches evidence everywhere and the phase-2 tests never call `validate`.
Fix: attach >=1 Evidence per asset from the relationship that introduced it. (Verified.)

**3. `upsert_asset` uses `INSERT OR REPLACE`, which cascade-deletes the asset's relationships.**
`upsert_asset` does `INSERT OR REPLACE INTO asset` (`repositories.py:219-228`);
`relationship.source/target_asset_id` are `ON DELETE CASCADE` with FKs ON
(`schema.sql:64-65`, `repositories.py:80`). On a PK conflict this is delete-then-insert,
firing the cascade. Masked in the normal path, but `resume=True` re-ingestion would
destroy existing edges. `create_run` already uses the safe `ON CONFLICT DO UPDATE`
(`repositories.py:119`) — apply that pattern to asset/relationship. (Verified.)

**4. `recompute_summaries` is an N+1 (2 COUNT queries per asset) and runs twice per analyze.**
`graph_service.py:372-381` loops over every asset issuing two `COUNT(*)` queries — ~400K
point queries at 200K assets. `api.analyze` calls it again (`api.py:53`) after ingestion
already did. Fix: two `GROUP BY` aggregates; dedupe the double call. (Verified.)

**5. Parallel scan can't actually parallelize, and has no WAL under concurrent writers.**
Parse fan-out uses `ThreadPoolExecutor` (`ingestion.py:331-343`) but COBOL parsing is
pure-Python ANTLR -> GIL-bound, so `max_workers` yields ~no CPU speedup; `connect()` sets
only `PRAGMA foreign_keys=ON` — no WAL, no `synchronous` tuning (`repositories.py:76-88`).
Fix: `ProcessPoolExecutor` for real parse parallelism; set WAL + `synchronous=NORMAL`. (Verified.)

**6. Docs are stale in both directions.** `readme_ip.md:196-200` lists parallel scan,
timeout controls, and IMS parsing as still-needed though Phase 1/2 ship them; meanwhile the
entire `--config` surface is undocumented. (Verified.)

### Medium

**7. Scan recompute is non-atomic** — DELETE commits separately from rebuild
(`graph_service.py:363-382`); crash leaves an empty `RUNNING` run. (Verified.)

**8. DB2 column parser doesn't strip SQL comments** (`ingestion.py:1534-1577`) -> drops a
real column, emits a `--` phantom, as `confirmed`/0.95. (Verified.)

**9. `parse_timeout_seconds` is a soft post-hoc flag, not a timeout** (`ingestion.py:868-902`);
a hung parse blocks its worker forever. (Verified.)

**10. The repository "PostgreSQL parity" seam is largely fictional** — services call
`connect()` + raw SQLite SQL + private helpers directly. (Verified.)

**11. Ingestion duplicates the repository's own INSERT SQL** (`ingestion.py:474-564`). (Verified.)

**12. Hardcoded confidences presented with false precision** in `domain_architecture.py`
and `capability_naming.py` (all correctly labeled `inferred`). (Verified.)

### Lower

- `api.validate` has two checks hardcoded `passed=True` (`api.py:109-117`). (Verified.)
- `api._ingestion_backend` dynamically imports a module + entry point that don't exist
  (`api.py:393-413`) — 2 of 3 branches dead. (Verified.)
- `relationship_id` hashes `str(dict)` (`models.py:83-92`) — order-dependent, fragile. (Verified.)
- `ingestion.py` is ~2,000 lines mixing many responsibilities. (Watch-item.)

---

## False positive caught (why verification matters)

**`frontend-1` ("ScanQualityPanel reads `check.name` but backend returns `check_name`") is wrong.**
The actual current code reads `check.check_name || check.name` (`main.jsx:454-456`) — the
contract drift is already handled. No action needed.

---

## Finder-reported, NOT independently verified

Treat as leads: whole-estate text held in memory (`ingestion.py:160-243`); IMS
`DEFINES_IMS_DATABASE` only matches non-standard `DBDGEN NAME=` (`ingestion.py:1586`);
`required_files` IN-clause can exceed SQLite's 32766-param limit; `GraphExporter.json_bundle`
loads the whole run unbounded (`exporters.py:16-26`); `_community_clusters` loads all
assets+relationships into memory every scan; 360-Workbench `GraphCanvas` renders up to 1500
SVG nodes uncapped; `openNode`/`openEdge`/`seedDemo` await with no try/catch.

---

## Two dimensions the spend limit killed — direct inspection

**Security (self-hosted threat model):** SQL injection low (parameterized; f-strings only
for placeholder lists + hardcoded table names). CORS wide open — `allow_origins/methods/
headers=["*"]` (`api.py:486-491`); fine for localhost, hazard if networked. No PII/secret
handling though the design names that capability. Resource exhaustion via no-hard-timeout
parse + unbounded exporters.

**Tests:** Real green suite (34 passed); failure/quarantine + parse-cache paths tested. But
phase-2 tests assert presence not counts (double-extraction invisible) and never call
`validate` (missing-evidence invisible). No concurrency / cascade / DB2-comments / resume /
memory tests. No frontend tests. No ground-truth precision/recall harness; phase-3 tests run
against the seeded fixture (read-model shape, not real extraction).

---

## Genuine strengths

- Evidence/confidence envelope is first-class (`models.py`).
- Dynamic-call discipline exactly to spec (kept + flagged, never dropped).
- Confidence capping on degraded parses is correct.
- `COPY ... REPLACING` expansion is correct (pseudo-text vs word-boundary, recursive + cycle guard).
- Read-side graph slices genuinely bounded with honest `truncated` flags + caching.
- `IntelligenceApi` facade: CLI and FastAPI are thin adapters over one surface.
- Layering is real (Inventory -> Metadata -> Graph -> Reasoning -> Modernization).
- Phase 4 UI is internally coherent; every endpoint is backed by real code.

---

## Recommended fix order

1. #2 missing evidence + a `validate`-on-real-scan test (restores flagship invariant).
2. #1 double-extraction + a "single edge per call site" test.
3. #3 `INSERT OR REPLACE` -> `ON CONFLICT DO UPDATE`.
4. #4 N+1 recompute -> `GROUP BY`, stop calling twice.
5. #5 WAL + ProcessPool (or document threads as I/O-only).
6. #6 fix the README in both directions.
7. Then mediums (#7–#12) and the unverified leads.
