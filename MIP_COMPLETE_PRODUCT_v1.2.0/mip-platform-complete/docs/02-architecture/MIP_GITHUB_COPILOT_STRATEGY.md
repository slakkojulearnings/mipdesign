# MIP GitHub Copilot Strategy

## Operating hierarchy

1. User goal and acceptance criteria
2. `CLAUDE.md`
3. `.github/copilot-instructions.md`
4. Active Agent Skill
5. Canonical architecture document
6. Focused prompt
7. Existing implementation style

## Recommended Copilot sequence

```text
Understand → Specify → Design → Test → Implement → Review → Validate → Document
```

Use repository context deliberately:

- attach the active skill
- attach one canonical architecture file
- attach the smallest implementation scope
- attach failing tests or sample source
- avoid sending an entire proprietary repository to a remote model unless organizational policy explicitly permits it

## High-value Copilot uses

- generate tests from explicit semantics
- critique parser edge cases
- create small repository adapters
- explain existing code using evidence
- implement approved specifications
- review diffs against acceptance criteria

## Prohibited use

- blind whole-estate translation
- invented business names presented as facts
- untested regex-only parser claims
- committing confidential code to a public repository
- accepting generated code without executing validation
