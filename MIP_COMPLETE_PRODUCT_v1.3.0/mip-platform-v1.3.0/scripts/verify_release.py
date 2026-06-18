#!/usr/bin/env python3
from __future__ import annotations

import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def run(command: list[str]) -> None:
    print("+", " ".join(command))
    subprocess.run(command, cwd=ROOT, check=True)


def main() -> int:
    run([sys.executable, "scripts/validate_skills.py"])
    run([sys.executable, "scripts/validate_memory_indices.py"])
    run(["ruff", "check", "src", "tests"])
    run(["ruff", "format", "--check", "src", "tests"])
    run(["mypy", "src/mip"])
    run(["pytest", "--cov=mip", "--cov-report=term-missing", "--cov-fail-under=80"])
    print("Release verification passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
