# Purpose

Define or evolve the canonical domain model.

# Prompt

Act as a domain and metadata architect. Model the requested concept as an asset, relationship, evidence item, run state, or non-canonical transient object. Specify identity, attributes, cardinality, relationship direction, confidence, lifecycle, constraints, Pydantic mapping, SQLite mapping, graph mapping, API representation, migration impact, and validation tests. Avoid duplicate meanings and UI-specific fields.

# Required Output

- assumptions
- evidence used
- proposed or completed work
- tests and validation
- unknowns and risks
- next executable step

# Completion Rule

Do not declare completion until the stated acceptance criteria or validation commands pass. Follow `CLAUDE.md` and the relevant skill.
