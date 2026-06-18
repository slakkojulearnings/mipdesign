---
name: test-equivalence-engineer
description: Builds characterization, golden-fixture, byte-equivalence, numeric-edge, integration, and performance tests for legacy modernization. Use to prove target behavior matches the original system.
license: Apache-2.0
compatibility: Works with skills-aware coding agents; repository workflows assume Python 3.12+, Git, and local file access.
metadata:
  author: mip-project
  version: "1.0"
---


# Test Equivalence Engineer

## Workflow

1. Inventory observable behavior.
2. Create deterministic fixtures and metadata.
3. Run or characterize the original program.
4. Capture raw outputs, mutations, return codes, and diagnostics.
5. Run the target implementation.
6. Compare raw bytes and semantic snapshots.
7. Diagnose differences by field offset, calculation step, ordering, or encoding.
8. Add regression tests before changing target behavior.
9. Publish an equivalence report.

## Required Edge Cases

- empty and single-record input
- zero, negative, maximum, and fractional numbers
- missing lookup/default behavior
- first and final control breaks
- malformed or truncated records
- encoding and padding differences
- overflow and rounding boundaries

## Success Criteria

Results are reproducible and every accepted deviation is explicitly approved.

## Operating Rules

- Follow `CLAUDE.md`.
- Preserve source evidence and confidence.
- Do not modify `mfcode/`.
- Keep generated material under `knowledge/` or `output/`.
- Use the work ledger before processing repository artifacts.
- Report unresolved references and unknowns explicitly.
