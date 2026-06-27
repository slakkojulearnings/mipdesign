# MIP — Complete Feature Inventory & Gap Checklist

> Cross-check list of **everything implemented** in `mip-enterprise-standalone`, enumerated from the
> live code (CLI, API, schema, extractors, graph, UI, tests), plus a **Gaps** section to hand to
> Copilot. Date: 2026-06-27.
>
> Legend: **✅ implemented** · **⚠️ implemented, with a known limitation** · **◻ not yet built (gap)**

---

## 1. CLI commands (37) — `python -m mip_intel.cli --db DB <cmd>`
| Command | Does | |
|---|---|---|
| `init-demo` | seed a small demo graph (no scan) | ✅ |
| `analyze` | scan an estate (baseline) → graph | ✅ |
| `stats` | run counts: assets, relationships, issues, telemetry | ✅ |
| `run-status` | run lifecycle/status | ✅ |
| `validate` | evidence/confidence/status gate checks | ✅ |
| `roots` | root-driver portfolio (risk-ranked) | ✅ |
| `clusters` | application/capability clusters | ✅ |
| `domains` | DDD bounded-context candidates | ✅ |
| `service-candidates` | Java service candidates + data contracts | ✅ |
| `roadmap` | risk-ordered modernization work packages | ✅ |
| `search` | search assets | ✅ |
| `nodes` | list selectable nodes by scope | ✅ |
| `node` | single node profile (+ coverage report) | ✅ |
| `edge` | single edge profile + evidence | ✅ |
| `graph-slice` | bounded graph slice (depth/limit/confidence) | ✅ |
| `call-graph` | upstream/downstream/360 call graph | ✅ |
| `dependency-graph` | bounded dependency graph | ✅ |
| `required-files` | reverse-engineering file closure | ✅ |
| `ast-tree` | parsed AST tree for a program | ✅ |
| `coverage` | parser+graph coverage for one node | ✅ |
| `heatmap` | compact matrix cells (type × type) | ✅ |
| `insights` | enterprise graph insights | ✅ |
| `export` | export graph (json / cytoscape / csv) | ✅ |
| `export-bundle` | reverse-engineering bundle (source+evidence) | ✅ |
| `scorecard` | run a ground-truth precision/recall scorecard | ✅ |
| `scorecards` | list persisted scorecard results | ✅ |
| `enrich` | persistent ANTLR deep enrichment (top-n/timeout/workers/priority/changed-only/force) | ⚠️ works; default `--timeout 10` too low for real programs (~75s/file) |
| `enrichment-coverage` | estate-level deep-enrichment coverage | ✅ |
| `parse-status` | baseline + deep parser status for an asset | ✅ |
| `corrections` / `correction-add` | list / add human discovery corrections | ✅ |
| `performance` | scan telemetry + slow-file report | ✅ |
| `import-catalog` | load external DB2/catalog dataset metadata | ✅ |
| `import-runtime` | load external runtime observations (liveness) | ✅ |
| `external-evidence` | show external/operational evidence | ✅ |
| `serve` | start the FastAPI server | ✅ |

## 2. HTTP API routes (35) — `create_fastapi_app`
GET: `/stats` `/runs/status` `/runs/{id}/status` `/validate` `/roots` `/clusters`
`/architecture/contexts` `/architecture/services` `/architecture/roadmap` `/search` `/nodes`
`/nodes/{id}` `/edges/{id}` `/coverage/{asset}` `/parser/status/{asset}` `/graph/slice` `/graphs/call`
`/graphs/dependencies` `/reverse/files` `/ast` `/heatmap` `/insights` `/export` `/performance`
`/corrections` `/scorecards` `/enrichment/coverage` `/external/evidence`
POST: `/demo` `/analyze` `/enrich` `/corrections` `/scorecards/run` `/external/catalog`
`/external/runtime`  — all ✅. CLI and API share one `IntelligenceApi` facade (cannot drift).

