# MIP Engineering Playbook

## Development loop

1. Select a small backlog item.
2. Define observable behavior and non-goals.
3. Add source fixtures and tests.
4. Implement deterministic behavior.
5. Run formatting, lint, typing, and tests.
6. Validate against representative mainframe samples.
7. Update canonical documentation and prompts/skills only when needed.

## Quality gates

```bash
ruff check src tests
ruff format --check src tests
mypy src/mip
pytest --cov=mip --cov-report=term-missing
```

## Parser rules

- Preserve line numbers.
- Handle extensionless files.
- Never fail an entire run because one source file is malformed.
- Emit unresolved references.
- Add a regression fixture for every parser defect.
- Prefer tokenization/grammar evolution over increasingly fragile global regexes.

## Pull request rules

- one goal per PR
- tests prove the goal
- no unrelated refactoring
- source and generated data remain excluded
- security and rollback implications documented
