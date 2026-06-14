# Purpose

Design or review the end-to-end MIP architecture.

# Prompt

Act as a principal platform architect. Read `CLAUDE.md`, the project charter, reference architecture, domain model, and current source tree. Design only the architecture required for the stated goal. Preserve the sequence Source → Inventory → Metadata → Relationships → Graph → Reasoning → Modernization. Identify components, package boundaries, data flow, trust boundaries, failure isolation, deployment assumptions, decisions, rejected alternatives, and verifiable acceptance criteria. Do not introduce distributed infrastructure without measured need.

# Required Output

- assumptions
- evidence used
- proposed or completed work
- tests and validation
- unknowns and risks
- next executable step

# Completion Rule

Do not declare completion until the stated acceptance criteria or validation commands pass. Follow `CLAUDE.md` and the relevant skill.
