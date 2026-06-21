# Platform Evaluation Playbook + MIP Consolidated Findings

> A reusable, machine-portable guide for evaluating a **code-intelligence / legacy-understanding /
> evidence-based analysis platform** (a tool that ingests a codebase or estate and produces a
> knowledge graph, insights, and modernization guidance).
>
> - **Part 1** is project-agnostic — copy it to any repo and run it as a checklist.
> - **Part 2** is the worked example: the consolidated recommendations for MIP Enterprise
>   Intelligence across three assessments (what was found, what was fixed, what remains).
>
> Author: Claude (Opus 4.8). Last updated: 2026-06-21.

---

# PART 1 — Reusable Evaluation Framework

## 1. The method (how to run an honest evaluation)

These six rules matter more than any checklist. Most weak evaluations fail here, not on coverage.

1. **Don't trust the demo. Run on a REAL corpus.** Seeded demo fixtures hide the failure modes
   that only appear on messy real input. For mainframe/COBOL, use a public estate
   (e.g. RocketSoftware **BankDemo**). For any tool, find representative real data, not the
   happy-path sample shipped with it.
2. **Establish ground truth first.** Run the test suite. Run the tool end-to-end. Capture
   numbers (time, counts, sizes). You cannot assess what you have not run.
3. **Verify every finding against the actual code.** Plausible ≠ true. In this very project, a
   confidently-reported "high-severity UI contract bug" turned out to be already fixed in the
   code — caught only by re-reading the cited lines. Treat un-verified findings as leads.
4. **Measure; do not assume.** "It should be fast/slow" is worthless. Time it. Count rows.
   Watch memory. One measurement beats ten opinions. (A measurement here proved the bulk parser
   was **1,170× slower** than the alternative — no amount of code-reading would have shown that.)
5. **Separate CLAIMED from DELIVERED.** Read the README/docs, then check each claim in code and
   at runtime. Stale "gaps" lists, aspirational scale numbers, and named-but-stubbed features are
   common and corrosive.
6. **Be balanced and calibrate severity.** Credit what is genuinely good. Don't inflate. A report
   that's all red gets ignored; a report that's all green is useless.

## 2. The ten evaluation dimensions (checklist)

Run each dimension as a pass. For each, the **probing questions** and the **red flags** to watch.

### D1. Correctness & data integrity
- Are writes idempotent on re-run (no double-insert, no silent delete)?
- Are multi-step operations atomic, or can a crash leave half-written / "RUNNING-forever" state?
- Are errors swallowed (`except: pass`) or mislabeled?
- 🚩 Red flags: `INSERT OR REPLACE` on a table with `ON DELETE CASCADE` children; delete-then-rebuild
  in separate transactions; cache keys missing an input that changes the result.

### D2. Domain / extraction fidelity (the parser/analyzer)
- Does it extract correctly on **real** input, or only on the test fixtures?
- What happens on unparseable input — kept+flagged, or silently dropped?
- Is the same fact extracted twice by two code paths (double-counting)?
- 🚩 Red flags: a "full grammar/parser" that silently falls back to a weaker one and reports
  success; extraction that drops comments/edge-syntax; presence-only tests that never assert counts.

### D3. Core-principle adherence (for evidence/AI platforms)
- Is every fact backed by evidence + a confidence + a validation status?
- Is inference **ever** presented as confirmed? Are confidence numbers real or hardcoded theater?
- Does AI/LLM output stay grounded in and cite the underlying data, verified before it's a decision?
- 🚩 Red flags: hardcoded confidences with false precision (0.86, 0.55…); a `validate` gate whose
  checks always pass; "confirmed" facts produced by a regex fallback.

