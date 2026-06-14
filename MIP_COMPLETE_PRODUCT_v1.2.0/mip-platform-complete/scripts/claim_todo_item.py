#!/usr/bin/env python3
from __future__ import annotations

import argparse
import os
import tempfile
from datetime import UTC, datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TODO = ROOT / "memory" / "todo.list"


def now() -> str:
    return datetime.now(UTC).isoformat()


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--owner", required=True)
    parser.add_argument("--artifact-type")
    args = parser.parse_args()

    lines = TODO.read_text(encoding="utf-8").splitlines()
    claimed = None

    # Atomic replace protects the file from partial writes. For multi-process
    # production use, wrap this operation with an OS/database lock.
    for idx, raw in enumerate(lines):
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        parts = raw.split("|")
        if len(parts) != 10 or parts[0] != "PENDING":
            continue
        if args.artifact_type and parts[1] != args.artifact_type:
            continue
        parts[0] = "IN_PROGRESS"
        parts[5] = args.owner
        parts[6] = now()
        lines[idx] = "|".join(parts)
        claimed = parts
        break

    if claimed is None:
        print("NO_CLAIMABLE_ITEM")
        return 2

    fd, temp_name = tempfile.mkstemp(dir=TODO.parent, prefix="todo.", text=True)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            handle.write("\n".join(lines) + "\n")
        os.replace(temp_name, TODO)
    finally:
        if os.path.exists(temp_name):
            os.unlink(temp_name)

    print("|".join(claimed))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
