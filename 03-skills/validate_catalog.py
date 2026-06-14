"""Validate the MIP skills against the agentskills standard + keep the catalog in sync.

Checks, for skills.catalog.json and every skill folder here:
  - each skill folder has a SKILL.md with YAML frontmatter
  - frontmatter `name` is present, matches the folder name, and is spec-valid
    (1-64 chars, lowercase a-z/0-9/hyphen, no leading/trailing/double hyphen)
  - `description` is present and non-empty (<= 1024 chars)
  - folders and catalog entries are 1:1 (run this after adding/deleting a skill)

Usage:  python validate_catalog.py     (exit 0 = OK, 1 = problems)
"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
NAME_RE = re.compile(r"^[a-z0-9]+(-[a-z0-9]+)*$")


def parse_frontmatter(text: str) -> dict:
    if not text.startswith("---"):
        return {}
    end = text.find("\n---", 3)
    if end == -1:
        return {}
    fm = {}
    for line in text[3:end].splitlines():
        m = re.match(r"^([A-Za-z0-9_-]+):\s*(.*)$", line)
        if m:
            fm[m.group(1)] = m.group(2).strip().strip('"')
    return fm


def main() -> int:
    errors: list[str] = []
    skill_dirs = sorted(p.name for p in HERE.iterdir()
                        if p.is_dir() and (p / "SKILL.md").exists())
    # also flag dirs that look like skills but lack SKILL.md
    for p in HERE.iterdir():
        if p.is_dir() and not (p / "SKILL.md").exists() and p.name not in {"modernization-leverage"}:
            errors.append(f"folder '{p.name}' has no SKILL.md")

    for name in skill_dirs:
        fm = parse_frontmatter((HERE / name / "SKILL.md").read_text(encoding="utf-8"))
        if fm.get("name") != name:
            errors.append(f"{name}: frontmatter name '{fm.get('name')}' != folder name")
        if not NAME_RE.match(name) or len(name) > 64:
            errors.append(f"{name}: invalid skill name per spec")
        desc = fm.get("description", "")
        if not desc:
            errors.append(f"{name}: missing description")
        elif len(desc) > 1024:
            errors.append(f"{name}: description exceeds 1024 chars")

    catalog_path = HERE / "skills.catalog.json"
    catalog_names = set()
    if catalog_path.exists():
        catalog = json.loads(catalog_path.read_text(encoding="utf-8"))
        catalog_names = {s["name"] for s in catalog.get("skills", [])}
    else:
        errors.append("skills.catalog.json missing")

    missing = set(skill_dirs) - catalog_names
    extra = catalog_names - set(skill_dirs)
    if missing:
        errors.append(f"skills not in catalog (add them): {sorted(missing)}")
    if extra:
        errors.append(f"catalog entries with no folder (remove them): {sorted(extra)}")

    if errors:
        print("SKILLS VALIDATION FAILED:")
        for e in errors:
            print("  -", e)
        return 1
    print(f"OK — {len(skill_dirs)} skills valid and in sync with skills.catalog.json")
    for n in skill_dirs:
        print("  -", n)
    return 0


if __name__ == "__main__":
    sys.exit(main())
