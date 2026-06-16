# MIP Skills

The canonical MIP skills, built to the **Agent Skills standard**
([agentskills.io/specification](https://agentskills.io/specification)): each skill is a
folder whose name matches a `SKILL.md` file with YAML frontmatter (`name` +
`description` required; `metadata`, `license` optional) followed by the instructions.

All skills inherit [MIP_ENGINEERING_PRINCIPLES.md](MIP_ENGINEERING_PRINCIPLES.md)
(evidence + confidence, resilience, explainability, …).

## The catalog is the source of truth

[`skills.catalog.json`](skills.catalog.json) is the registry. It records every skill
plus its **connections**: the prompts that invoke it, the tools/code that implement it,
and a `status` (`implemented` / `partial` / `specified`).

> **Rule:** whenever you add, delete, or rename a skill, update `skills.catalog.json`
> in the same change, then run the validator. CI/humans use it to keep skills,
> prompts, and tools wired together.

```bash
python validate_catalog.py        # checks frontmatter + name==folder + catalog 1:1 sync
```

## How skills connect to the rest of MIP

```
04-prompts/*  (what to do)  ──►  03-skills/*  (who/how)  ──►  reference-implementation + 02-algorithms  (code that runs)
```

- Each prompt header names its **owning skill** (link to this folder).
- Each catalog entry lists the **prompts** and **tools/api** for that skill.
- `validate_catalog.py` guarantees folders ⇄ catalog stay 1:1.

## The 13 skills

| Skill | Category | Status |
|-------|----------|--------|
| mainframe-code-analyst | discovery | implemented |
| metadata-modeler | metadata | implemented |
| sqlite-engineer | platform | implemented |
| graph-engineer | intelligence | partial |
| business-capability-analyst | intelligence | partial |
| resilience-engineer | intelligence | partial |
| security-compliance-analyst | intelligence | specified |
| mainframe-modernization-architect | modernization | specified |
| legacy-rewrite-engineer | modernization | partial |
| test-engineer | platform | implemented |
| documentation-writer | platform | implemented |
| repository-engineer | platform | implemented |
| code-reviewer | platform | specified |

See [`modernization-leverage/SKILLS.md`](modernization-leverage/SKILLS.md) for
leverage-able community roles (incl. the Karpathy engineering guidelines).
