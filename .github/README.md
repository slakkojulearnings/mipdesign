# GitHub setup (project-level)

This repo ships with **CI** so it validates itself on every push — no secrets required.

| Workflow | Trigger | What it does |
|----------|---------|--------------|
| [`ci.yml`](workflows/ci.yml) | push / PR | Engine tests (pytest) + sample scan, **skills-catalog validation**, frontend build |

If your default branch isn't `main`/`master`, adjust the `branches:` in `ci.yml`.

## Project Claude Code config

Local Claude Code config also ships in [`.claude/`](../.claude/): the MIP **skills**
(`.claude/skills/`), **subagents** (`.claude/agents/`), and shared **settings**
(`.claude/settings.json`). These work locally with no setup. Personal overrides go in
`.claude/settings.local.json` (git-ignored).

> The optional Claude GitHub Action workflows are intentionally **not** included — they'd
> require installing the Claude GitHub App and an `ANTHROPIC_API_KEY` secret. Add them
> later if you want `@claude` on PRs.
