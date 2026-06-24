# Requirements Pipeline Spec — Reverse-engineered BR + FR with confirmation (build target)

> Target tree: `mip-enterprise-standalone`. Turns MIP's graph facts into **business rules (BR)** and
> **functional rules (FR)** that earn trust in stages and feed the Java rewrite. Same buildable style
> as `ENRICHMENT_SPEC.md`. Status: **NOT implemented** (the BR graph facts exist; the requirements
> layer + confirmation loop do not).
> Date: 2026-06-24.

## ⚠️ Governing principle (must be honored in code and UI)
A requirement is **never** auto-promoted from machine guess to truth. It climbs a ladder, and each
rung is recorded:

```
DERIVED            DRAFTED              CONFIRMED            TEST-BACKED          IMPLEMENTED
(machine, inferred  (cited-LLM prose,   (an SME agrees the   (a characterization (Java written from
 ~0.6, cited to  →  still inferred;  →   meaning; recorded →  test from the    →  the confirmed
 the code)           uncited -> 0.4)      who/when/why)        rule passes on       requirement)
                                                               legacy)
```
- `confirmed` is set **only** by a human review (§5). The LLM (§4) is an assistant, never an author.
- A requirement is **decision-grade only when `state=confirmed` AND `test_status=passed`** (§9).
- Rejected requirements are kept for audit, excluded from the spec/Java input.

## 0. Model in one paragraph
MIP already extracts **BUSINESS_RULE** assets (from IF / EVALUATE / COMPUTE / level-88) and
**functional contracts** (service-candidate operations + owned/read data). This layer assembles those
into `requirement` rows, lets a cited LLM draft readable prose, lets an SME confirm or edit the
meaning, backs each with a characterization test, and tracks coverage end to end — so the confirmed,
tested requirement becomes both the **Java spec** and the **equivalence test** that proves the rewrite.

## 1. What feeds it (already in the graph — no new extraction)
- **BR** ← `BUSINESS_RULE` assets + `DEFINES_BUSINESS_RULE` / `RULE_USES_FIELD` /
  `DEFINES_TRANSFORMATION` edges (produced by `cobol_ast.business_rules()` +
  `ingestion._business_rule_relationships`). Each already carries `condition`, `statement`, `kind`,
  `fields`, and `source_evidence` (file:line), at `inferred`/0.6.
- **FR** ← `domain_architecture` service candidates: `api_candidates` (operations the capability
  performs), `data_contracts` (`owned_write_model` vs `read_dependency`), `event_candidates` — each
  backed by real `CALLS`/`READS_TABLE`/`WRITES_TABLE`/CICS edges with citations.

## 2. Schema additions
```sql
CREATE TABLE IF NOT EXISTS requirement (
    requirement_id    TEXT PRIMARY KEY,   -- stable_id(run_id,"requirement",derived_from)  (stable across re-draft/edit)
    run_id            TEXT NOT NULL REFERENCES run_manifest(run_id) ON DELETE CASCADE,
    kind              TEXT NOT NULL,      -- business_rule | functional_rule
    capability        TEXT NOT NULL,      -- bounded context it belongs to
    title             TEXT NOT NULL,      -- short label, e.g. "Late fee on overdue accounts"
    statement         TEXT NOT NULL,      -- readable BR/FR text (templated, or LLM-drafted, or SME-edited)
    derived_from      TEXT NOT NULL,      -- the rule_id / service-operation / edge id it came from
    rule_fingerprint  TEXT NOT NULL,      -- hash of (program, condition/expr) — for stale detection on re-scan
    state             TEXT NOT NULL,      -- derived | drafted | confirmed | rejected
    test_status       TEXT NOT NULL DEFAULT 'none',  -- none | pending | passed | failed
    source            TEXT NOT NULL,      -- machine | llm | human  (who last set `statement`)
    confidence        REAL NOT NULL,
    validation_status TEXT NOT NULL,      -- inferred (derived/drafted) | needs_review (uncited LLM) | confirmed (SME)
    citations_json    TEXT NOT NULL DEFAULT '[]',   -- [{entity_kind, entity_id}] -> rule/asset/relationship + evidence
    created_at        TEXT NOT NULL,
    updated_at        TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_requirement_run ON requirement(run_id, kind, state);

-- The human verdict (modeled on discovery_correction): auditable, never overwritten.
CREATE TABLE IF NOT EXISTS requirement_review (
    review_id         TEXT PRIMARY KEY,
    requirement_id    TEXT NOT NULL REFERENCES requirement(requirement_id) ON DELETE CASCADE,
    rule_fingerprint  TEXT NOT NULL,      -- so a confirmation survives a re-scan IFF the rule is unchanged
    verdict           TEXT NOT NULL,      -- accepted | edited | rejected
    edited_statement  TEXT,
    reviewer          TEXT NOT NULL,
    reason            TEXT NOT NULL DEFAULT '',
    reviewed_at       TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_requirement_review_req ON requirement_review(requirement_id);
```
**Stale rule:** on re-scan, if a requirement's `rule_fingerprint` is unchanged, its prior
`accepted/edited` review re-applies (stays `confirmed`). If the underlying rule changed, the
requirement reverts to `drafted`/`needs_review` and must be re-confirmed — *if the code changed, the
meaning must be re-verified.*

