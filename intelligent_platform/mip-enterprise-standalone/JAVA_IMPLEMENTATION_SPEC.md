# Java Implementation & Equivalence Spec — grounded rewrite, proven equivalent (build target)

> Target tree: `mip-enterprise-standalone`. The third and final spec in the chain
> (`ENRICHMENT_SPEC` → `REQUIREMENTS_PIPELINE_SPEC` → **this**). It consumes **confirmed, test-backed
> requirements** and produces **Java that is proven to behave like the mainframe.** Same buildable
> style. Status: **NOT implemented.**
> Date: 2026-06-24.

## ⚠️ Governing principle (must be honored in code and UI)
**AI proposes; tests decide.** Generated Java is a *proposal* grounded in confirmed requirements and
graph evidence. It is **never trusted until the same characterization test that defined the
requirement passes against the new code** (dual-run / golden-master). A unit is cutover-eligible only
when proven equivalent.

```
GENERATED            COMPILED            EQUIVALENT              CUTOVER-READY
(grounded in      →  (it builds)      →  (every requirement   →  (equivalent AND the
 confirmed reqs,                          test matches legacy     requirement is
 cited, inferred)                         within tolerance)       decision-grade)
```

## 0. Model in one paragraph
For each service candidate (from `domain_architecture`), MIP maps its COBOL **data + interface
contracts** to Java types, asks a grounded LLM to generate the service from its **confirmed
requirements** (each method citing the requirement it implements), compiles it, and runs the
**characterization tests carried over from `REQUIREMENTS_PIPELINE_SPEC`** against both the legacy
golden master and the Java — cutting over only when behavior matches. Every step is traced
`requirement → Java unit → equivalence result`, so you can prove every business rule was implemented
*and* behaves identically.

## 1. What feeds it
- **Confirmed, test-backed requirements** (`requirement` rows where `decision_grade=true`) — the spec.
- **Data contracts** — copybook layouts / DB2 columns with captured geometry (PIC, COMP-3, REDEFINES,
  OCCURS) → Java types.
- **Interface contracts** — `CALL ... USING` / `LINKAGE` / CICS `COMMAREA` → method signatures & DTOs.
- **Characterization tests** — the `input → expected-legacy-output` cases from the requirements layer.
- **Roadmap order** — `modernization_roadmap` gives the risk-ordered strangler sequence + the existing
  `feedback_loop` quality gates (contract_tests, golden_master_regression, dual_run_reconciliation,
  rollback_signal). Reuse them; do not reinvent.

## 2. Schema additions
```sql
CREATE TABLE IF NOT EXISTS java_unit (
    java_unit_id        TEXT PRIMARY KEY,   -- stable_id(run_id,"java",capability,unit_name)
    run_id              TEXT NOT NULL REFERENCES run_manifest(run_id) ON DELETE CASCADE,
    capability          TEXT NOT NULL,
    service_candidate   TEXT NOT NULL,
    unit_name           TEXT NOT NULL,      -- e.g. CardPostingService / LateFeePolicy
    unit_kind           TEXT NOT NULL,      -- service | domain_logic | dto | repository | facade
    target_path         TEXT,
    state               TEXT NOT NULL,      -- draft | generated | compiled | equivalent | rejected
    source              TEXT NOT NULL DEFAULT 'llm',   -- llm | human-edited
    grounded            INTEGER NOT NULL DEFAULT 0,     -- 1 = every method cites a confirmed requirement
    confidence          REAL NOT NULL,
    validation_status   TEXT NOT NULL,      -- inferred until equivalence-passed
    requirement_ids_json TEXT NOT NULL DEFAULT '[]',
    citations_json      TEXT NOT NULL DEFAULT '[]',
    created_at          TEXT NOT NULL,
    updated_at          TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_java_unit_run ON java_unit(run_id, capability, state);

CREATE TABLE IF NOT EXISTS equivalence_result (
    equivalence_id    TEXT PRIMARY KEY,
    run_id            TEXT NOT NULL REFERENCES run_manifest(run_id) ON DELETE CASCADE,
    java_unit_id      TEXT NOT NULL REFERENCES java_unit(java_unit_id) ON DELETE CASCADE,
    requirement_id    TEXT NOT NULL,
    test_case_id      TEXT NOT NULL,        -- the characterization test from REQUIREMENTS_PIPELINE
    input_json        TEXT NOT NULL,
    legacy_output     TEXT NOT NULL,        -- golden master / mainframe output
    java_output       TEXT NOT NULL,
    match             TEXT NOT NULL,        -- equal | within_tolerance | mismatch
    tolerance         TEXT NOT NULL DEFAULT '',  -- e.g. "decimal scale 2, HALF_UP"
    details_json      TEXT NOT NULL DEFAULT '{}',
    created_at        TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_equivalence_unit ON equivalence_result(run_id, java_unit_id, match);
```

