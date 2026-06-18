---
name: sqlite-engineer
description: Designs and optimizes the local SQLite metadata repository, schema migrations, indexes, constraints, transactions, queries, and PostgreSQL evolution path. Use for persistence changes and query performance work.
license: Apache-2.0
compatibility: Designed for skills-aware coding agents working with the MIP repository.
metadata:
  author: mip-project
  version: "1.0"
---

# SQLite Engineer

## Workflow

1. Start from domain invariants and query patterns.
2. Use foreign keys, uniqueness, parameterized SQL, and explicit indexes.
3. Keep completed analysis runs immutable.
4. Make write operations transactional and failures recoverable.
5. Add schema and repository tests.
6. Measure query performance before adding denormalization.
7. Document the PostgreSQL-compatible logical mapping.

## Constraints

No string-formatted SQL with user input. No destructive migration without backup and rollback. JSON attributes do not replace core relational identity.

## Success Criteria

The database preserves integrity and supports the required local queries predictably.

## Repository Rules

Follow `CLAUDE.md`, protect proprietary source, keep changes surgical, and run the relevant validation commands before completion.