## 3. The pipeline (each step: deliverable + acceptance)
1. **Assemble** (machine). Build one `requirement` per `BUSINESS_RULE` asset (kind=business_rule)
   and per service-candidate operation/data-contract (kind=functional_rule), copying the templated
   `statement`, `derived_from`, citations, `confidence` 0.6, `validation_status` inferred, state
   `derived`. *Acceptance:* every BUSINESS_RULE asset and every service operation yields exactly one
   requirement with ≥1 citation; re-running is idempotent (stable `requirement_id`).
2. **Draft** (cited LLM, §4). Optionally replace the templated `statement` with readable prose;
   state→`drafted`. *Acceptance:* an uncited LLM response leaves the requirement `needs_review`/≤0.4.
3. **Confirm** (human, §5). SME accepts/edits/rejects; writes a `requirement_review`; accepted/edited
   → state `confirmed`, `validation_status` confirmed, confidence raised to ≤0.9 (not 1.0 until
   test-backed). *Acceptance:* only a review can set `confirmed`; reviewer + reason recorded.
4. **Test-back** (§6). Derive a characterization test from the confirmed rule, run vs legacy
   golden-master; set `test_status`. *Acceptance:* a passing test sets `test_status=passed` and makes
   the requirement decision-grade.
5. **Trace** (§7). Maintain `requirement → derived_from → BUSINESS_RULE/edge → evidence`, and forward
   to the generated Java unit + its test.

## 4. Cited-LLM drafting rules (reuse `llm_insights` pattern)
- Feed the model **only** the rule facts + their evidence; require it to cite the `derived_from`
  rule/asset id.
- **No citation ⇒ `validation_status='needs_review'`, `confidence=min(.,0.4)`** (same guard as
  `EvidenceGroundedInsightService`). The draft is never `confirmed`, never overwrites the machine
  `statement` silently — it is a proposal stored alongside.
- **Offline default:** no endpoint configured ⇒ keep the templated statement; no network call.

## 5. The human confirmation gate (the authoritative one)
- A review surface shows: the candidate requirement, its cited code (file:line), confidence, and
  accept / edit / reject.
- The verdict is written to `requirement_review` (auditable, append-only). `accepted` keeps the text;
  `edited` stores `edited_statement` and copies it onto the requirement (`source='human'`);
  `rejected` sets state `rejected` (retained, excluded from export/Java).
- **This is the only path to `confirmed`.** Mirrors `discovery_correction` — corrections live in the
  DB as data, not code.

## 6. Characterization-test gate (behavioral confirmation — extend `scorecards.py`)
- From a **calculation** rule, the formula gives expected output (`balance 1000 → fee 50`); from a
  **decision** rule, the branch condition gives the expected action. Generate a test case
  (input → expected) citing the rule.
- Run against the **legacy** program's golden-master output where available; set `test_status`
  passed/failed. Same precision/recall ethos as scorecards, applied to behavior.
- *Honesty:* if no golden master exists yet, `test_status='pending'` — never silently `passed`.

