# Claude Workspace

This folder contains portable Claude Code assets for MIP Enterprise Intelligence.

- `agents\` contains project subagent prompts.
- `skills\` contains Claude-compatible MIP skills.
- `settings.json` is sanitized for this standalone package.
- `settings.local.json` is intentionally not shipped. Use it for personal or
  machine-specific overrides.

Do not store API keys or local absolute paths in committed Claude settings.
