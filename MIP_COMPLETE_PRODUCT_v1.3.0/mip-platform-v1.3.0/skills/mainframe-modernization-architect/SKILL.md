---
name: mainframe-modernization-architect
description: Designs evidence-driven modernization options, service/API/event candidates, migration waves, and risk controls. Use only after metadata, dependencies, lineage, business rules, and confidence are available.
license: Apache-2.0
compatibility: Works with skills-aware coding agents; repository workflows assume Python 3.12+, Git, and local file access.
metadata:
  author: mip-project
  version: "1.0"
---


# Mainframe Modernization Architect

## Workflow

1. Confirm knowledge coverage and confidence.
2. Identify capability and data boundaries.
3. Evaluate retain, retire, refactor, rehost, replatform, expose, or rebuild options.
4. Preserve high-value operational characteristics.
5. Sequence changes by dependency and risk.
6. Define verification, rollback, observability, and coexistence.
7. Produce options with tradeoffs—not a single unexplained answer.

## Constraints

- Do not recommend microservices solely from graph communities.
- Do not assume cloud migration improves latency or cost.
- Do not recommend rewrite without behavior characterization.
- Separate modernization goals from technology preferences.

## Success Criteria

Recommendations are evidence-linked, risk-aware, testable, and executable in increments.

## Operating Rules

- Follow `CLAUDE.md`.
- Preserve source evidence and confidence.
- Do not modify `mfcode/`.
- Keep generated material under `knowledge/` or `output/`.
- Use the work ledger before processing repository artifacts.
- Report unresolved references and unknowns explicitly.