## 7. Traceability & coverage rollup
- Chain: `requirement.citations → BUSINESS_RULE/edge → evidence(file:line)`, and forward
  `requirement_id → generated Java unit → its test` (when the Java layer lands).
- `mip requirements-coverage` rollup per capability: counts + % at each rung
  (`derived → drafted → confirmed → test-backed → implemented`) and the **gaps** (rules with no
  requirement, requirements never reviewed, confirmed-but-untested). Show it; don't claim "all
  captured."

## 8. CLI / API surface
```
mip --db DB requirements <capability|program|--all> [--draft] [--limit N]   # assemble (+ optional LLM draft)
mip --db DB requirements-review <requirement_id> --verdict accepted|edited|rejected
                                  --reviewer NAME [--statement "..."] [--reason "..."]
mip --db DB requirements-coverage [--capability X]
mip --db DB requirements-export <capability|--all> [--format md|json]       # the BR+FR spec document
```
API: `GET /requirements`, `POST /requirements/{id}/review`, `GET /requirements/coverage`,
`GET /requirements/export`. All on the same `IntelligenceApi` facade as the existing commands.

## 9. Decision-grade rule (honesty gate)
```
requirement.decision_grade = (state == 'confirmed') AND (test_status == 'passed')
```
Until true, the requirement is a **candidate**: shown with its rung + confidence, excluded from any
"approved requirements" export, and the export header carries: *"Candidate requirements — machine-
derived and not yet SME-confirmed and behavior-verified; not a basis for cutover."*

## 10. Why this closes the loop
The **confirmed + test-backed requirement is simultaneously the Java spec and the equivalence test.**
The same `requirement_id` threads legacy → requirement → Java → verification, so you can prove every
business rule was implemented and behaves identically.

> **Worked example, carried through:**
> - Legacy `CRDPOST.cbl:412`: `IF ACCOUNT-OVERDUE  COMPUTE WS-FEE = WS-BALANCE * 0.05.`
> - **derived** (inferred 0.6): requirement from rule `CRDPOST-R007`, statement "Set WS-FEE to
>   WS-BALANCE * 0.05", cited to `CRDPOST.cbl:412`.
> - **drafted** (LLM, cites R007, needs_review until reviewed): "BR-12: When an account is overdue,
>   apply a 5% late fee on the outstanding balance."
> - **confirmed** (SME accepts; reviewer=jdoe recorded): validation_status=confirmed.
> - **test-backed**: characterization test `overdue + balance 1000 → fee 50` passes on the legacy
>   golden master ⇒ test_status=passed ⇒ decision_grade=true.
> - **implemented**: Java `LateFeePolicy` generated from BR-12; the same test runs dual-run vs the
>   mainframe ⇒ equivalent ⇒ cut over.

## 11. Test gate (must pass before production)
| Test | Asserts |
|---|---|
| Assemble completeness | one requirement per BUSINESS_RULE asset + per service operation, each with ≥1 citation |
| Assemble idempotency | re-run → same `requirement_id`s, no duplicates, existing reviews preserved |
| Uncited LLM downgrade | LLM draft with no citation ⇒ `needs_review`, confidence ≤ 0.4 |
| Confirm gate | only a `requirement_review` sets `confirmed`; reviewer + reason persisted |
| Reject retained | rejected requirement is excluded from export but kept in the DB |
| Stale on change | changed `rule_fingerprint` reverts a confirmed requirement to needs_review |
| Stale survives | unchanged rule keeps its prior confirmation across a re-scan |
| Test gate | calculation/decision rule yields a test; pending until a golden master exists; never auto-passed |
| Decision-grade | requirement is decision_grade only when confirmed AND test passed |
| Traceability | every exported requirement resolves to a real file:line via its citations |
| Coverage rollup | the per-rung counts reconcile (derived = drafted+confirmed+rejected+…); gaps surfaced |

## 12. Out of scope (track separately)
Generating the actual Java implementation (the next spec) and the live dual-run harness against a
running mainframe/emulator. This spec stops at producing **confirmed, test-backed, fully-traceable
requirements** — the input both of those steps consume.
