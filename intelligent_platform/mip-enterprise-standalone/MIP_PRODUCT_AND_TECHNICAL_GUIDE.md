# MIP — Mainframe Intelligence Platform
### Product & Technical Guide

*A single guide for anyone who will use or work on MIP. It explains, in plain words, every
functionality built so far — what it does, how it works (with a small real code snippet), a
concrete example, and the problem it solves. Grounded in the actual `mip-enterprise-standalone`
codebase.*

---

## 1. What MIP is — in 30 seconds

Old mainframe systems (COBOL, JCL, DB2, CICS, IMS, VSAM) are huge, undocumented, and risky to
change. **MIP reads that legacy estate and turns it into a trustworthy, queryable map** — every
program, job, table, file, and the links between them — *before* anyone tries to modernize it.

Its one rule: **understand before you transform.** And its one promise: **never guess in disguise.**
Every fact MIP records carries (1) the **evidence** it came from, (2) a **confidence** from 0.0 to
1.0, and (3) a **validation status** — `confirmed`, `inferred`, or `needs_review`. A guess is never
shown as a fact, and anything unresolved (like a dynamic call) is **kept and flagged**, never
dropped.

> **The problem it solves:** the riskiest moment in any mainframe modernization is the start, when
> nobody actually knows what the system contains or how it connects. MIP replaces guesswork with an
> evidence-cited map, so a team can scope, sequence, and de-risk a rewrite (e.g. COBOL → Java).

---

## 2. How it works — the six layers

MIP works in strict order. **You never skip a layer.**

```
1. INVENTORY     walk the estate, identify every file
2. METADATA      parse each file into structured facts
3. GRAPH         link those facts as nodes + edges in SQLite
4. REASONING     roots, clusters, bounded contexts, service candidates, roadmap
5. COPILOT       grounded LLM explanations that must cite the graph
6. MODERNIZATION export evidence bundles for the rewrite
```

Each layer reads only the layer below it. The UI deliberately shows **bounded slices** of the
graph, never the whole thing, because real estates can be 200K+ files.

---

## 3. The idea that makes MIP trustworthy: the evidence envelope

Everything rests on one small data shape. Every asset and every relationship carries this:

```python
@dataclass(frozen=True)
class Evidence:
    source_path: str
    line_start: int | None = None
    line_end: int | None = None
    evidence_text: str = ""
    extractor: str = "manual"
    discovery_method: str = "observed"
    confidence: float = 1.0
    validation_status: str = "confirmed"   # confirmed | inferred | needs_review
```
*(src/mip_intel/models.py)*

Because confidence and status travel **with** each fact (and are stored per-row in SQLite), an
inference can never be silently promoted to a proven fact. This is MIP's honesty contract — keep it
in mind for every section below.

---

## 4. The layers in detail

Each subsystem below follows the same shape: **what it does → how → a real example → what it solves
→ details that matter.**

### 4.1 Inventory — Discovery & classification
**Finds every file and names what it is, even with no file extension.**

Mainframe files often have no `.cbl`/`.jcl` extension, so MIP classifies in a ladder: **folder
signal → content signal → "referenced by another file" promotion**, falling back to `UNKNOWN_TEXT`
(kept for review) when nothing matches.

```python
for markers, artifact_type in FOLDER_TYPES:
    if _contains_ordered(parts, markers):
        return artifact_type, f"folder:{'/'.join(markers)}", 0.95, "confirmed"
content_rules = (
    ("COBOL",    "content:PROGRAM-ID",            0.90, r"\bPROGRAM-ID\s*\."),
    ("JCL",      "content:JCL JOB/EXEC",          0.85, r"(?m)^\s*//\S+\s+(JOB|EXEC)\b"),
    ("COPYBOOK", "content:copybook level numbers",0.70, r"(?m)^\s*(01|05|10|77)\s+\S+"),
)
```
*(src/mip_intel/ingestion.py)*

> **Example.** A file `copylib/CUSTREC` (no extension) → `COPYBOOK`, basis `folder:copylib`,
> confidence 0.95, `confirmed`. A stray file first scored `UNKNOWN_TEXT` (0.35) but referenced as
> `COPY CUSTREC` elsewhere → promoted to `COPYBOOK`, basis `referenced-by-copy-name`, 0.82,
> `inferred`.

**Solves:** a complete, honest file inventory — including extensionless and EBCDIC files ordinary
tools mislabel or skip — so the whole pipeline starts from a trustworthy list.