## 3. The pipeline (each step: deliverable + acceptance)
1. **Select** a service candidate in roadmap risk order; gather its `decision_grade` requirements +
   data/interface contracts. *Acceptance:* refuse to generate a unit from requirements that are not
   confirmed + test-backed.
2. **Map contracts** (§5): COBOL data → Java types; COMMAREA/LINKAGE → method signatures/DTOs; DB2 →
   entities/repository. *Acceptance:* every field has an explicit, documented Java type (no silent
   `String` for packed decimals).
3. **Generate** (grounded LLM, §4): produce the Java; each method annotated with the
   `requirement_id` it implements; state→`generated`, `inferred`. *Acceptance:* zero orphan methods,
   zero unimplemented confirmed requirements.
4. **Compile/build**: state→`compiled` on success; failures recorded, never hidden.
5. **Equivalence (the gate, §6)**: run every requirement's characterization test against the Java and
   the legacy golden master; write `equivalence_result`. All match ⇒ state→`equivalent`. *Acceptance:*
   a mismatch keeps state `generated` and records the exact input/legacy/Java delta.
6. **Trace & sequence** (§7,§8): record `requirement → java_unit → equivalence`; cut over per the
   strangler roadmap only when cutover-ready.

## 4. Grounded generation rules
- The LLM is given **only**: the confirmed requirement statements + conditions + fields, the mapped
  data/interface contracts, and citations. It must annotate each method `// implements: <requirement_id>`.
- **No orphan code** (a method with no requirement) and **no unimplemented requirement** (a confirmed
  requirement with no method) — both are coverage failures, surfaced (§8), never silent.
- Generation is a **proposal**: `validation_status='inferred'`, `state='generated'`. It never
  overwrites a `human-edited` unit (track `source`, like `requirement_review`).
- Ungrounded output (a method citing no requirement) sets `grounded=0` and blocks compile→equivalent.

## 5. Data & interface mapping fidelity (where rewrites silently go wrong)
| COBOL | Java | Note |
|---|---|---|
| `PIC 9(n)` / `S9(n)` | `int` / `long` | by digit count |
| `PIC 9(n)V9(m)` **COMP-3** | **`BigDecimal`** (scale m, explicit rounding) | never `double` — penny errors |
| `PIC X(n)` | `String` | trailing-space + EBCDIC collation rules captured |
| level-88 condition name | `enum` / `boolean` | the business flag becomes a typed state |
| `OCCURS` / `OCCURS DEPENDING ON` | `List` / array (+ controlling field) | bounded |
| `REDEFINES` | typed views / sealed union | overlay made explicit, not lost |
| `COMMAREA` / `LINKAGE` | request/response **DTO** | the inter-module contract |
| DB2 table / `DCLGEN` | entity + repository | column-typed |

*Honesty:* decimal scale, `ROUNDED`, sign handling, and EBCDIC vs ASCII collation are **explicit and
tested** (§6), not assumed.

## 6. Equivalence gate (dual-run / golden-master — the proof)
- The **same characterization test** that defined the requirement (`input → expected legacy output`)
  now runs against the Java. `match` ∈ `equal` | `within_tolerance` (a *declared* numeric rounding
  rule) | `mismatch`.
- **Dual-run**: execute legacy (golden master) and Java on identical inputs and diff. A unit is
  `equivalent` only when **all** its requirements' tests match.
- Mandatory edge coverage: COMP-3/rounding (the penny test), boundary values, EBCDIC ordering for
  sorts/comparisons, date-window logic, and the `OTHER`/else branches.
- *Honesty:* if no golden master exists for a requirement, its equivalence is `pending` — never
  silently `equal`.

## 7. Cutover rule (strangler, behind a facade)
```
java_unit.cutover_ready = (state == 'equivalent')
                          AND all(requirement.decision_grade for requirement it implements)
```
Cut over per the `modernization_roadmap` order: expose the service behind a facade, route **one
operation at a time**, dual-run in production with delta monitoring, and honor the roadmap's existing
`rollback_signal`. Until `cutover_ready`, the unit is watermarked *"machine-generated, not yet
behavior-verified — not for production."*

