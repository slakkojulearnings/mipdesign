# MIP Canonical File Index

This file identifies the authoritative artifact for each concern. Do not create a competing document; update the canonical file or record an ADR.

| Concern | Canonical file |
|---|---|
| Product overview and quick start | `README.md` |
| Agent behavior | `CLAUDE.md` |
| Cross-agent behavior | `AGENTS.md` |
| GitHub Copilot behavior | `.github/copilot-instructions.md` |
| Project charter | `docs/01-foundation/MIP_PROJECT_CHARTER.md` |
| Manifesto | `docs/01-foundation/MIP_MANIFESTO.md` |
| Product backlog | `docs/01-foundation/MIP_PRODUCT_BACKLOG.md` |
| Reference architecture | `docs/02-architecture/MIP_REFERENCE_ARCHITECTURE.md` |
| Repository structure | `docs/02-architecture/MIP_REPOSITORY_STRUCTURE.md` |
| Domain model | `docs/02-architecture/MIP_DOMAIN_MODEL.md` |
| Metadata model | `docs/02-architecture/MIP_ENTERPRISE_METADATA_MODEL.md` |
| SQLite physical model | `docs/02-architecture/MIP_SQLITE_PHYSICAL_MODEL.md` and `src/mip/persistence/schema.sql` |
| Knowledge graph | `docs/02-architecture/MIP_ENTERPRISE_KNOWLEDGE_GRAPH_MODEL.md` |
| Agent architecture | `docs/02-architecture/MIP_AGENT_ARCHITECTURE.md` |
| Copilot strategy | `docs/02-architecture/MIP_GITHUB_COPILOT_STRATEGY.md` |
| Phase execution | `docs/03-execution/MIP_PHASE_0_TO_4_EXECUTION_PLAN.md` |
| Discovery workflow | `docs/03-execution/MIP_DISCOVERY_AND_DOCUMENTATION_WORKFLOW.md` |
| Engineering playbook | `docs/03-execution/MIP_ENGINEERING_PLAYBOOK.md` |
| Coding standards | `docs/03-execution/MIP_CODING_STANDARDS.md` |
| Testing strategy | `docs/03-execution/MIP_TESTING_STRATEGY.md` |
| Migration workflow | `docs/03-execution/MIP_COBOL_TO_JAVA_MIGRATION_PLAYBOOK.md` |
| Equivalence testing | `docs/03-execution/MIP_TESTING_AND_EQUIVALENCE_STRATEGY.md` |
| Internal knowledge OS | `docs/04-operating-system/MIP_INTERNAL_OS.md` |
| Memory/index model | `docs/04-operating-system/MIP_MEMORY_MODEL.md` |
| Operations | `docs/05-operations/MIP_OPERATIONS_RUNBOOK.md` |
| Security | `docs/05-operations/MIP_SECURITY_MODEL.md` and `SECURITY.md` |
| Observability | `docs/05-operations/MIP_OBSERVABILITY.md` |
| CLI/API | `docs/05-operations/MIP_API_CLI_REFERENCE.md` |
| Product limitations | `docs/05-operations/MIP_PRODUCT_LIMITATIONS.md` |
| Skills | each `skills/<name>/SKILL.md` |
| Reusable task prompts | `prompts/` |
| Release history | `CHANGELOG.md` |

## Status labels

- `CANONICAL`: authoritative and maintained
- `REFERENCE`: useful supporting detail
- `GENERATED`: derived and reproducible
- `ARCHIVED`: superseded and excluded from agent guidance