**Details that matter:**
- Encoding detection tries utf-8 → cp037 (EBCDIC) → latin-1; EBCDIC files are tagged `DECODED` and
  kept readable, not dumped as binary.
- Binary is detected with no parser: a NUL byte, >30% non-printable bytes in the first 8 KB, or size
  over 4 MB → `BINARY` (kept, flagged unparseable).
- `member_id` is a stable hash of `(run_id, "member", relative_path)` → re-scans upsert, never
  duplicate.
- `file_inventory_cache` makes re-scans skip unchanged files (basis `inventory-cache:`).
- `run_manifest` = scan provenance; `scan_issue` quarantines failures (one bad file never aborts the
  scan); `discovery_correction` lets a human override a wrong guess.

### 4.2 Metadata — Parsing (two COBOL parsers behind one call)
**Turns COBOL text into structure: program id, divisions, paragraphs, fields, CALLs, COPYs, SQL,
CICS, and field-to-field flows.**

There are two parsers. A fast hand-written one (`cobol_ast`) always runs. A full COBOL-85 grammar
(ANTLR) is tried for deeper coverage. `reference_parser.parse_cobol` is the single entry point.

```python
if cobol_antlr is not None and cobol_antlr.available():
    try:
        expanded_text = antlr_adapter.preprocess(text, resolver=resolver)
        expanded_unit = cobol_antlr.parse(text, resolver=resolver, pre=expanded_text)
        parser_backend_info["effective"] = "local-antlr4-full-grammar"
        return _unit_payload(raw_unit, expanded_unit, text, expanded_text, parser_backend_info, resolver)
    except Exception as exc:
        parser_backend_info["antlr4_error"] = type(exc).__name__
# ... falls through to preprocessor + cobol_ast
```
*(src/mip_intel/reference_parser.py)*

> **Example.** `MOVE 'CRDPOST' TO WS-PGM` then `CALL WS-PGM` → MIP recovers the real target by
> **constant propagation**: `{target: CRDPOST, kind: resolved, via: WS-PGM, confidence: 0.7,
> validation: inferred}` — never shown as `confirmed`.

**Solves:** dependency facts you can trust before touching code — full coverage when ANTLR works, a
guaranteed result when it doesn't, and a clear label of which facts are proven vs inferred.

**Details that matter:**
- `COPY ... REPLACING` is genuinely expanded (recursive, with a cycle guard, depth cap 25); an
  unresolved COPY is removed so parsing continues, but the COPY *edge* is still recorded.
- Confidence is capped by parser mode: 0.95 full grammar, 0.78 degraded, 0.45 regex fallback, and
  ≤0.70 if any copybook is unresolved.
- The ANTLR path reuses the verified `cobol_ast` extractors for SQL/CICS/COPY/field-flows, so the two
  backends never disagree.
- `parser_result_cache` (keyed by source SHA + resolver fingerprint + parser version) skips
  re-parsing unchanged files.
- **Current direction (important):** ANTLR is measured at ~340× slower than `cobol_ast` and parses
  only some real programs, so the agreed plan (`PARSER_ARCHITECTURE_REVIEW.md` /
  `ENRICHMENT_SPEC.md`) is to make `cobol_ast` the authoritative baseline for every file and move
  ANTLR into a persistent, out-of-band `mip enrich` step. *That restructure is specified, not yet
  built.*

### 4.3 Metadata — Fact & relationship extraction
**Turns parsed source into evidence-backed graph edges — who calls whom, what reads/writes what,
how data and control flow — deduped and confidence-scored.**

A family of `_*_relationships` builders each handle one fact type; everything funnels through a
dedup gate:

```python
def _append_found(found, seen, rel):
    attrs_key = json.dumps(rel.attributes or {}, sort_keys=True, default=str)
    key = (rel.relationship_type, rel.source_asset_id, rel.target.asset_id, attrs_key)
    if key in seen:
        return
    seen.add(key)
    found.append(rel)
```
*(src/mip_intel/ingestion.py)*

> **Example.** `CALL 'CRDPOST'` → `CALLS → PROGRAM CRDPOST`, `static`, `confirmed`, 1.0. The same
> call through an unknown variable → `DYNAMIC_CALL → UNRESOLVED`, `needs_review`, ~0.3 — **kept and
> flagged**, not dropped.

