#!/usr/bin/env python3
from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SKILLS = ROOT / "skills"
NAME_PATTERN = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")


def frontmatter(text: str) -> dict[str, str]:
    if not text.startswith("---\n"):
        return {}
    try:
        raw = text.split("---\n", 2)[1]
    except IndexError:
        return {}
    result: dict[str, str] = {}
    for line in raw.splitlines():
        if line.startswith(" ") or ":" not in line:
            continue
        key, value = line.split(":", 1)
        result[key.strip()] = value.strip().strip('"')
    return result


def main() -> int:
    errors: list[str] = []
    count = 0
    for directory in sorted(path for path in SKILLS.iterdir() if path.is_dir()):
        count += 1
        skill_file = directory / "SKILL.md"
        if not skill_file.exists():
            errors.append(f"{directory.name}: missing SKILL.md")
            continue
        text = skill_file.read_text(encoding="utf-8")
        metadata = frontmatter(text)
        name = metadata.get("name", "")
        description = metadata.get("description", "")
        if name != directory.name:
            errors.append(f"{directory.name}: frontmatter name must match directory")
        if not NAME_PATTERN.fullmatch(name):
            errors.append(f"{directory.name}: invalid skill name")
        if not description or len(description) < 20:
            errors.append(f"{directory.name}: description is missing or too short")
        if len(text) > 30_000:
            errors.append(f"{directory.name}: SKILL.md is too large; use progressive disclosure")
    if errors:
        print("Skill validation failed:")
        for error in errors:
            print(f"- {error}")
        return 1
    print(f"Skill validation passed for {count} skills.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
