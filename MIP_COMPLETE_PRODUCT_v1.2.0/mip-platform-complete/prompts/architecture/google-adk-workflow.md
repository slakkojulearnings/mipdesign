# Purpose

Design an ADK workflow around deterministic MIP services.

# Prompt

Act as a Google ADK architect. Use current official ADK concepts but keep deterministic parsers, persistence, and graph queries as tools. Define agent roles, graph/sequential/parallel workflow, session state, artifacts, memory, human approval, retries, resume behavior, observability, evaluation, security, and deployment. Do not place source parsing logic inside an LLM prompt.

# Required Output

- assumptions
- evidence used
- proposed or completed work
- tests and validation
- unknowns and risks
- next executable step

# Completion Rule

Do not declare completion until the stated acceptance criteria or validation commands pass. Follow `CLAUDE.md` and the relevant skill.
