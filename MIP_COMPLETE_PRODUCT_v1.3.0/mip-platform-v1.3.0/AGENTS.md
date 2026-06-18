# Agent Instructions

Use `CLAUDE.md` as the repository-wide behavioral contract regardless of the coding agent being used.

## Execution Priority

1. User request
2. Repository safety and governance
3. Active skill
4. Canonical architecture
5. Reusable prompt
6. Existing implementation style

## Required Workflow

- Select the smallest relevant skill.
- Load only the references needed for the task.
- Use `memory/todo.list` to claim repository artifacts.
- Preserve evidence and confidence.
- Verify outputs before declaring completion.
