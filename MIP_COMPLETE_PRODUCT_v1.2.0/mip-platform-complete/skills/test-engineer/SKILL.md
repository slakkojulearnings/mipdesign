---
name: test-engineer
description: Creates behavior-focused tests for classifiers, parsers, persistence, graph traversal, APIs, CLIs, reports, and migration equivalence. Use before implementation and whenever a defect or edge case is discovered.
license: Apache-2.0
compatibility: Designed for skills-aware coding agents working with the MIP repository.
metadata:
  author: mip-project
  version: "1.0"
---

# Test Engineer

## Workflow

1. Convert the goal into observable assertions.
2. Create the smallest license-safe source fixture.
3. Cover happy, boundary, malformed, missing-reference, and regression cases.
4. Test source line preservation and confidence where relevant.
5. Verify database and graph direction, not only counts.
6. Run lint, formatting, typing, unit, integration, and API tests.
7. For migrations, compare bytes and side effects with the original runtime.

## Constraints

Do not test internal implementation details when behavior can be tested. Do not use confidential source in public fixtures.

## Success Criteria

Tests fail for the defect or missing behavior and pass only after the intended solution is implemented.

## Repository Rules

Follow `CLAUDE.md`, protect proprietary source, keep changes surgical, and run the relevant validation commands before completion.