**Solves:** the complete, cited edge list that impact and blast-radius analysis runs on — and by
keeping dynamic/unresolved calls as flagged edges, it makes the system's blind spots *visible*.

**What it captures (the edge catalog):**
| Area | Relationships |
|---|---|
| Calls | `CALLS` (static/resolved), `DYNAMIC_CALL`, with `USING` operands as an interface contract |
| Copybooks | `USES_COPYBOOK`, plus field-level `DECLARES_COPYBOOK_FIELD` / `FIELD_DERIVED_FROM_COPYBOOK` |
| DB2 | `READS_TABLE`/`WRITES_TABLE`, `DEFINES_DB2_DATABASE/TABLESPACE/BUFFERPOOL`, `DEFINES_DB2_CURSOR` (table/column/predicate), DCLGEN |
| Files/VSAM | `READS_FILE`/`WRITES_FILE`, `READS/WRITES/USES_DATASET` (direction from JCL `DISP`, GDG captured) |
| IMS | `DEFINES_IMS_DATABASE/PSB/SEGMENT/FIELD` |
| CICS | `LINK`/`XCTL`, map and queue edges |
| JCL | `CONTAINS_STEP`, `EXECUTES`, `INVOKES_PROC`, `DECLARES_DD` |
| Flow | control flow `PERFORMS`/`BRANCHES_TO`; field lineage `FLOWS_TO` (always `inferred`, ≤0.88) |

**Details that matter:** regex fallbacks only fire for fact types the structured parser didn't supply
(no double-counting); every edge carries Evidence (file + line + ≤500 chars of source); confidence is
capped by parser quality; persisted ids are deterministic and upserted (re-scan = idempotent).

### 4.4 Graph store — Persistence, schema & evidence
**One SQLite database holds the whole estate; every fact is line-pinned, confidence-scored, and
re-runnable.**

```python
conn = sqlite3.connect(self.db_path)
conn.execute("PRAGMA foreign_keys = ON")
conn.execute("PRAGMA journal_mode = WAL")
conn.execute("PRAGMA synchronous = NORMAL")
conn.execute("PRAGMA busy_timeout = 10000")
try:
    yield conn; conn.commit()
except Exception:
    conn.rollback(); raise
```
*(src/mip_intel/repositories.py — every write goes through this; WAL + busy_timeout for safe
concurrent reads, all-or-nothing commit.)*

> **Example.** Scanning `CRDPOST.cbl` writes the program asset, the `CALLS CRDVAL` edge, and a
> line-pinned evidence row. A second identical scan re-runs `ON CONFLICT DO UPDATE` — row counts are
> unchanged (idempotent).

**Solves:** a single, queryable, re-runnable record where every fact traces to exact source lines —
so no one trusts an unsupported claim, and re-scans don't pile up duplicates.

**Details that matter:**
- Every fact-carrying table has its own `confidence` + `validation_status` columns — the envelope is
  stored, not bolted on.
- `stable_id()` (16-char SHA1 of identifying parts, names upper-cased) makes writes content-addressed
  and idempotent.
- Caches make re-scans cheap: `parser_result_cache`, `graph_slice_cache`, `file_inventory_cache`.
- Rich telemetry is first-class: `scan_progress`, `scan_issue`, `scan_phase_telemetry`,
  `scan_file_telemetry` — failures are recorded, not hidden.
- `scorecard_result` stores precision/recall vs ground truth; `discovery_correction` stores human
  overrides as auditable data.
- `storage.create_repository()` is the backend factory — SQLite today; a PostgreSQL DSN raises
  `NotImplementedError` (honest, not faked).

### 4.5 Graph — Navigation & analysis
**Explore the web: search, "what calls this / what does it call" (360 call graph), required files,
roots, clusters, heatmaps — always in bounded slices.**

```python
while queue and len(nodes) < req.limit:
    asset_id, depth = queue.popleft()
    asset = self.repository.get_asset(asset_id)
    if asset is None: continue
    nodes[asset_id] = self._node(asset, depth)
    if depth >= req.depth: continue
    for rel in self.repository.relationships_for_asset(req.run_id, asset_id, ...):
        ...
```
*(src/mip_intel/graph_service.py — the bounded BFS behind every view; depth- and limit-capped, always
reports `truncated`.)*

