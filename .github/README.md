# GitHub setup (project-level)

This repo ships with GitHub automation so it works as soon as you push it.

## Workflows

| Workflow | Trigger | What it does |
|----------|---------|--------------|
| [`ci.yml`](workflows/ci.yml) | push / PR | Engine tests (pytest), sample scan, **skills-catalog validation**, frontend build |
| [`claude.yml`](workflows/claude.yml) | `@claude` in an issue/PR comment | Claude Code acts on the request (answer / implement / open a PR) |
| [`claude-code-review.yml`](workflows/claude-code-review.yml) | PR opened/updated | MIP-aware automatic code review |

## One-time enablement (for the Claude workflows)

1. Install the **Claude GitHub App** on the repo: <https://github.com/apps/claude>
   (or run `/install-github-app` from Claude Code).
2. Add a repo secret **`ANTHROPIC_API_KEY`** (Settings → Secrets and variables → Actions).
3. That's it — comment `@claude please …` on an issue/PR, or open a PR to get a review.

> CI needs no secrets and runs on its own. If your default branch isn't `main`/`master`,
> adjust the `branches:` in `ci.yml`.

## Skills / agents

Project-level Claude Code config also ships in [`.claude/`](../.claude/): the MIP
**skills** (`.claude/skills/`), **subagents** (`.claude/agents/`), and shared
**settings** (`.claude/settings.json`). Personal overrides go in `settings.local.json`
(git-ignored, not shipped).
