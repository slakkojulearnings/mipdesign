---
name: repository-engineer
description: Creates and evolves the MIP repository, package boundaries, configuration, CI, VS Code workspace, and delivery scaffolding. Use when bootstrapping the repo or deciding where new code and documents belong.
license: Apache-2.0
compatibility: Designed for skills-aware coding agents working with the MIP repository.
metadata:
  author: mip-project
  version: "1.0"
---

# Repository Engineer

## Purpose

Maintain a small, coherent repository that a new engineer can run safely.

## Inputs

- approved architecture and technology choices
- feature specification
- existing repository structure

## Workflow

1. Read the canonical repository-structure document.
2. Place the change in the narrowest existing package.
3. Avoid creating a new layer without a demonstrated responsibility.
4. Add configuration, tests, CI, and documentation needed to run the change.
5. Protect `mfcode/`, `data/`, `output/`, logs, and credentials.
6. Verify install, lint, type checks, tests, and a smoke command.

## Outputs

- repository structure changes
- setup/configuration files
- CI or developer tooling
- updated run instructions

## Constraints

Do not create speculative services, frameworks, or deployment infrastructure. Do not move unrelated files.

## Success Criteria

A clean clone can install, test, and run the affected workflow using documented commands.

## Repository Rules

Follow `CLAUDE.md`, protect proprietary source, keep changes surgical, and run the relevant validation commands before completion.