> **Example.** `root_portfolio(run_id)` → entry-point programs (reached by a job/transaction but never
> called) ranked by risk. On the demo: `CRDPOST` — reachable_assets 7, data_touchpoints 2,
> unresolved_count 1, risk_score 0.082, `confirmed`.

**Solves:** when you inherit a mainframe nobody understands, you start from a search box and the true
entry points, then walk impact in safe slices to scope what one change touches.

**Details that matter:**
- Slices are bounded by design: depth clamped 0–8 (UI 1–4), limit 1–1500; every payload reports
  `truncated`; results are cached by a stable key.
- `call_graph` uses only call-type edges; `dependency_graph` uses the wider data+control set.
- Roots = programs with an entry edge but **zero confirmed callers** (dynamic calls can't fake a
  root).
- Clusters come from union-find over dependency edges + folder affinity; a cluster is only `inferred`
  at confidence ≥ 0.65, else "Needs Review".
- `required_files` = the exact file set (+ minimal context bundle) to hand a rewrite team or an LLM.
- Coverage reports say `not_observed` means "no evidence in this slice," **not** proof of absence.

### 4.6 Reasoning → Modernization — Domain architecture (DDD)
**Proposes how to break the estate into services and in what order — every proposal cited, never a
decision.**

```python
def modernization_roadmap(self, run_id, *, limit=50):
    candidates = self.service_candidates(run_id, limit=limit)["service_candidates"]
    ordered = sorted(candidates, key=lambda i: (-i["risk_score"], i["confidence"], i["name"]))
    ...
```
*(src/mip_intel/domain_architecture.py — risk-first, then confidence-ordered strangler sequence.)*

> **Example.** A cluster of programs writing `CARD_MASTER`/`BALANCE`/`LEDGER` →
> `name: "Card Posting & Balance Management"`, `java_service: CardPostingService`,
> `validation_status: inferred`, with `CARD_MASTER` as an `owned_write_model` data contract and a
> strangler work package — all stamped `decision_status: candidate`.

**Solves:** the hardest modernization question — *what to carve out, in what order, how risky each
piece is* — answered only from what the code proves.

**Details that matter:**
- Everything is a **proposal**: `membership_rule = "Clusters and ownership are graph-derived; LLM
  naming is advisory only"`; services are `candidate`; outputs are `inferred`/`needs_review`.
- When cluster membership is only sampled, confidence is capped at 0.82 and `confirmed` is demoted to
  `inferred`.
- Every proposal carries citations (CLUSTER/ASSET/RELATIONSHIP ids) back to the graph.
- Roles separate `owned_write_model` (tables a context writes) from `read_dependency` — the signal for
  safe data-ownership boundaries.
- Each package carries a feedback loop: quality gates (contract tests, golden-master regression,
  dual-run reconciliation) and self-correction actions.

### 4.7 Reasoning — Insights, scorecards & quality (self-checking)
**Explains what it found (with citations) and proves the graph is right (precision/recall + a
validate gate).**

```python
citations = response.get("citations") or []
if not citations:
    response["validation_status"] = "needs_review"
    response["confidence"] = min(float(response.get("confidence", 0.4)), 0.4)
```
*(src/mip_intel/llm_insights.py — an LLM insight with no citations is forced to `needs_review` at low
confidence. AI proposes; it never decides.)*

> **Example.** A scorecard with a ground-truth manifest (expects edge `CALLS CARDSRC→CARDTGT`, forbids
> `CALLS CARDSRC→WRONG`) → `{status: passed, precision: 1.0, recall: 1.0}`.

**Solves:** you must trust the map before acting on it — so MIP shows *why* each fact is claimed,
measures how complete/accurate the extraction is against known truth, and blocks any guess from being
shown as confirmed.

**Details that matter:**
- Deterministic insights (`INVENTORY_SUMMARY`, `ROOT_SUMMARY`, `INGESTION_GAPS`) are written during
  the scan, always with citations; a root with unresolved relationships drops to `needs_review`/0.75.
- Offline by default — no network call unless an LLM endpoint is configured; any error falls back to
  the deterministic summary.
- Scorecard: `recall = matched/expected`, `precision = matched/(matched+forbidden-seen)`; passes only
  with zero missing and zero forbidden.
- `validate` is a **gate**: confidences out of 0..1 or a status outside the allowed three **fail the
  run**.

---

## 5. The surfaces — how you use MIP

One Python facade, `IntelligenceApi`, holds every operation. The **CLI** and the **FastAPI server**
are thin wrappers over the same methods, so they can never drift apart.

