# GitHub Copilot Instructions for MIP

You are working on an enterprise legacy understanding and modernization platform.

Follow `CLAUDE.md` as the primary behavioral contract.

## Architecture Sequence

```text
Source → Inventory → Metadata → Relationships → Graph → Reasoning → Modernization
```

Never skip directly from raw source to an unverified modernization answer.

## Engineering Defaults

- Python 3.12+
- Pydantic v2 models
- SQLite for local persistence
- NetworkX `MultiDiGraph` for typed relationships
- Google ADK for agent orchestration
- pytest for tests
- structured logging
- type hints for production code

## Before Generating Code

1. Identify the active specification and skill.
2. State assumptions that affect design.
3. Define verifiable success criteria.
4. Identify required tests.
5. Keep changes minimal.

## Mainframe Analysis Rules

- Files may have no extensions; classify from content and folder evidence.
- Respect fixed columns, continuation rules, copybook replacement, compiler directives, and encodings.
- Distinguish static and dynamic calls.
- Resolve JCL EXEC PGM, PROC expansion, symbolic parameters, DD datasets, and utility behavior.
- Record unresolved references rather than inventing targets.
- Preserve source evidence for every relationship.

## Translation Rules

- Do not translate before behavior has been characterized.
- Preserve record lengths, field offsets, signedness, decimal scale, rounding, overflow, encoding, sort order, and control-break behavior.
- Generate byte-equivalence tests for fixed-record interfaces.
- Keep migrated code under a separate target directory.
