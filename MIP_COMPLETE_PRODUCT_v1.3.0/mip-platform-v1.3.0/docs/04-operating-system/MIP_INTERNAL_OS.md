# MIP Internal OS

## Three Layers

### Layer 1: Raw Sources

- `mfcode/`
- `resources/raw/`
- original attachments and transcripts

Raw sources are immutable.

### Layer 2: Knowledge

- `knowledge/`
- generated summaries
- artifact pages
- workflow pages
- diagrams
- approved capability pages

Knowledge is regenerable and evidence-linked.

### Layer 3: Schema and Workflows

- `CLAUDE.md`
- `.github/copilot-instructions.md`
- `skills/`
- `prompts/`
- `templates/`
- `memory/`
- canonical architecture

This layer tells agents how to work and how knowledge is organized.

## Continuous Improvement

Use `/improve-system` after meaningful sessions to:

- update a skill when output required repeated correction
- record reusable lessons
- flag duplicate or stale guidance
- add missing validation steps
- preserve relevant experiences under `knowledge/me/experiences/`

Changes must be small, justified, and reviewable.
