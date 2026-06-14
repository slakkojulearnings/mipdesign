#!/usr/bin/env python3
from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
EXCLUDED_PARTS = {
    ".git",
    ".venv",
    "__pycache__",
    ".pytest_cache",
    ".ruff_cache",
    ".mypy_cache",
    "htmlcov",
    "dist",
    "build",
    "mip_platform.egg-info",
}


def main() -> int:
    files = []
    for path in ROOT.rglob("*"):
        if not path.is_file():
            continue
        relative = path.relative_to(ROOT)
        if any(part in EXCLUDED_PARTS for part in relative.parts):
            continue
        if relative.as_posix() in {"MANIFEST.md", ".coverage"}:
            continue
        if (
            relative.parts
            and relative.parts[0] in {"data", "output", "logs"}
            and path.name != ".gitkeep"
        ):
            continue
        files.append(relative.as_posix())
    files.sort()
    content = "# File Manifest\n\n" + "\n".join(f"- `{name}`" for name in files) + "\n"
    (ROOT / "MANIFEST.md").write_text(content, encoding="utf-8")
    print(f"Wrote MANIFEST.md with {len(files)} files.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
