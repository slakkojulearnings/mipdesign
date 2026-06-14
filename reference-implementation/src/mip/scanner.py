"""Repository scanner — Level 1 (inventory).

Classifies each file by CONTENT first (real mainframe PDS members usually have no
file extension), then falls back to the library folder name, then extension.
"""

from __future__ import annotations

import re
from pathlib import Path

from .records import Artifact, Evidence, make_id

# content signatures
_JOB_LINE = re.compile(r"(?mi)^//\w+\s+JOB\b")
_EXEC_PGM = re.compile(r"(?i)EXEC\s+PGM=")
_LEVEL_LINE = re.compile(r"(?m)^\s*\d{2}\s+[\w-]+")

_FOLDER_HINT = {
    "JCL": "jcl", "PROCLIB": "proc", "COBOL": "cobol", "COB": "cobol",
    "COPYLIB": "copybook", "COPY": "copybook", "CPY": "copybook",
    "DB2": "db2", "DDL": "db2", "VSAM": "vsam", "CICS": "cics",
}
_EXT_HINT = {
    ".cbl": "cobol", ".cob": "cobol", ".cpy": "copybook",
    ".jcl": "jcl", ".sql": "db2",
}


def classify(text: str, path: Path) -> str:
    up = text.upper()

    # 1. content signatures (works for extension-less members)
    if _JOB_LINE.search(text) or _EXEC_PGM.search(text):
        return "jcl"
    if "IDENTIFICATION DIVISION" in up and "PROGRAM-ID" in up:
        return "cobol"
    if "CREATE TABLE" in up:
        return "db2"
    if _LEVEL_LINE.search(text) and "PIC" in up:
        return "copybook"  # COBOL data layout without a PROGRAM-ID

    # 2. fall back to the library folder name
    for part in path.parts:
        hint = _FOLDER_HINT.get(part.upper())
        if hint:
            return hint

    # 3. fall back to extension
    return _EXT_HINT.get(path.suffix.lower(), "unknown")


def scan(root: str | Path) -> list[Artifact]:
    root = Path(root)
    artifacts: list[Artifact] = []
    for p in sorted(root.rglob("*")):
        if not p.is_file():
            continue
        try:
            text = p.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        atype = classify(text, p)
        rel = str(p.relative_to(root)).replace("\\", "/")
        artifacts.append(
            Artifact(
                artifact_id=make_id(rel),
                path=rel,
                artifact_type=atype,
                file_name=p.name,
                size_bytes=p.stat().st_size,
                line_count=text.count("\n") + 1,
                evidence=Evidence.confirmed(f"scan:{rel}", method="scan"),
            )
        )
    return artifacts
