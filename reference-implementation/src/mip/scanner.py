"""Repository scanner — Level 1 (inventory).

Classifies each file by CONTENT first (real mainframe PDS members usually have no
file extension), then falls back to the library folder name, then extension.

Scale note: a real estate is ~180k members, many of them compiled/binary library
members (load modules, DBRMs, maps). To stay fast and to avoid garbage-parsing
binary content, classification reads only a capped header of each file:

  * If the header looks binary (NUL bytes or a high ratio of undecodable bytes),
    the file is classified "binary", inventoried, and NOT read further. Binary
    library members (LOADLIB, CICSLOAD, DBRMLIB, ...) are inventory-only — MIP
    never parses them as source.
  * Otherwise the capped header is decoded as text and classified with the same
    COBOL/JCL/DB2/CICS/copybook signatures as before (they all appear early in a
    member, so the header is sufficient and no full read is needed to classify).

See docs/MAINFRAME_ARTIFACTS.md for the artifact taxonomy and IMS/MQ scope.
"""

from __future__ import annotations

import re
from pathlib import Path

from .records import Artifact, Evidence, make_id

# Only the first HEADER_CAP bytes of each file are read for classification.
# Every text signature below appears at the top of a member, so this is enough
# to classify without ever reading a multi-thousand-line program in full.
HEADER_CAP = 64 * 1024

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

# Library/folder names whose members are compiled/binary artifacts. MIP inventories
# these and skips them for parsing (they are not source). See the artifact doc for
# what each is and the low-confidence relationship a binary name still implies.
_BINARY_LIBRARY_HINT = {
    "LOADLIB", "LOAD", "LINKLIB", "CICSLOAD", "LSM", "DBRMLIB", "DBRM",
    "DBDLIB", "DBD", "PSBLIB", "PSB", "MAPLIB", "MAP", "LDV", "VOG",
}

# Bytes that are normal in EBCDIC-or-ASCII mainframe text. Anything outside this
# set (other than the printable range) counts toward the "looks binary" ratio.
_TEXT_BYTES = bytes(range(0x20, 0x7F)) + b"\t\n\r\f\x0b"
_NON_TEXT_RATIO = 0.30


def _looks_binary(chunk: bytes) -> bool:
    """Header-only binary test: NUL bytes, or too many non-text bytes."""
    if not chunk:
        return False
    if b"\x00" in chunk:
        return True
    non_text = sum(b not in _TEXT_BYTES for b in chunk)
    return (non_text / len(chunk)) > _NON_TEXT_RATIO


def _binary_library_hint(path: Path) -> bool:
    """True if the path sits in a known compiled/binary library."""
    return any(part.upper() in _BINARY_LIBRARY_HINT for part in path.parts)


def classify(text: str, path: Path) -> str:
    """Classify already-decoded TEXT (used by callers that hold the text).

    Operates on whatever string it is given; in scan() this is the capped header.
    """
    up = text.upper()

    # 1. content signatures (works for extension-less members)
    if _JOB_LINE.search(text) or _EXEC_PGM.search(text):
        return "jcl"
    if "IDENTIFICATION DIVISION" in up and "PROGRAM-ID" in up:
        return "cobol"
    if "CREATE TABLE" in up:
        return "db2"
    if "DEFINE TRANSACTION" in up or "DEFINE PROGRAM" in up or "DFHCSDUP" in up:
        return "cics"      # CICS CSD/RDO resource definitions
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
            with p.open("rb") as fh:
                head = fh.read(HEADER_CAP)
        except OSError:
            continue

        size = p.stat().st_size                       # cheap; no read needed
        capped = size > len(head)                     # file is larger than the header
        rel = str(p.relative_to(root)).replace("\\", "/")

        # binary path FIRST: a binary member must never be misread as text.
        if _looks_binary(head) or _binary_library_hint(p):
            atype = "binary"
            line_count = None                         # do not line-count binary
        else:
            text = head.decode("utf-8", errors="replace")
            atype = classify(text, p)
            # line_count from the header bytes only; if the file was capped this is a
            # partial count (None signals "unknown / not fully read") — never a 2nd read.
            line_count = None if capped else head.count(b"\n") + 1

        artifacts.append(
            Artifact(
                artifact_id=make_id(rel),
                path=rel,
                artifact_type=atype,
                file_name=p.name,
                size_bytes=size,
                line_count=line_count,
                evidence=Evidence.confirmed(f"scan:{rel}", method="scan"),
            )
        )
    return artifacts
