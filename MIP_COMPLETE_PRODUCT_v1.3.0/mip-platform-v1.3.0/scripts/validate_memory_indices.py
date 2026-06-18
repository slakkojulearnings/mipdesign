#!/usr/bin/env python3
from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
MEMORY = ROOT / "memory"

SCHEMAS = {
    "catalog.txt": 9,
    "relationships.txt": 9,
    "todo.list": 10,
    "processed.log": 7,
}


def records(path: Path):
    for number, raw in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        yield number, line.split("|")


def main() -> int:
    errors: list[str] = []
    for name, expected in SCHEMAS.items():
        path = MEMORY / name
        if not path.exists():
            errors.append(f"missing: {path}")
            continue
        for number, parts in records(path):
            if len(parts) != expected:
                errors.append(f"{name}:{number}: expected {expected} fields, found {len(parts)}")

    todo_path = MEMORY / "todo.list"
    if todo_path.exists():
        seen_paths: dict[str, int] = {}
        for number, parts in records(todo_path):
            source_path = parts[3]
            if source_path in seen_paths:
                errors.append(
                    f"todo.list:{number}: duplicate source path; first seen at "
                    f"line {seen_paths[source_path]}: {source_path}"
                )
            seen_paths[source_path] = number

    catalog_path = MEMORY / "catalog.txt"
    if catalog_path.exists():
        seen_ids: set[tuple[str, str]] = set()
        for number, parts in records(catalog_path):
            key = (parts[0], parts[1])
            if key in seen_ids:
                errors.append(f"catalog.txt:{number}: duplicate TYPE/ID: {key}")
            seen_ids.add(key)

    if errors:
        print("Memory index validation failed:")
        for error in errors:
            print(f"- {error}")
        return 1

    print("Memory index validation passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