## 3. Persistence — SQLite tables (27)
`schema_version` `run_manifest` `source_member` `asset` `relationship` `evidence` `root_summary`
`app_cluster` `node_degree` `graph_slice_cache` `parser_result_cache` `insight` `validation_result`
`scan_progress` `scan_issue` `scan_phase_telemetry` `scan_file_telemetry` `file_inventory_cache`
`discovery_correction` `scorecard_result` `enrichment_artifact_cache` `enrichment_member_status`
`enrichment_job` `enrichment_fact_source` `runtime_observation` `catalog_dataset` — all ✅.
Engine: WAL + `synchronous=NORMAL` + `busy_timeout` ✅; idempotent `ON CONFLICT` upserts ✅;
content-addressed `stable_id` ✅; `origin`/`enriched_by_member` provenance columns ✅.

## 4. Inventory & classification ✅
- Recursive walk incl. **extensionless** files; excluded-dir tracking.
- Classification ladder: **folder signal → content signal → referenced-member promotion → UNKNOWN_TEXT**.
- Artifact types recognized: COBOL, COPYBOOK, JCL, PROC, DCLGEN, SQL_DDL, BMS_MAP, CSD, IMS, MQ, PLI,
  ASSEMBLER, SCHEDULER, plus BINARY / UNKNOWN_TEXT.
- Encoding detection (utf-8 → cp037 EBCDIC → latin-1); binary detection (NUL/non-printable ratio/size).
- `file_inventory_cache` incremental re-scan ✅; `scan_issue` quarantine ✅; `run_manifest` provenance ✅;
  per-file/per-phase telemetry ✅.

## 5. Parsing ✅ (two-tier)
- **Baseline** (`parse_cobol`): fast hand-written `cobol_ast` + COPY/REPLACING preprocessor; **no ANTLR
  on the scan path**. Captures program-id, divisions, paragraphs, data items (PIC/level/88/COMP-3/
  REDEFINES/OCCURS/usage/value), CALLs (static + dynamic via constant propagation), COPY, EXEC SQL,
  EXEC CICS, field flows.
- **Deep** (`parse_cobol_deep` / `enrich`): ANTLR full COBOL-85 grammar, two-stage SLL, run out-of-band.
  ⚠️ ~75s/file on real programs (pure-Python ANTLR) → prioritized/incremental tier, not whole-estate.
- Confidence capped per parser mode; fallback to regex if parser missing; parser-result cache.

## 6. Extraction — 32 relationship builders (grouped) ✅
- **COBOL core:** `_cobol_relationships`, `_procedure_structure_relationships`, `_control_flow_relationships`
- **Calls/interface:** `_interface_contract_relationships`, `_call_argument_mapping_relationships`
- **Copybook/fields:** `_data_dictionary_relationships`, `_field_flow_relationships`, `_cross_member_relationships`
- **DB2:** `_sql_relationships`, `_embedded_sql_relationships`, `_db2_statement_relationships`,
  `_db2_cursor_relationships`, `_db2_dml_relationships`, `_db2_include_relationships`,
  `_db2_package_relationships`, `_db2_infrastructure_relationships`
- **IMS:** `_ims_relationships`
- **VSAM/files:** `_vsam_file_control_relationships`, `_file_io_semantic_relationships`,
  `_file_record_layout_relationships`, `_sort_merge_relationships`
- **CICS:** `_cics_contract_relationships`, `_csd_relationships`
- **JCL/batch:** `_jcl_relationships`, `_proc_expansion_relationships`,
  `_jcl_condition_reference_relationships`, `_scheduler_relationships`
- **Datasets:** `_with_dataset_identity_relationships` (normalizes DD/VSAM/FD → one identity)
- **Business logic:** `_business_rule_relationships`
- **Other langs:** `_pli_relationships`, `_assembler_relationships`
- Dedup gate (`_append_found`) + regex fallback gated on parser output (no double-count) ✅.

## 7. Relationship (edge) vocabulary ✅ — what it captures
- **Control/call:** CALLS, DYNAMIC_CALL, EXECUTES, INVOKES_PROC, STARTS_PROGRAM, STARTS_TRANSACTION,
  TRIGGERS, PERFORMS, BRANCHES_TO, CONTAINS_PARAGRAPH/SECTION, SECTION_CONTAINS_PARAGRAPH,
  CONTAINS_STATEMENT, CONTAINS_STEP, EXECUTES_BEFORE
