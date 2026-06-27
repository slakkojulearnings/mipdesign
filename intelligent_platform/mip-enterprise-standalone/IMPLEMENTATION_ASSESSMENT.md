# Implementation Assessment - Decision-Grade Facts

Date: 2026-06-27
Target: `mip-enterprise-standalone`

## Verdict

The four previously blocking decision-grade facts are now implemented end to end in the standalone app:

- bounded copybook layout
- CALL USING / LINKAGE interface contracts
- CICS COMMAREA contract field modeling
- dataset identity normalization
- runtime observed calls
- external catalog reconciliation

They are extracted during scan, persisted as graph nodes/relationships in SQLite, exposed through graph/coverage/API/UI surfaces, and covered by regression tests.

## Implemented In This Pass

- Added relationship identity discriminators for multi-instance contract/layout/dataset edges.
- Added `COPY_SITE` nodes for each program copy expansion site.
- Added `COPY_SITE_DECLARES_FIELD` and `MATERIALIZES_COPYBOOK_FIELD` so `COPY REPLACING` fields are bounded to the actual program site.
- Added `INTERFACE_CONTRACT` nodes for program entry contracts and call-site contracts.
- Added `CALL_PASSES_FIELD`, `ENTRY_CONTRACT_USES_FIELD`, and `CALL_ARGUMENT_MAPS_TO_LINKAGE`.
- Added CICS COMMAREA modeling with `DEFINES_COMMAREA_CONTRACT` and `COMMAREA_CONTAINS_FIELD`.
- Added `DATASET_IDENTITY` nodes and normalized relationships such as `NORMALIZES_TO_DATASET_IDENTITY`, `READS_DATASET_IDENTITY`, and `WRITES_DATASET_IDENTITY`.
- Added external runtime observations with `runtime_observation` rows and `OBSERVED_CALLS` relationships.
- Added external catalog reconciliation with `catalog_dataset`, `CATALOG_DESCRIBES_DATASET`, and `CATALOG_ALIASES_DATASET`.
- Added CLI/API/UI visibility for external evidence: `import-runtime`, `import-catalog`, and `external-evidence`.
- Bounded large copybook field materialization while keeping small copybooks complete.
- Bounded program data-dictionary graph projection while preserving the full parser payload in node attributes.
- Replaced the scan hot path's row-by-row member/node/edge/evidence writes with batched SQLite writes.
- Tightened architecture decision gates to require the normalized facts, not generic field or dataset edges.
- Added UI graph presets and edge styling for the new facts.
- Added `tests/test_decision_grade_facts.py`.
- Updated the product/technical guide and this assessment.

## Validation Performed

Backend compile:

```powershell
python -m compileall intelligent_platform/mip-enterprise-standalone/src
```

Result: passed.

Focused decision-grade tests:

```powershell
cd intelligent_platform\mip-enterprise-standalone
python -m unittest tests.test_decision_grade_facts -v
```

Result:

```text
Ran 2 tests in 30.136s
OK
```

Focused external-evidence tests:

```powershell
python -m unittest tests.test_external_evidence -v
```

Result:

```text
Ran 3 tests in 93.914s
OK
```

Affected regression batch:

```powershell
python -m unittest `
  intelligent_platform/mip-enterprise-standalone/tests/test_decision_grade_facts.py `
  intelligent_platform/mip-enterprise-standalone/tests/test_production_intelligence_depth.py `
  intelligent_platform/mip-enterprise-standalone/tests/test_phase7_10_complete_intelligence.py `
  intelligent_platform/mip-enterprise-standalone/tests/test_enrichment_pipeline.py
```

Result:

```text
Ran 10 tests in 222.968s
OK
```

Full backend suite:

```powershell
cd intelligent_platform\mip-enterprise-standalone
python -m unittest discover -s tests -v
```

Result:

```text
Ran 66 tests in 494.255s
OK
```

Frontend:

```powershell
cd intelligent_platform\mip-enterprise-standalone\frontend
npm run build
```

Sandboxed build failed on local environment access:

```text
EPERM: operation not permitted, lstat 'C:\Users\srika'
```

Escalated build passed:

```text
vite v5.4.21 building for production...
1581 modules transformed.
built in 47.67s
```

UI runtime smoke:

```powershell
npm run preview -- --host 127.0.0.1 --port 4174
Invoke-WebRequest -UseBasicParsing http://127.0.0.1:4174/
```

Result:

```text
HTML status: 200
root element: present
JS asset /assets/index-C3iQRieJ.js status: 200
```

## Strict Remaining Risks

- ANTLR deep parsing is still dialect-dependent. Failures are persisted and visible, but not automatically solved.
- CALL argument to LINKAGE mapping is positional when both caller and callee are present in the scan. Dynamic targets still require review.
- Dataset identity normalization plus catalog import now handles static/GDG identity and supplied catalog aliases. Full enterprise truth still depends on external metadata quality.
- Runtime-only calls can be imported as `OBSERVED_CALLS`, but scheduler substitutions, generated JCL, and dynamically built program names still require runtime evidence to exist.
- Copybook/data-dictionary graph projection is now bounded for scale. This improves large scans but must still be benchmarked on a representative 200K-file estate.
- React was validated by production build and local HTTP preview smoke. I did not perform an in-app browser click-through in this run.

## Production Position

This is no longer partial for the named static/runtime/catalog evidence gates. The standalone app now persists the core decision-grade evidence needed to start reverse-engineering service interfaces and data ownership.

It is still not a substitute for enterprise runtime/catalog validation. MIP should continue to mark inferred or dynamic facts as `needs_review` rather than presenting them as confirmed.
