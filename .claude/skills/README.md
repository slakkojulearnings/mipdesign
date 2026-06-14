# Project Skills (deployed for Claude Code)

These are the MIP skills made available to **Claude Code at the project level** — they
follow the Agent Skills standard (`<name>/SKILL.md` with `name`/`description` frontmatter)
and are auto-discovered when working in this repo.

**Canonical source:** [`03-skills/`](../../03-skills/). This folder
is a *deployment copy* so the skills ship and are usable from Claude Code. Keep them in
sync — after editing a skill in `03-skills/`, re-deploy:

```bash
# from repo root
cp 03-skills/MIP_ENGINEERING_PRINCIPLES.md .claude/skills/
cp 03-skills/skills.catalog.json          .claude/skills/
for d in 03-skills/*/; do n=$(basename "$d"); \
  [ -f "$d/SKILL.md" ] && mkdir -p ".claude/skills/$n" && cp "$d/SKILL.md" ".claude/skills/$n/SKILL.md"; done
python 03-skills/validate_catalog.py
```

The registry is [`skills.catalog.json`](skills.catalog.json) (skill → prompts → tools/api).
Update it on any add/delete and run the validator.