- **Interface contracts:** DECLARES_CALL_CONTRACT, CALL_CONTRACT_TARGETS, CALL_PASSES_FIELD,
  CALL_ARGUMENT_MAPS_TO_LINKAGE, DECLARES_ENTRY_CONTRACT, ENTRY_CONTRACT_USES_FIELD
- **Copybook/fields:** USES_COPYBOOK, DECLARES_COPYBOOK_FIELD, DECLARES_FIELD, RECORD_DECLARES_FIELD,
  FIELD_DERIVED_FROM_COPYBOOK, USES_COPYBOOK_FIELD, HAS_COPY_SITE, COPY_SITE_DECLARES_FIELD,
  COPY_SITE_EXPANDS_COPYBOOK, MATERIALIZES_COPYBOOK_FIELD, FLOWS_TO (field lineage)
- **DB2:** DEFINES_TABLE, INDEXES_TABLE, DEFINES_DB2_DATABASE/TABLESPACE/BUFFERPOOL/LOCATION/PACKAGE/PLAN,
  DECLARES_TABLE, DCLGEN_DECLARES_TABLE, USES_DCLGEN, DEFINES_DB2_CURSOR, DECLARE_CURSOR,
  OPENS/FETCHES/CLOSES_DB2_CURSOR, CURSOR_READS_TABLE/READS_COLUMN/FILTERS_BY_COLUMN/JOINS_ON_COLUMN,
  STATEMENT_READS_TABLE/WRITES_TABLE/READS_COLUMN/WRITES_COLUMN/FILTERS_BY_COLUMN/JOINS_ON_COLUMN,
  STATEMENT_INPUTS_FROM_HOST_VARIABLE/OUTPUTS_TO_HOST_VARIABLE, HOST_VARIABLE_BINDS_COLUMN,
  USES_DB2_PACKAGE, READS_TABLE, WRITES_TABLE
- **IMS:** DEFINES_IMS_DATABASE/PSB/FIELD, CONTAINS_IMS_SEGMENT, USES_IMS_DATABASE/SEGMENT
- **Files/VSAM:** DEFINES_FILE, USES_FILE, READS_FILE, WRITES_FILE, USES_DATASET, READS/WRITES_DATASET,
  DEFINES_FILE_IO, HAS_RECORD_LAYOUT, DEFINES_SORT_MERGE, READS/WRITES_QUEUE, USES_QUEUE, USES_MAP
- **Dataset identity:** NORMALIZES_TO_DATASET_IDENTITY, BINDS_DATASET, BINDS_DATASET_IDENTITY,
  USES/READS/WRITES_DATASET_IDENTITY, CATALOG_ALIASES_DATASET
- **CICS:** DEFINES_CICS_CONTRACT, DEFINES_COMMAREA_CONTRACT, COMMAREA_CONTAINS_FIELD, CONTRACT_USES_FIELD,
  HANDLES_CICS_CONDITION, DEFINES_CONDITION
- **JCL:** DECLARES_DD, CONDITION_CHECKS_RETURN_CODE, CONDITION_REFERENCES_STEP, CONTROLS_STEP,
  EXPANDS_TO_STEP, EXPANDED_FROM_PROC_STEP
- **Business logic:** DEFINES_BUSINESS_RULE, RULE_USES_FIELD, DEFINES_TRANSFORMATION,
  TRANSFORMATION_INPUT_FIELD/OUTPUT_FIELD
- **Assembler/PLI:** DEFINES_ASSEMBLER_DSECT, (PL/I call/include edges)

