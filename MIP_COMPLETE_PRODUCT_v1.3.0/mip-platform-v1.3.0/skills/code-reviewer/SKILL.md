---
name: code-reviewer
description: Performs evidence-based principal-engineer review of MIP code, parser semantics, schema changes, graph direction, tests, security, and scope. Use before merge or when a design appears overly broad or fragile.
license: Apache-2.0
compatibility: Designed for skills-aware coding agents working with the MIP repository.
metadata:
  author: mip-project
  version: "1.0"
---

# Code Reviewer

## Review Order

1. Goal and acceptance criteria
2. Correctness and mainframe semantics
3. Evidence and unknown handling
4. Tests and failure isolation
5. Security and confidential-data protection
6. Simplicity and architectural fit
7. Performance based on measurements
8. Documentation and operability

## Output

Classify findings as blocker, high, medium, low, or suggestion. Cite file and line. Explain consequence and the smallest correction.

## Constraints

Do not rewrite the implementation during review. Do not raise style preferences as blockers when automated standards pass.

## Success Criteria

The author can act on every finding and understand why it matters.

## Repository Rules

Follow `CLAUDE.md`, protect proprietary source, keep changes surgical, and run the relevant validation commands before completion.
