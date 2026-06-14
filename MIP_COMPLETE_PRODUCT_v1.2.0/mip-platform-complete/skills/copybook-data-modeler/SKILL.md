---
name: copybook-data-modeler
description: Parses and documents COBOL copybooks and fixed-record layouts. Use for PIC clauses, hierarchy, level 88 values, REDEFINES, OCCURS, OCCURS DEPENDING ON, byte offsets, record lengths, codecs, and Java data-model planning.
license: Apache-2.0
compatibility: Works with skills-aware coding agents; repository workflows assume Python 3.12+, Git, and local file access.
metadata:
  author: mip-project
  version: "1.0"
---


# Copybook Data Modeler

## Workflow

1. Parse level hierarchy and parent-child relationships.
2. Interpret PIC, USAGE, SIGN, SYNCHRONIZED, VALUE, and JUSTIFIED clauses.
3. Resolve REDEFINES and overlapping storage.
4. Resolve OCCURS and OCCURS DEPENDING ON.
5. Calculate byte offsets and lengths for each supported representation.
6. Record 88-level condition names as business-value constraints.
7. Identify nested COPY dependencies.
8. Generate a data dictionary and a codec-oriented Java mapping.
9. Validate total record length against declarations or sample records.

## Java Mapping Rules

- Separate logical values from physical codecs.
- Use explicit fixed-width codecs.
- Use `BigDecimal` for decimal business values.
- Do not discard leading zeros or spaces.
- Do not represent REDEFINES as unrelated duplicated fields without documenting overlap.

## Success Criteria

Every field has hierarchy, physical representation, byte range, logical interpretation, and confidence.

## Operating Rules

- Follow `CLAUDE.md`.
- Preserve source evidence and confidence.
- Do not modify `mfcode/`.
- Keep generated material under `knowledge/` or `output/`.
- Use the work ledger before processing repository artifacts.
- Report unresolved references and unknowns explicitly.