## 8. Asset (node) types ✅
PROGRAM, JOB, TRANSACTION, TABLE, FILE, DATASET, COPYBOOK, MAP, MQ_QUEUE, UNRESOLVED, BINARY_ARTIFACT,
UNKNOWN_ARTIFACT; DB2_DATABASE/TABLESPACE/BUFFERPOOL/LOCATION/PACKAGE/PLAN/COLUMN/CURSOR/STATEMENT,
HOST_VARIABLE; IMS_DATABASE/SEGMENT/FIELD/PSB; CICS_CONTRACT/CICS_CONDITION/CSD_RESOURCE/CICS_RESOURCE;
PARAGRAPH, SECTION, STATEMENT, JOB_STEP, PROC_STEP, JCL_DD, JCL_CONDITION, RETURN_CODE;
COPYBOOK_FIELD, COPY_SITE, FIELD, INTERFACE_CONTRACT, BUSINESS_RULE, TRANSFORMATION,
FILE_IO_OPERATION, FILE_RECORD, SORT_MERGE_OPERATION, DATASET_IDENTITY.

## 9. Knowledge graph & navigation ✅ (`graph_service`)
`search` (search-first) · `root_portfolio` · `application_clusters` (union-find + folder affinity) ·
`graph_slice` (bounded BFS, depth/limit/confidence, truncated flag, cached) · `call_graph`
(up/down/360) · `dependency_graph` · `required_files` (closure + minimal context) · `node_profile`
(+ coverage_report) · `edge_profile` · `heatmap` (type×type matrix) · `ast_tree` ·
`recompute_summaries` (GROUP-BY degrees, roots, clusters). Bounded by design (no full-graph render).

## 10. Reasoning → modernization ✅ (`domain_architecture`, `capability_naming`)
`bounded_contexts` · `service_candidates` (Java service + API + data contracts + events) ·
`modernization_roadmap` (risk/confidence-ordered strangler sequence + quality gates + rollback signal).
Confidence downgraded on sampled membership; citations on every proposal. ⚠️ capability **naming**
still uses a hardcoded card-domain ontology (`CARD_PATTERNS`) → generic on non-card estates.

## 11. Insights, quality, scorecards, validation ✅
- Deterministic insights (INVENTORY_SUMMARY, ROOT_SUMMARY, INGESTION_GAPS) with citations.
- LLM insights (`llm_insights`): grounded, cited, **auto-downgraded to needs_review if uncited**;
  offline by default.
- `scorecards`: precision/recall vs ground-truth (expected vs forbidden members/nodes/edges).
- `validate`: evidence-present, confidence-in-range, status-allowed, line-ranges-valid (a gate).
- `performance`: phase/file telemetry + slow-file report.
- Decision-grade fact tagging (tested in `test_decision_grade_facts`).

## 12. Deep enrichment pipeline ✅ (`enrichment.py`)
Baseline-first split (`parse_cobol` vs `parse_cobol_deep`) · two-layer ledger (artifact cache +
run/member status) · enrichment job history · fact-source provenance · **idempotent purge-then-upsert
supersession** (attribute-independent `relationship_id` + per-type discriminator) · subprocess-per-file
**terminable timeout** · priority (roots/degree/changed) + top-N + changed-only + force · coverage
rollup. ⚠️ default timeout too low; ⚠️ supersede-baseline path correct in code but not yet exercised
end-to-end (deep parses time out at 10s).

## 13. External / operational evidence ✅ (new)
`import-catalog` (DB2/catalog dataset metadata → `catalog_dataset`, dataset-identity aliasing) ·
`import-runtime` (runtime observations → `runtime_observation`, e.g. liveness/usage) ·
`external-evidence` / `/external/*` API. This reconciles **static reachability with operational
reality** (which programs/datasets are actually live) — tested in `test_external_evidence`.

## 14. Human-in-the-loop feedback ✅
`discovery_correction` (override type/name/status, global or per-run, auditable) via
`correction-add` / `/corrections`. Reclassification + confidence re-derivation honored.

## 15. Evidence & honesty model ✅
Every asset/relationship carries source evidence (file:line) + confidence (0..1) + validation status
(confirmed | inferred | needs_review). Inference never shown as confirmed; dynamic/unresolved kept &
flagged; coverage reports say "not_observed ≠ absent"; parser mode caps confidence.