### 5.1 CLI (`mip-intel` / `python -m mip_intel.cli`)
```python
api = IntelligenceApi(Path(args.db))
if args.command == "roots":
    print_json(api.roots(args.run_id, limit=args.limit))
```
Commands: `init-demo`, `analyze`, `stats`, `validate`, `roots`, `clusters`, `domains`,
`service-candidates`, `roadmap`, `search`, `nodes`, `graph-slice`, `call-graph`,
`dependency-graph`, `coverage`, `ast-tree`, `export`, `export-bundle`, `scorecard`, `insights`,
`serve` (+ correction/performance helpers).

> **Example.** `mip-intel --db data/mip.db init-demo && mip-intel --db data/mip.db roots --limit 1`
> → `{"roots":[{"technical_name":"CRDPOST","reachable_assets":7,"risk_score":0.082,
> "confidence":1.0,"validation_status":"confirmed"}]}`

Handy behaviors: commands default to the latest run; you can pass a **name or an id** (`CRDPOST` or
its hash); `--config` accepts JSON, `@file.json`, or a relaxed `key=value` form; `export-bundle`
writes a full reverse-engineering bundle (graph JSON + copied source) for a rewrite team.

### 5.2 API (FastAPI)
`create_fastapi_app(db)` exposes the same methods as HTTP routes — `GET /stats`, `/validate`,
`/roots`, `/clusters`, `/architecture/contexts|services|roadmap`, `/search`, `/graph/slice`,
`/graphs/call|dependencies`, `/nodes/{id}`, `/edges/{id}`, `/coverage/{asset}`, `/heatmap`, `/ast`,
`/export`, `/insights`, `POST /demo|/analyze`. A missing asset → HTTP 404; CORS is open for the
bundled frontend. Only `serve` imports uvicorn.

### 5.3 The React UI (Enterprise Intelligence Explorer)
A single-page app: a **left sidebar** searches and switches views; the **center** shows the view; a
**right rail** streams plain-language insights; a **slide-in drawer** shows the evidence behind any
node/edge you click.

```jsx
<button onClick={() => onOpenGraph(item.asset_id)}>
  <strong>{item.technical_name}</strong>
  <small>{item.asset_type} / {item.validation_status} / confidence {formatNumber(item.confidence)}</small>
</button>
```
*(frontend/src/main.jsx — every result shows type + status + confidence inline, never a bare name.)*

