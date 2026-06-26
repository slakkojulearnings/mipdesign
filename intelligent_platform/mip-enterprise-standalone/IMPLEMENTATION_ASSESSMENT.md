# Implementation Assessment - Parser Enrichment Milestone

Date: 2026-06-26
Target: `mip-enterprise-standalone`

## Verdict

Implemented the agreed parser/enrichment milestone in the standalone application. The scan path is now baseline-first, ANTLR enrichment is persistent and explicit, parser status is visible in CLI/API/UI, and modernization outputs are marked not decision-grade until the required interface/data ownership gates exist.

This is a real improvement over the previous state. It is not yet the final decision-grade modernization engine.

## Implemented

- `parse_cobol` is baseline-only: COPY/REPLACING preprocessing plus `cobol_ast`.
- `parse_cobol_deep` is the explicit ANTLR deep parser path.
- Relationship identity no longer includes the full attributes dict.
- SQLite schema version is now `2`.
- Added enrichment tables:
  - `enrichment_artifact_cache`
  - `enrichment_member_status`
  - `enrichment_job`
  - `enrichment_fact_source`
- Added `mip enrich`, `mip parse-status`, and `mip enrichment-coverage`.
- Added FastAPI routes:
  - `POST /enrich`
  - `GET /parser/status/{asset}`
  - `GET /enrichment/coverage`
- Added React UI coverage card, `Enrich 25` action, and parser status drawer.
- AST view now prefers persisted deep AST when enrichment has completed.
- Modernization contexts, service candidates, and roadmap items now include `decision_grade`.
- Product/technical guide rewritten to reflect the current behavior.

## Validation Performed

Backend:

```powershell
$env:PYTHONPATH='F:\mip\mip_structure\intelligent_platform\mip-enterprise-standalone\src'
python -m unittest discover -s tests -p 'test_*.py'
```

Result:

```text
Ran 61 tests in 336.605s
OK
```

Frontend:

```powershell
cd frontend
npm install
npm run build
```

Result:

```text
vite build completed
```

CLI smoke:

```powershell
python -m mip_intel.cli --db _tmp_smoke.db analyze _tmp_smoke_estate
python -m mip_intel.cli --db _tmp_smoke.db parse-status CARD001
python -m mip_intel.cli --db _tmp_smoke.db enrich --top-n 1 --timeout 10 --max-workers 1
python -m mip_intel.cli --db _tmp_smoke.db enrichment-coverage
python -m mip_intel.cli --db _tmp_smoke.db validate
```

Result: scan passed, baseline parser reported correctly, deep enrichment materialized one program, enrichment coverage reached 100% for the smoke estate, and validation passed.

## Strict Gaps

- Bounded copybook layout is not fully implemented as separate `CopyExpansionSite` and alias nodes.
- `CALL USING` / `LINKAGE` contract extraction exists only as partial graph evidence and needs a stricter interface model.
- CICS COMMAREA/channel/container contracts need stronger normalized modeling.
- Dataset identity normalization still needs full reconciliation across COBOL FD, JCL DD, VSAM, IMS, and catalog evidence.
- ANTLR success remains dialect-dependent. Failures are persisted and visible, but they are not magically solved.
- React was validated by production build and API/CLI smoke, not by an in-app browser click-through in this session.
- `npm install` reported 2 dependency audit findings. I did not run `npm audit fix --force` because it can introduce breaking changes.

## Production Position

Good enough for fast baseline inventory, persistent parser enrichment, graph exploration, evidence export, and modernization planning with visible caveats.

Not yet good enough to declare Java service boundaries decision-grade without human review and the remaining contract/data-ownership gates.