## 16. React UI — views & components ✅
Views: **Dashboard** (stats, validation, enrichment + external-evidence coverage, roots, clusters) ·
**Graph Explorer** (bounded slice, relationship-type presets, depth/limit/confidence/direction) ·
**Matrix** (heatmap presets — programs→tables, cursors→tables, rules→fields, DDs→datasets,
datasets→identity, calls→fields, jobs→programs…) · **Engineering Workbench** (call/dependency
canvas) · **Required Files** · **AST Tree** · **Architecture** (contexts/services/roadmap) ·
**Quality** (performance, corrections, scorecards, validation) · **Search** · **Detail Drawer**
(evidence + confidence + parser status + coverage report) · **Insights** rail · **Export Controls**.
Node-scope filters: roots / programs / normal_programs / jobs / tables / copybooks.

## 17. Tests ✅ (suite green, 61 tests)
contracts_and_guardrails · decision_grade_facts · enrichment_pipeline · enterprise_deep_parser_models ·
external_evidence · graph_strategy · ingestion_insights · local_antlr_parser · phase1 scan reliability ·
phase2 parser coverage (DB2/IMS/VSAM/JCL) · phase3 domain architecture · phase5 production readiness ·
phase6 feedback/performance/quality · phase7-10 complete intelligence · production_intelligence_depth ·
production_parser_hardening · reverse_engineering_graphs.

---

## 18. GAPS — not yet implemented (the build list for Copilot) ◻
These are the items from the spec chain / assessments that are **not** in the code:
1. **Requirements pipeline (BR/FR confirmation)** ◻ — no `requirement` / `requirement_review` tables,
   no `mip requirements` / `requirements-review` / `requirements-export`. *(Business rules are
   captured as graph facts ✅, but the SME-confirmation loop + cited BR/FR document are not.)*
   → build per `REQUIREMENTS_PIPELINE_SPEC.md`.
2. **Java/Python generation + equivalence** ◻ — no `java_unit` / `equivalence_result` tables, no
   `generate` / `equivalence` / `cutover-status` commands; no dual-run proof.
   → build per `JAVA_IMPLEMENTATION_SPEC.md`.
3. **Ontology-based capability naming** ◻ — naming is hardcoded `CARD_PATTERNS`; no
   `capability_ontology` / `glossary_term` / `capability_proposal` / `journey` tables, no
   `capabilities` / `journeys` / `ontology-load` / `glossary-load` commands.
   → build per `CAPABILITY_ONTOLOGY_SPEC.md`.
4. **Customer journeys as a native feature** ◻ — only exists as the external `journey-discovery/`
   scripts + Copilot prompts; not persisted/served by the app.
5. **3D "living map" UI** ◻ — only the standalone POC (`demo/mip_living_map.html`); not wired to the
   live graph or in the React app.
6. **Round-trip / backtrack diagnosis UI** ◻ — the citation links exist; reverse-traversal
   "target issue → COBOL cause" navigation + write-back loop is not built.

## 19. Known limitations on implemented features ⚠️ (worth fixing, not missing)
- **Baseline scan slow + copybook-field explosion** — ~294s and ~35k relationships for 6 programs +
  83 copybooks; `COPY_SITE`/per-site model was *added on top of*, not *bounding*, expansion. Fix:
  expand only used fields + batch DB writes.
- **`enrich --timeout 10` default too low** — real programs deep-parse in ~75s and time out (so they
  fail). Raise to ~120s; deep tier is prioritized/partial by nature.
- **Capability names generic off-card** — `CARD_PATTERNS` is card-specific (see gap #3).
- **Postgres** — `storage.create_repository` raises `NotImplementedError` (SQLite only).
- **UI served via Vite proxy** — FastAPI doesn't serve the built `dist/`; production needs a static
  mount or reverse proxy.

---
**Bottom line:** the *understand-the-system* engine is broad and deep and well-tested (✅ sections
1–17). The remaining build is the *rebuild-and-prove* half (gaps 1–3) plus the experience features
(gaps 4–6) and the two scale fixes (§19). Hand gaps 1–3 to Copilot using the matching spec files in
the repo root.