## 8. Traceability & coverage rollup
- Chain: `requirement_id → java_unit_id → equivalence_result → test_case` (and back to
  `BUSINESS_RULE → evidence(file:line)`). Full legacy-to-Java audit trail.
- `mip cutover-status <capability>` rollup: % of confirmed requirements that are
  `implemented → compiled → equivalent → cutover-ready`, plus the **gaps** (confirmed requirement with
  no Java, orphan Java method, generated-but-not-equivalent, equivalence pending for lack of golden
  master). Prove coverage; don't claim it.

## 9. CLI / API surface
```
mip --db DB generate <capability|service> [--out DIR] [--lang java]   # grounded generation
mip --db DB equivalence <capability|java_unit> [--golden DIR]         # run dual-run, record results
mip --db DB cutover-status <capability>                               # the coverage/readiness rollup
mip --db DB generate-export <capability>                              # code + traceability report
```
API: `POST /generate`, `POST /equivalence`, `GET /cutover-status`, `GET /generate/export` — same
`IntelligenceApi` facade.

## 10. Honesty guardrails (consistent with the whole platform)
- Generated code is `candidate`/`inferred` and watermarked until proven equivalent.
- No orphan code, no unimplemented confirmed requirement — both surfaced as coverage gaps.
- Equivalence is required before cutover; numeric/collation/edge fidelity is tested, not assumed.
- Human edits are tracked and never clobbered by re-generation (stable `java_unit_id`).
- AI never decides — it drafts; the tests and the roadmap gates decide.

## 11. Worked example, carried all the way through
> - **Confirmed requirement** `BR-12` (decision_grade): *"When an account is overdue, apply a 5% late
>   fee on the outstanding balance"* — from `CRDPOST-R007`, cited `CRDPOST.cbl:412`; test:
>   `overdue + balance 1000 → fee 50`.
> - **Generate**: `LateFeePolicy.applyLateFee(Account a)` `// implements: CRDPOST-R007/BR-12`;
>   `WS-BALANCE → BigDecimal balance`, rate `0.05`, `RoundingMode.HALF_UP`, scale 2.
> - **Compile** → ok.
> - **Equivalence (dual-run)**: input `{overdue:true, balance:1000.00}` → legacy `50.00`, Java
>   `50.00` → `match=equal`; plus `{overdue:false}` → both `0.00`; plus a `1000.005` rounding case →
>   both `50.00` (the penny test). All match ⇒ `state=equivalent`, `cutover_ready=true`.
> - **Cutover**: route `processCrdpost`'s fee step through `LateFeePolicy` behind the facade,
>   dual-run in production, monitor the delta, then retire the COBOL step.

## 12. Test gate (must pass before production)
| Test | Asserts |
|---|---|
| Confirmed-only input | `generate` refuses requirements that aren't confirmed + test-backed |
| Grounded generation | every generated method cites a `requirement_id`; orphan methods flagged |
| Implementation coverage | a confirmed requirement with no Java unit is reported as a gap, not hidden |
| Type fidelity | COMP-3 fields map to `BigDecimal` with explicit scale/rounding, never `double` |
| Equivalence pass | a matching dual-run sets `state=equivalent`; a mismatch records the delta and stays `generated` |
| Penny test | a rounding edge case matches the legacy golden master to scale |
| Collation/edge | EBCDIC ordering, boundary values, and `OTHER`/else branches are covered |
| Pending honesty | no golden master ⇒ equivalence `pending`, never auto-`equal` |
| Cutover gate | `cutover_ready` only when equivalent AND the requirement is decision_grade |
| Human-edit safety | re-generation does not clobber a `human-edited` unit; `java_unit_id` is stable |
| Traceability | every java_unit resolves requirement → equivalence test → evidence(file:line) |
| Coverage rollup | `cutover-status` counts reconcile and surface every gap |

## 13. Out of scope (track separately)
The choice of code-generation engine, the build toolchain, and the wiring to a running mainframe /
COBOL emulator for live dual-run (this spec assumes golden-master outputs are available from the
requirements layer). It defines the **contract and the proof**, not the runtime plumbing.
```
ENRICHMENT_SPEC  →  REQUIREMENTS_PIPELINE_SPEC  →  JAVA_IMPLEMENTATION_SPEC
 fast+deep facts     confirmed BR/FR (cited)        grounded Java, proven equivalent
```