### D4. Architecture & coherence
- Is there a real abstraction seam (e.g. storage swappable), or is it advertised but bypassed?
- Are layers respected, or does the data/SQL leak everywhere?
- Are there dead/speculative seams (dynamic imports of modules that don't exist)?
- 🚩 Red flags: ABCs that services route around; god-modules (thousands of lines, many concerns);
  duplicated schema knowledge in two places; multiple divergent copies of the codebase.

### D5. Claims vs reality (honesty audit)
- Does every doc claim map to working code? Are "production gaps" lists current?
- Are named features (timeouts, resume, parallelism) real, or stubs?
- Is a headline scale number ("handles 200K files") backed by a measurement?
- 🚩 Red flags: docs that *understate* (hide shipped features) or *overstate* (claim unmeasured scale);
  a config flag whose name implies a guarantee the code doesn't provide.

### D6. Persistence & data layer
- Parameterized queries (no SQL injection via string interpolation)?
- Concurrency story (WAL/locking/timeouts) if there are parallel writers?
- Indexes covering the hot query paths? Param-count limits respected (e.g. SQLite 32,766)?
- 🚩 Red flags: no WAL with concurrent writers; per-row commits in a hot loop; identifier
  interpolation into SQL.

### D7. Scale & performance (always empirical)
- Per-unit cost (per file/record) measured on real input × realistic volume = is it feasible?
- Memory: is the whole dataset held at once? Streaming/batching?
- N+1 query loops? Unbounded result materialization?
- Does the graph/state **grow without bound** with input size?
- 🚩 Red flags: O(n) point queries where one `GROUP BY` would do; "parallel" via threads for
  CPU-bound pure-Python work (GIL); node/edge count that explodes per unit of input.

### D8. UI / data utilization
- Is the data that's extracted actually **surfaced**, or computed-then-discarded?
- Are loading/error/empty states handled? Is rendering bounded (no full-graph dump)?
- Is confidence/uncertainty shown honestly to the user?
- 🚩 Red flags: rich parsed fields stored but never rendered; a "lineage" feature whose data is
  only kept as a count; unbounded canvas rendering.

### D9. Tests & verification honesty
- Do tests assert real behavior/correctness, or just exercise the happy path?
- Do they assert **counts and absence**, not only presence?
- Is there a ground-truth precision/recall harness, or circular tests over a seeded fixture?
- Do mocks hide whether the real path works?
- 🚩 Red flags: green suite that never runs the tool on real input; tests that never call the
  product's own `validate`/quality gate; no frontend tests.

### D10. Security & robustness
- Injection (SQL/command/path), arbitrary file read/write via params?
- CORS / auth posture vs the real threat model?
- Resource exhaustion (huge/pathological input, zip-bomb, no timeout)?
- Sensitive-data handling (the tool may ingest credentials/PII)?
- 🚩 Red flags: `allow_origins=["*"]` on a data API reachable beyond localhost; no hard timeout on
  untrusted input; secrets logged.

## 3. Empirical tests to ALWAYS run (don't trust claims)

Adapt the specifics; keep the intent. For a graph/analysis platform:

1. **Run the test suite** — record pass/fail/skip and **wall-clock** (slow tests are a signal).
2. **Scan/ingest a real public corpus**, not the demo. Record total wall-clock and **per-unit time**.
3. **Extrapolate to the claimed scale** — per-unit time × claimed volume. Is it hours? Months?
4. **Run the product's own quality gate** (`validate`/scorecard) on that real run — does it pass?
5. **Audit for duplicates**: `GROUP BY (type, source, target) HAVING COUNT(*)>1` — double-counting?
6. **Audit completeness of evidence**: count facts with no backing evidence row.
7. **Check the "effective engine" distribution**: how often did the good parser actually run vs.
   silently fall back? (A "full parser" that's always falling back is a dead feature.)
8. **Check growth**: node/edge/row count ÷ input units. Does it stay bounded?
9. **Watch peak memory** on the real run.
10. **Diff docs vs behavior**: pick 5 doc claims, verify each in code and at runtime.

## 4. Severity rubric

| Severity | Meaning |
|---|---|
| **Critical** | Wrong facts presented as confirmed; data corruption; crash on normal input; security hole. |
| **High** | Clear principle violation; real bug on plausible input; materially misleading claim. |
| **Medium** | Correctness risk; missing degrade path; scale/maintainability hazard. |
| **Low** | Style/clarity; narrow edge case. |
| **Info** | Neutral note or a genuine strength worth crediting. |

## 5. Anti-patterns common to this class of tool

- **Silent-fallback masking** — the flagship engine fails and a weaker path quietly takes over,
  so everything "works" while capturing little. *Always check the effective-engine distribution.*
- **Demo-fixture overfitting** — tests/dashboards pass because they run on seeded data that has
  properties real input lacks.
- **Confidence theater** — precise-looking confidence numbers that are hardcoded constants.
- **Claims drift** — docs that overstate scale or understate (hide) shipped features.
- **State/graph explosion** — one node per sub-element per container; unbounded at scale.
- **Unsafe defaults** — the slow/uncapped/serial mode is the default; the safe mode is opt-in.
- **God-module & divergent copies** — one file grows to thousands of lines; multiple near-duplicate
  trees appear and rot.
- **Treating the symptom** — adding a timeout/guard around a too-slow core instead of fixing the
  core (e.g. a hard timeout that makes scans *complete* but *empty*).

## 6. Scorecard template (fill one row per dimension)

| Dimension | Score (1–5) | Evidence (file:line / measurement) | Top risk | Recommendation |
|---|---|---|---|---|
| D1 Correctness | | | | |
| D2 Extraction fidelity | | | | |
| D3 Principle adherence | | | | |
| D4 Architecture | | | | |
| D5 Claims vs reality | | | | |
| D6 Persistence | | | | |
| D7 Scale/perf | | | | |
| D8 UI/utilization | | | | |
| D9 Tests | | | | |
| D10 Security | | | | |

Scoring guide: 5 = exemplary; 4 = solid, minor gaps; 3 = works, real gaps; 2 = significant gaps;
1 = not credible. Always attach the **evidence** column — a score without evidence is an opinion.

---

# PART 2 — MIP Enterprise Intelligence: consolidated findings & recommendations

Three assessments of `intelligent_platform/mip-enterprise-intelligence`. Items are tagged
**[FIXED]**, **[OPEN]**, or **[NEW]** as of the post-Codex review (2026-06-21).

## Assessment #1 — Correctness & trust (initial review)

| # | Finding | Sev | Status |
|---|---|---|---|
| 1 | Double-extraction: every CALL/SQL/file fact emitted twice; the duplicate laundered to `confirmed`/1.0 | High | **[FIXED]** regex pass gated on `parser_rel_types` |
| 2 | Target-only assets carry no evidence → `validate` fails on every real scan | High | **[FIXED]** `asset_evidence` map; validate now passes (0/17,578 missing) |
| 3 | `INSERT OR REPLACE` cascade-deletes an asset's relationships | High | **[FIXED]** `ON CONFLICT DO UPDATE` |
| 4 | No WAL/`busy_timeout`; concurrent writers risk "database is locked" | Med | **[FIXED]** WAL + synchronous=NORMAL + busy_timeout |
| 5 | `recompute_summaries` N+1 (2 COUNT/asset), run twice | High | **[FIXED]** `GROUP BY` |
| 6 | Non-atomic recompute → crash leaves empty `RUNNING` run | Med | partially addressed; re-confirm |
| 7 | `parse_timeout` was a soft post-hoc flag, not a real timeout | Med | **[FIXED]** hard process-based timeout |
| 8 | DB2 column parser doesn't strip `--` comments | Med | re-verify |
| 9 | Repository "Postgres parity" seam largely fictional | Med | **[OPEN]** design choice |
| 10 | `api.validate` has checks hardcoded `passed=True` | Low | **[OPEN]** `review_items_are_visible` still always-pass |
| 11 | Docs stale in both directions (over- and under-state) | High | re-verify against current README |

## Assessment #2 — Performance, data utilization, COBOL completeness

| # | Recommendation | Status |
|---|---|---|
| 1 | **Bulk scan should default to the fast hand parser; ANTLR on-demand only** | **[OPEN] — the one ship-blocker** (see below) |
| 2 | Real multi-core parsing (ProcessPool, not GIL-bound threads) | **[FIXED]** `ProcessPoolExecutor` |
| 3 | Stop redundant per-file parsing / double preprocess | **[FIXED]** |
| 4 | Persist `field_flows` (field lineage) instead of discarding | **[FIXED]** real `FLOWS_TO` edges + `data_lineage` |
| 5 | Surface parsed data in the UI (DB2 columns, copy-resolution, dialect, lineage) | **[FIXED]** graph filters + QualityView |
| 6 | Add intra-program control flow (PERFORM/GO TO) | **[FIXED]** `PERFORMS`/`BRANCHES_TO` |
| 7 | Add data-structure semantics (REDEFINES/OCCURS/88-levels) | **[FIXED]** |
| 8 | CALL USING / LINKAGE interface contracts | re-verify / likely partial |
| 9 | Deeper DB2 (cursors/host-vars), CICS (COMMAREA), File-I/O semantics | partially added; re-verify |
| 10 | Structured JCL parser (vs regex) | **[OPEN]** |
| 11 | Add a ground-truth precision/recall harness | **[FIXED]** `scorecards.py` |

## Assessment #3 — Post-Codex (the current state)

**Verdict:** correctness/robustness is now strong (trust-breakers gone, `validate` passes honestly,
lineage/control-flow/data semantics captured, real precision/recall harness, UI surfaces it). **The
core speed/scale problem is unsolved, and deep-extraction made scale worse.**

### [OPEN] Ship-blocker: the bulk scan still parses with pure-Python ANTLR first
Empirical (12 real BankDemo programs):

```
ANTLR-first scan (current):        328s, all 12 timed out → parse-error, 0 program data.
cobol_ast (fast hand parser) only: 0.28s, 21 field_flows captured.  → ~1,170× faster + more data.
```

`parse_cobol` tries pure-Python ANTLR (~57–112s/file) **first** and only falls back to `cobol_ast`
**after** it fails — so a hard timeout kills the slow attempt before the fast one runs ⇒ "fast but
empty" (with timeout) or "complete but months-long" (without). **Fix: run `cobol_ast` first for the
bulk scan; invoke ANTLR on-demand for one program's deep AST. Or move ProLeap to a compiled (Java
sidecar) runtime — the Python ANTLR *runtime* is the bottleneck, not the grammar.**

### [NEW] Field-level graph explosion
12 programs produced **17,578 assets / 19,106 `DECLARES_COPYBOOK_FIELD` edges** (one FIELD node per
copybook field per including program). Unbounded at estate scale. **Fix: model a copybook layout
once and reference it; make field-level depth opt-in; report the field-node count in scan stats.**

### [OPEN] Unsafe defaults
`parse_timeout_seconds=0` (no timeout) and `max_workers=1` (serial). A naive `mip analyze <estate>`
runs the months-long path. **Make bounded + parallel + on-demand-deep the default.**

### [OPEN] Structural
`ingestion.py` is ~5,000 lines (god-module); split along its existing seams. Three near-duplicate
sibling trees exist (`mip-enterprise-standalone`, `-deep-parser`, `-phase1-6`) — **pick one
canonical tree** before they diverge.

## The single highest-leverage next step
Reorder the parser (hand-parser-first for bulk, ANTLR on-demand) and bound field-level node
creation. That converts the platform from "trustworthy but can't ingest a real estate" to matching
its "very large estate" framing — and it's a small, surgical change proven 1,170× on real input.

---

# PART 3 — Universal Inventory & Code Discovery: the complete capture reference

> The master spec for a "discover and capture **everything**" engine over an arbitrary mainframe/
> enterprise estate. Use it two ways: (a) as the **target** when building a discovery engine, and
> (b) as the **completeness rubric** when evaluating one (does it capture each row? if not, is the
> gap recorded or silent?). The governing rule throughout: **capture everything you can, record
> everything you can't, never drop silently.**

## 3.1 The discovery pipeline (six stages, strictly ordered)

```
WALK → IDENTIFY → CLASSIFY → PARSE (degrade ladder) → RELATE → SYNTHESIZE
                                   ↘ keep-and-flag / quarantine ↗
                         (every stage emits evidence + a coverage entry)
```

1. **WALK** — recurse the whole tree; include **extensionless** files and PDS/PDSE members;
   record excluded/skipped dirs as evidence (exclusions are auditable, not silent); sort for
   determinism.
2. **IDENTIFY** — per file: `sha256` (identity/dedup/incremental key), `size_bytes`,
   **binary vs text** (NUL in first 8KB; non-text-byte ratio; size ceiling), and **encoding**
   (utf-8 → EBCDIC codepage → latin-1; record *which won* and cap confidence on a guessed decode).
3. **CLASSIFY** — assign artifact type by **ordered signals**: folder marker → content signal →
   **referenced-member promotion** (an unknown member that another member `COPY`s/`INCLUDE`s is
   promoted). Unmatched-but-readable → `UNKNOWN_TEXT` (kept + flagged, never dropped).
4. **PARSE** — run the **degrade ladder** (§3.5); each rung captures what it can and stamps the
   parser mode + a confidence cap. Failures are quarantined; the scan still completes.
5. **RELATE** — emit typed edges from the parsed facts (calls, I/O, control flow, lineage…).
6. **SYNTHESIZE** — build the cross-artifact graph, resolve dynamic/dangling targets where evidence
   allows, derive roots/impact/clusters, and write a **coverage report** of what was *not* captured.

## 3.2 Complete artifact taxonomy (recognize, incl. extensionless)

| Group | Artifact types |
|---|---|
| **Programs** | COBOL (incl. nested/contained, embedded SQL/CICS/DLI); PL/I (proc/package/`%INCLUDE`); HLASM Assembler (CSECT/DSECT/MACRO); REXX; CLIST; Easytrieve; NATURAL (program/subprogram/map/DDM/LDA-GDA-PDA); IDMS DML; SAS; **USS** shell/Java/C/Python (modern-edge, often present) |
| **Copy/include** | Copybook (no self-header — identity = member name); DCLGEN (dual SQL-contract + structure); PL/I include; Assembler macro/copy; shared cross-language include |
| **Data definition** | SQL DDL (table/index/view/tablespace/db/bufferpool/sequence/trigger/proc/func); IMS DBD & PSB & ACB; IDCAMS VSAM define; MFS; IDMS schema/subschema/IDD |
| **Batch** | JCL job; cataloged/instream PROC; INCLUDE group; instream control-card streams (IDCAMS/SORT/DFSORT/ICETOOL/IEBGENER/IEBCOPY/IEBUPDTE/IKJEFT01-DSN); scheduler defs (Control-M/CA-7/TWS/Zeke/JOBTRAC); GDG base/generation |
| **Online** | CICS program; BMS mapset & symbolic-map copybook; CSD/RDO; MQSC defs; MQ-via-CALL copybooks (CMQ*); COMMAREA/CHANNEL contracts |
| **Governance** | RACF/ACF2/Top-Secret exports; DB2 GRANT/REVOKE + SYSAUTH unloads; data dictionary / element catalog; runbooks/docs |
| **Binaries & listings** *(often missed — see §3.7)* | Load module; object deck/DBRM; **compiler/assembler/binder LISTINGS** + SYSADATA + load-map (the evidence that resolves dynamic CALLs & COPY expansion); link-edit control (SYSLIN INCLUDE/ENTRY/ALIAS) |
| **Config-as-data** | Parameter/PARM members; ISPF tables; control files & VSAM-resident rate/threshold tables (externalized business parameters) |
| **The catch-all** | `UNKNOWN_TEXT` (readable, unmatched — must be reviewed) and `BINARY_ARTIFACT` (inventoried, flagged unparseable) |

> One file can be **multiple artifacts** (a JCL member with instream PROC + SYSIN data; a DCLGEN
> that is both copybook and SQL contract). **Member name ≠ identity** (use PROGRAM-ID/JOB/CSECT/
> mapset/table self-name; flag mismatches).

## 3.3 Entity & relationship catalog (by layer)

**Inventory:** `SourceMember`, `RunManifest`, `PDS/Library`, `MemberFingerprint(sha)`,
`AliasSet`, `ScanIssue`, `FileTelemetry`, `InventoryCache`, `DiscoveryCorrection`.
Edges: `CONTAINS_MEMBER`, `CLASSIFIED_AS`, `PROMOTED_FROM_REFERENCE`, `DUPLICATE_OF`,
`NAME_CONFLICT`, `ALIAS_OF`, `QUARANTINED_AS`, `CORRECTED_BY`, `EXCLUDED_BY_POLICY`.

**Program internals:** `Program`, `Paragraph`, `Section`, `DataItem`, `ConditionName(88)`,
`FileDescriptor(FD)`, `FileControlEntry(SELECT)`, `LinkageContract`, `EntryPoint`.
Edges: `CALLS` (static), `DYNAMIC_CALL`, `DECLARES_INTERFACE(USING/LINKAGE)`, `PERFORMS`,
`FALLS_THROUGH_TO`, `GOES_TO`, `REDEFINES`, `CONTROLS_OCCURS`, `CONDITION_OF`, `USES_COPYBOOK`,
`FLOWS_TO` (field→field), `SORTS_USING`, `CONTAINS_PROGRAM`.

**Relational (DB2):** `Table`,`Column`,`View`,`Index`,`Alias`,`Constraint`,`Tablespace`,
`Database`,`Sequence`,`Trigger`,`StoredProc`,`Function`,`Package`,`Plan`,`Cursor`,`HostVariable`,
`DclgenBinding`. Edges: `READS/WRITES`, `READS_COLUMN/WRITES_COLUMN`, `BINDS_HOSTVAR`,
`DECLARES_CURSOR_ON`, `OPENS/FETCHES/CLOSES`, `JOINS`, `REFERENCES_FK`, `HAS_COLUMN`, `INDEXED_BY`,
`DCLGEN_BINDS`, `CALLS_PROC`, `TRIGGERS`, `BOUND_IN`, `PACKAGE_IN_PLAN`, `DYNAMIC_TARGET`.

**Hierarchical/file (IMS/VSAM):** `IMS_Database(DBD)`,`Segment`,`Field`,`LCHILD`,`XDFLD`,`PSB`,
`PCB`,`SENSEG`,`ACB`,`VSAM_Cluster`,`AIX`,`Path`,`File`,`RecordLayout`,`Dataset`,`GDG_Base`,`MFS`.
Edges: `CONTAINS_IMS_SEGMENT`, `HAS_PARENT_SEGMENT`, `HAS_SEQUENCE_KEY`, `LOGICAL_RELATIONSHIP`,
`HAS_SECONDARY_INDEX`, `PCB_REFERENCES_DATABASE`, `SENSITIVE_TO_SEGMENT`, `PROGRAM_USES_PSB`,
`DLI_READS_SEGMENT/DLI_WRITES_SEGMENT`, `ALTERNATE_INDEX_OF`, `PATH_OVER`, `DDNAME_BOUND_TO_DATASET`,
`HAS_RECORD_LAYOUT`, `GDG_GENERATION_OF`, `REPRO_LINEAGE`.

**Batch (JCL):** `Job`,`Step`,`Proc`,`DD`,`Dataset`,`Symbol`,`JclCondition`,`ReturnCode`,
`ControlCard`,`SchedulerJob`,`LibraryRef`. Edges: `EXECUTES`, `INVOKES_PROC`,
`EXPANDED_FROM_PROC_STEP`, `READS_DATASET/WRITES_DATASET`, `PASSES_DATASET_TO`, `EXECUTES_BEFORE`,
`CONDITION_GUARDS_STEP`, `CONDITION_CHECKS_RETURN_CODE`, `INCLUDES_MEMBER`, `RESOLVES_SYMBOL_FROM`,
`SEARCHES_LIBRARY`, `DSN_RUN_INVOKES_PROGRAM`, `TRIGGERS_JOB`.

**Online (CICS/BMS/MQ):** `Transaction`,`Program`,`Mapset`,`Map`,`Field`,`CommareaContract`,
`Channel`,`Container`,`CicsFile`,`TS_Queue`,`TD_Queue`,`MQ_Queue`,`QueueManager`,`AbendHandler`.
Edges: `ROUTES_TO`, `RETURNS_WITH_TRANSID`, `TRANSFERS_CONTROL_XCTL`, `LINKS_TO`,
`STARTS_TRANSACTION`, `SENDS_MAP/RECEIVES_MAP`, `PASSES_COMMAREA/PASSES_CHANNEL`,
`READS_FILE/WRITES_FILE`, `WRITES_TS_QUEUE/READS_TS_QUEUE`, `TRIGGERS_TRANSACTION`,
`PUTS_MESSAGE/GETS_MESSAGE`, `REPLY_CORRELATES_REQUEST`, `DEFINED_IN_GROUP`.

**Governance:** `SecurityProfile`,`Principal`,`AccessGrant`,`SensitiveDataElement`,`BusinessRule`,
`HardcodedLiteral`,`ComputationFormula`,`ProcessingWindow`,`DataDictionaryElement`,`RegulatoryScope`.
Edges: `PERMITS_ACCESS`, `GRANTS_DB2_PRIVILEGE`, `PROTECTS_RESOURCE`, `RUNS_UNDER_IDENTITY`,
`CHECKS_AUTHORIZATION`, `DECLARES_SENSITIVE_FIELD`, `SENSITIVE_FLOWS_TO`, `DEFINES_BUSINESS_RULE`,
`RULE_USES_FIELD`, `RULE_REFERENCES_LITERAL`, `SCHEDULED_IN_WINDOW`, `DOCUMENTS`.

**Meta (the contract):** `Evidence`, `Run`, `CoverageReport`, `Insight(AI proposal)`,
`DiscoveryCorrection`. Edges: `HAS_EVIDENCE`, `SCOPED_BY`, `DERIVED_FROM`, `RESOLVES_TO`,
`CAPS_CONFIDENCE`, `QUARANTINES`, `CITES`, `REPRODUCED_BY`, `OVERRIDDEN_BY`.

## 3.4 What a master captures per domain (and what naive tools miss)

- **COBOL** — capture: divisions; data geometry (level, PIC, **USAGE COMP/COMP-3/COMP-5**,
  **byte offsets/lengths**, sign, implied-decimal `V`, `SYNC`), `REDEFINES` overlap maps,
  `OCCURS [DEPENDING ON]` + the **controlling field**, `88` condition names (business flags),
  `LINKAGE` (callee contract); paragraphs/sections + `PERFORM`/`GO TO`/`ALTER` control flow;
  `CALL` static-literal vs **dynamic (with constant propagation)** + `USING BY REFERENCE/CONTENT/
  VALUE` interface; `COPY ... REPLACING`; file verbs + OPEN modes + `AT END`/`INVALID KEY`/FILE
  STATUS; embedded SQL/CICS/DLI. *Naive miss:* column-area semantics (cols 1-6/7/73-80),
  continuation lines, dynamic-call targets, OCCURS-DEPENDING offset shifts, comment-vs-commented-out
  code, dialect/free-vs-fixed.
- **JCL** — capture: JOB/EXEC/DD; `DISP` triplet; concatenation; **symbolic + SET + nested-PROC
  resolution**; GDG `(+1/0/-1)`→base; `IF/COND` + **RETURN-CODE flow between steps**; utility control
  cards (IDCAMS/SORT…); `IKJEFT01-DSN`→DB2; the JOB→STEP→PGM→DATASET data-flow graph; scheduler
  triggers. *Naive miss:* unresolved symbolics, ddname≠DSN (and ddname is per-step), instream PROC/
  SYSIN, COND/IF semantics, GDG relativity, control-card sub-languages.
- **DB2/SQL** — capture: full DDL; **DCLGEN/DECLARE→table binding**; static vs **dynamic SQL**;
  cursors (DECLARE/OPEN/FETCH/CLOSE); host-var↔column binding; **column-level CRUD/JOIN lineage**;
  package→plan→program bind; SQLCODE/WHENEVER handling. *Naive miss:* dynamic string-built SQL,
  cursor lifecycle, column-level (not just table-level) lineage, DCLGEN↔column identity, bind graph.
- **IMS/VSAM** — capture: DBD `ACCESS`/segment hierarchy/`FIELD SEQ` keys/logical rels/secondary
  indexes; PSB `PCB`/**`PROCOPT` decoded per letter (G/I/R/D…)**/SENSEG; **positional PCB binding**;
  DL/I function codes (GU/GN/ISRT/REPL/DLET) + SSA segment targets; VSAM type from IDCAMS
  (KSDS/ESDS/RRDS/LDS) + keys + AIX/PATH; FD↔SELECT↔DDNAME↔DSN; **RECFM/LRECL/key-offset**. *Naive
  miss:* DL/I isn't SQL (CALL 'CBLTDLI'), function-code read/write intent, positional PCB binding,
  PROCOPT letters, alternate indexes, GDG normalization, IDCAMS REPRO as data movement.
- **CICS/BMS/MQ** — capture: LINK/XCTL/START/RETURN + **COMMAREA/CHANNEL/CONTAINER data contracts**;
  SEND/RECEIVE MAP; file control; TS/TD queues; HANDLE/EIB; BMS DFHMSD/MDI/MDF; CSD transaction→
  program→file→mapset; MQ open/put/get + **trigger→transaction** correlation; transaction→program→
  map screen-flow. *Naive miss:* pseudo-conversational state via COMMAREA, dynamic program names in
  LINK/XCTL, channel/container vs commarea, MQ-trigger async start, RDO resource wiring.
- **Other langs** — PL/I (`%INCLUDE`, CALL/FETCH, embedded SQL/CICS), Assembler (CSECT/DSECT/macro,
  BALR/SVC), REXX/CLIST (ADDRESS, dataset alloc, EXECIO), Easytrieve, NATURAL/ADABAS (CALLNAT, DDM),
  IDMS (DML/subschema), SAS; plus Endevor/Changeman version metadata. *Naive miss:* the call/include
  graph in each, embedded SQL/CICS inside them, dynamic FETCH/CALLNAT targets.
- **Governance** — capture: security profiles/grants + **runtime identity**; **PII/PCI/PHI/financial
  classification** by name+PIC+usage+table with regulatory scope and *why*; sensitive-data lineage;
  business rules from 88s/EVALUATE/edit-logic/thresholds/formulas; processing windows/SLAs; data
  dictionary; doc/runbook text. *Naive miss:* end-to-end "who can reach table T via job J," sensitive
  lineage across the copybook/DCLGEN seam, externalized (data-resident) business parameters.

## 3.5 The universal capture model (the honesty contract)

- **Evidence envelope on every node and edge:** `source_path`, `line_start/end`, `evidence_text`,
  `extractor` + **parser rung/version**, `discovery_method`, `confidence` (0..1), `validation_status`
  (`confirmed` = directly observed · `inferred` = deterministic/heuristic · `needs_review` =
  unresolved/dynamic/missing-source). Inference is **never** stamped `confirmed`.
- **Degrade ladder** (each rung caps confidence, and the rung used is recorded):
  `full grammar (ANTLR/structured)` → `preprocessor + light hand-parser` → `regex line-parser` →
  `inventory-only`. A higher rung being unavailable/failed is itself a recorded fact.
- **Keep-and-flag, never drop:** unresolved dynamic CALL/EXEC/SQL targets, missing copybooks, parse
  failures, unknown members → kept as `needs_review` with the *reason* and *candidate set*, and
  quarantined in `scan_issue`. Dynamic targets must record the **variable's value provenance**
  (MOVE literal / read from DD / LINKAGE / control table), not just "dynamic."
- **Content-addressed identity:** stable hash of `(run, type, name)` for entities and
  `(type, src, tgt, attrs)` for edges, so re-scans converge (same `sha` → same id) and divergence
  (member changed, classification flipped) is detectable.
- **Coverage report (provable, not assumed):** every cap/limit is a first-class fact —
  truncations (e.g. "field lineage capped at N/program"), `completeness = sampled|complete`, parser
  rung distribution, unresolved-dependency counts, codepage-guess flags. "We captured everything we
  could" must be *demonstrable* from this ledger.
- **AI/LLM enrichment is a proposal:** it must cite the graph and be verified by tests before it is a
  decision; it never overwrites a primary fact.

## 3.6 The hard part — cross-domain seams (where "capture everything" actually breaks)

These are the failures a single-domain parser cannot see; a master engine assigns each a **single
owner**:

1. **Dataset identity normalization** — JCL (DD DSN), IMS/VSAM (IDCAMS cluster), and COBOL (FD/
   SELECT) each mint a different node for the *same physical file*. Resolve GDG relatives, symbolic
   DSNs, aliases, and ddname↔DSN into **one** dataset node, or lineage fragments at every seam.
2. **Dynamic-target resolution** — dynamic CALL/EXEC-PGM/SQL/LINK/CALLNAT can only be resolved with
   evidence from *another* artifact: a control/parameter member, a DD, or a **compiler/link-edit
   listing**. One owner must consume those to turn `needs_review` into `resolved`.
3. **Field identity chain** — `host-variable ↔ DB2 column ↔ DCLGEN ↔ COBOL copybook field ↔ physical
   record byte` is a four-domain chain; PII/impact lineage must traverse it end-to-end (don't stop at
   each domain's boundary). Per-site `COPY ... REPLACING` means the same copybook yields *different*
   fields per program — capture the expansion site, or you create false cross-program equivalence.
4. **RETURN-CODE / ABEND origin** — the program *sets* RC, JCL *tests* it, the scheduler *reacts*.
   Connect program-side RC origin to the step it guards.
5. **Security reachability** — "can identity X reach table T by running job J?" joins RACF/ACF2/TSS +
   DB2 GRANT + JCL `USER=` + CICS transaction auth into one traversable subgraph.
6. **Asynchronous flow** — MQ message → trigger monitor → CICS transaction; TD-queue trigger; IMS
   message → transaction; started task. Emit the async edge or the 360° call graph shows phantom
   disconnected components.
7. **Liveness vs static reachability** — reconcile graph-reachability with *operational* evidence
   (scheduler actually triggers it; DB2 catalog "last used") before calling anything dead code.
8. **Closed-loop reclassification** — when a downstream parser proves an `UNKNOWN_TEXT` member is
   really a copybook/DCLGEN, feed that back as a `DiscoveryCorrection` (not only the COPY-name path).

## 3.7 Completeness gaps most engines miss (design for these explicitly)

- **Compiler/binder LISTINGS, SYSADATA, load maps, link-edit control (SYSLIN)** — the *ground truth*
  that resolves dynamic calls, COPY expansion, INCLUDE/PROC resolution, and cross-module CALL targets
  (CSECT/ENTRY/ALIAS). Most engines never ingest them.
- **DB2 catalog / RUNSTATS / EXPLAIN / package last-used** — operational telemetry that separates
  live from dead with evidence, not just graph reachability.
- **Externalized business parameters in DATA** (ISPF tables, control/rate/threshold files) — rules
  live in data, not only code.
- **Modern edge already in the estate** — USS (HFS/zFS) shell/Java/C/Python, Db2 SQL-PL/JCC stored
  procs, properties/YAML/XML; CICS Web Services (WSDL/WSBIND/PIPELINE), z/OS Connect, IMS Connect,
  CTG, COBOL `XML/JSON PARSE/GENERATE`. These are the seams to the outside world.
- **Test/golden-master assets** (compare JCL, expected-output GDGs, File-AID/Xpediter scripts) —
  dual-run reconciliation presumes they exist; capture them.
- **Codepage breadth** — cp037/cp1047/cp273/cp500/cp930/cp939 + DBCS SOSI; a wrong codepage silently
  corrupts every field/literal/name. Record detected codepage + cap confidence on guesses.
- **Conditional compilation / preprocessor variants** (`>>IF`, `%IF`, assembler `AIF/AGO`) — record
  which variant compiled and that alternates exist (kept-and-flagged).
- **Versions/temporal** (Endevor/Changeman levels) — `PRIOR_VERSION_OF`/`CHANGED_BETWEEN_RUNS` so
  "what changed" and concurrent-version conflicts are representable.
- **Negative/absence facts** — `UNREACHABLE_FROM_ANY_ROOT`, `NO_CALLERS`, `REFERENCES_MISSING_TARGET`,
  `DUPLICATE_DIVERGENT` are themselves high-value evidence for triage.

## 3.8 Capture-coverage scorecard (grade any discovery engine)

| Capability | Captured? | Gap recorded if not? | Confidence honest? |
|---|---|---|---|
| Extensionless / PDS-member classification | | | |
| EBCDIC + codepage breadth (not cp037-only) | | | |
| Binary kept-and-flagged (load/object distinguished) | | | |
| COBOL data geometry (offsets, COMP-3, REDEFINES, OCCURS-DEPENDING) | | | |
| Dynamic CALL/EXEC/SQL kept + value provenance | | | |
| Intra-program control flow (PERFORM/GO TO) | | | |
| Field-level lineage (incl. host-var↔column) | | | |
| DB2 column-level CRUD + cursor lifecycle | | | |
| IMS DL/I function-code read/write intent | | | |
| VSAM type + keys + AIX/PATH; ddname↔DSN↔FD reconciled | | | |
| CICS COMMAREA/channel contracts + screen flow | | | |
| Non-COBOL langs + embedded SQL/CICS within them | | | |
| Batch graph (JOB→STEP→PGM→DATASET) + scheduler triggers | | | |
| Async flow (MQ/TD trigger → transaction) | | | |
| PII/regulatory classification + sensitive lineage | | | |
| Security reachability (identity→job→resource→grant) | | | |
| Compiler/binder listings ingested to resolve dynamics | | | |
| Coverage report (truncations/caps/parser-rung as facts) | | | |
| Evidence + confidence + validation on every node/edge | | | |
| Re-scan convergence + divergence detection | | | |

Score each row 0 (absent) / 1 (captured but silent gaps) / 2 (captured + gaps recorded + honest
confidence). A true "capture everything" engine scores 2 across the board — or names exactly why not.
