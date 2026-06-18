---
name: cobol-to-java-migrator
description: Plans and implements narrowly scoped COBOL-to-Java migrations with preserved semantics. Use after discovery to create migration specs, Java structure, copybook codecs, file abstractions, business logic, GnuCOBOL harnesses, and equivalence-tested target code.
license: Apache-2.0
compatibility: Works with skills-aware coding agents; repository workflows assume Python 3.12+, Git, and local file access.
metadata:
  author: mip-project
  version: "1.0"
---


# COBOL-to-Java Migrator

## Activation Gate

Do not start until the selected source scope has approved documentation, dependencies, record layouts, and executable or characterized behavior.

## Workflow

1. Create a migration specification.
2. Define target location and excluded scope.
3. Build Java models and explicit codecs from copybooks.
4. Build minimal file/data abstractions.
5. Translate business logic preserving operation order.
6. Create an executable original-program harness where possible.
7. Create unit, integration, and equivalence tests.
8. Compare outputs byte-for-byte where interfaces are fixed records.
9. Document approved differences.
10. Update modernization records and ADRs.

## Constraints

- Idiomatic Java does not mean changing behavior.
- Do not use floating point for decimal business calculations.
- Do not trim fixed-width fields unless the specification says so.
- Do not replace sequential/control-break behavior with unordered processing.
- Do not introduce frameworks without a verified need.

## Success Criteria

The target implementation passes behavioral equivalence and documented performance/operability checks.

## Operating Rules

- Follow `CLAUDE.md`.
- Preserve source evidence and confidence.
- Do not modify `mfcode/`.
- Keep generated material under `knowledge/` or `output/`.
- Use the work ledger before processing repository artifacts.
- Report unresolved references and unknowns explicitly.
