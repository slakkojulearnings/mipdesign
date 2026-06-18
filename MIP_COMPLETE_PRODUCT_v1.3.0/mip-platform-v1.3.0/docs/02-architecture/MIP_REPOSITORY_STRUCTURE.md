# MIP Repository Structure

## Source and generated-content boundary

- `mfcode/`: proprietary or local source mount; read-only and ignored by Git
- `src/mip/`: deterministic product implementation
- `data/`: local SQLite databases; ignored
- `output/`: generated reports, graph exports, and portable memory indexes; ignored
- `knowledge/`: reviewed or generated Markdown knowledge pages

## Engineering support

- `.github/`: CI, issue/PR templates, Dependabot, Copilot instructions
- `.claude/`: optional tool-specific agent definitions
- `skills/`: standards-compatible Agent Skills
- `prompts/`: reusable invocations; they do not replace skills
- `templates/`: documentation, ADR, memory, and migration templates
- `scripts/`: setup, validation, and maintenance utilities
- `tests/`: product behavior and regression tests

## Python package boundaries

```text
mip/
├── discovery/      decoding, scanning, classification
├── parsers/        deterministic artifact analyzers
├── persistence/    schema and repository operations
├── graph/          graph construction and traversal
├── services/       orchestration, reports, export, validation
├── api/            FastAPI interface
├── adk/            optional Google ADK adapter
├── utils/          stable IDs and source text helpers
├── models.py       canonical runtime models
└── cli.py          Typer interface
```

Dependencies flow inward through models and repository contracts. Parsers do not call the API or ADK layer. The ADK layer calls deterministic services.