The seven views walk the MIP thesis: **Dashboard** (what's in the estate) → **Graph Slice** &
**Matrix** (how things connect) → **360 Workbench** (everything one program touches) → **Quality**
(scan telemetry, corrections, scorecards) → **Architecture** (bounded contexts, service candidates,
risk-ordered roadmap).

> **Example.** Search `CRDPOST` → click it → click a `DYNAMIC_CALL` edge → the drawer shows
> Status `needs_review` (orange pill), Confidence 0.60, and the evidence (source file + line).

Details: confidence + validation status are color-coded everywhere; relationship-type filter presets
(All / Control / Data / DB2); slices show `bounded`/`cached`/truncation badges; explicit empty/loading
states; everything exportable to JSON. *(The dev UI reaches the backend via the Vite `/api` proxy;
the built `dist/` relies on that proxy — FastAPI does not serve static files itself.)*

---

## 6. How to read confidence, validation & coverage (read this before trusting output)

This is the most important section for a *user*.

- **Three labels, fixed meaning:** `confirmed` = MIP saw it directly in the source; `inferred` =
  reasoned from signals; `needs_review` = shaky, unresolved, or AI output that cited nothing.
- **Confidence only ratchets down.** The parser starts optimistic (0.95 full grammar) and every doubt
  lowers it — and below 0.7 the status flips to `needs_review`:

```python
confidence = 0.95 if effective == "local-antlr4-full-grammar" else 0.78
if parser.get("antlr4_error"): confidence = min(confidence, 0.68)
if effective == "fallback-regex": confidence = min(confidence, 0.45)
if any(not row.get("resolved") for row in copy_resolution): confidence = min(confidence, 0.70)
```
*(src/mip_intel/reference_parser.py)*

- **Nothing is dropped to look clean.** Dynamic calls and unresolved targets stay in the graph,
  flagged — so gaps are counted, not hidden.
- **Coverage ≠ proof.** A `not_observed` coverage check means "no evidence in this slice," not "it
  isn't there."
- **AI is a cited proposal, never a fact.** No citations → `needs_review`, confidence capped at 0.4.

**How to act on it:** trust `confirmed` facts; double-check `inferred` ones; treat `needs_review` and
anything < 0.7 as a lead to verify, not a decision input. For modernization specifically: the
service/decomposition output is a starting map — not decision-grade until interface contracts and
dataset-identity facts are added (see the build journey).

---

## 7. Quickstart (run it yourself)

```powershell
# 1. install
python -m pip install -e ".[api,dev]"

# 2. see it instantly on a seeded demo
python -m mip_intel.cli --db data\mip.db init-demo
python -m mip_intel.cli --db data\mip.db roots
python -m mip_intel.cli --db data\mip.db service-candidates

# 3. scan your own estate, then validate
python -m mip_intel.cli --db data\estate.db analyze "F:\path\to\source"
python -m mip_intel.cli --db data\estate.db validate

# 4. explore in the browser (backend + UI)
python -m mip_intel.cli --db data\estate.db serve        # or start_ui.bat
cd frontend && npm install && npm run dev                # opens on :5174, proxies /api -> :8000
```

---

## 8. The build journey (and where it's heading)

MIP grew in phases you can trace in the test files:
- **Phase 1 — scan reliability:** durable runs, progress, telemetry, quarantine.
- **Phase 2 — parser coverage:** DB2 DDL/cursors, IMS DBD/PSB/PCB, VSAM file-control, JCL PROC.
- **Phase 3 — DDD domain architecture:** bounded contexts, service candidates, roadmap.
- **Phase 4 — React UI.**
- **Phase 5 — production readiness:** hard parse timeouts, parser cache, incremental classification,
  WAL tuning.
- **Phase 6 — feedback / performance / quality:** human-correction loop + ground-truth scorecards.
- **Phases 7–10 — deep intelligence:** column-level DB2 lineage, host-variable bindings, CICS
  COMMAREA contracts, file-I/O semantics, business-rule nodes.

**Current direction (specified, in progress):** split parsing into a fast `cobol_ast` **baseline**
(every file) plus a persistent **`mip enrich`** step that runs ANTLR out-of-band and writes deep
facts back by *supersession*. See `PARSER_ARCHITECTURE_REVIEW.md` and `ENRICHMENT_SPEC.md`. Until
interface contracts (CALL USING / LINKAGE), CICS COMMAREA, dataset-identity normalization, and a
bounded copybook-layout model are implemented, **modernization output is marked not decision-grade.**

---

## 9. Verified working (2026-06-23)

Checked on this tree against the seeded demo graph:
- **CLI:** `init-demo`, `stats`, `validate`, `roots`, `clusters`, `domains`, `service-candidates`,
  `roadmap`, `insights`, `search` all run and return correct JSON. `validate` → **all checks
  passed** (every asset/relationship has evidence; confidence in range; status allowed).
- **API:** all 12 sampled FastAPI routes returned HTTP 200 with the expected payload shapes;
  `POST /demo` returned 200.
- **UI contract:** the React client's `/api/*` calls map cleanly to the server routes via the Vite
  proxy; a prebuilt `dist/` is present.
- **Tests:** the suite is green (58 tests).

**Known gaps to be aware of** (consistent with MIP's own honesty rule): ANTLR is still tried first
and is slow on real estates (the enrichment restructure is specified, not built); copybook field
expansion can over-produce field nodes at scale; PostgreSQL is intentionally not implemented; the
built UI relies on the dev proxy (FastAPI doesn't serve static files); a live-browser click-through
was not performed (verification was API-/contract-level).

---

## Glossary
- **Asset** — a node: a program, job, table, file, copybook, transaction, etc.
- **Relationship** — a typed edge between assets (CALLS, READS_TABLE, FLOWS_TO, …).
- **Evidence** — the source file + line + text that justifies a fact.
- **Confidence** — 0.0–1.0; how sure MIP is.
- **Validation status** — `confirmed` (seen), `inferred` (reasoned), `needs_review` (verify it).
- **Root / driver** — an entry-point program (reached, never called).
- **Bounded context** — a graph-derived business area proposed as a service boundary.
- **Coverage report** — per-program account of what the parser did and didn't see.
- **Scorecard** — precision/recall of the extraction vs hand-labeled ground truth.
