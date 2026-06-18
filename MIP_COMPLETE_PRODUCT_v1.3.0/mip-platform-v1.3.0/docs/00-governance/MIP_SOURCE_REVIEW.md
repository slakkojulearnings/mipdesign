# External Source Review and Adoption Decisions

## Agent Skills Specification

Adopted:

- Each skill is a directory with a required uppercase `SKILL.md`.
- YAML frontmatter includes `name` and a task-triggering `description`.
- Main instructions stay focused.
- Detailed material moves to `references/`.
- Deterministic helpers move to `scripts/`.
- Templates and static formats move to `assets/`.
- Skills use progressive disclosure and relative references.

Not adopted:

- Tool-specific assumptions that reduce portability.
- Deep chains of references.
- Large monolithic skill files.

## Public Mainframe Modernization Example

Adopted patterns:

- Repository-level operating instructions.
- Specialized documentation and diagram roles.
- Artifact catalog translating cryptic names.
- Pipe-delimited relationship index.
- Todo ledger to avoid duplicate processing.
- Program, copybook, JCL, file, and workflow extraction templates.
- Daily batch flow documentation.
- GnuCOBOL-compatible characterization testing.
- Fixed-length input/output verification.
- Separate migrated-code directory.

Excluded:

- Vendor-specific dataset names, credentials, infrastructure commands, product branding, and environment-specific conventions.
- Any assumption that one demonstration application's naming rules apply to another repository.
- Automatic business-name assignment without evidence.

## Coding-Agent Behavioral Guidance

Adopted:

- Think before coding.
- Simplicity first.
- Surgical changes.
- Goal-driven execution.
- Responsibility for completing in-scope work.
- Verification before completion.

MIP extension:

- Evidence before inference.
- Deterministic parsing before LLM reasoning.
- Work-item claiming and content-hash idempotency.
- Mainframe semantic equivalence gates.

## Three-Layer Internal OS

Adopted:

1. Raw sources: immutable source and ingested references.
2. Knowledge layer: generated Markdown and diagrams.
3. Schema and operating layer: agent instructions, skills, indexes, templates, and governance.

This separation prevents generated interpretation from overwriting source truth.
