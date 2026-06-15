"""Repository scanner — Level 1 (inventory), adaptive & content-driven.

Real estates are ~180k members, mostly extension-less, with folders that differ per
site and change over time. So classification is **learned from the estate**, not from a
hardcoded folder map:

  1. CONTENT first — language signatures (COBOL/JCL/DB2/CICS/copybook) that are intrinsic
     to the languages, not site config. A capped header read is enough (signatures sit at
     the top of a member), so we never read a multi-thousand-line program in full.
  2. BINARY by content — NUL bytes / high non-text ratio in the header => "binary",
     inventoried but never parsed. This catches load modules/DBRMs/maps regardless of
     folder name.
  3. LEARNED FOLDER PROFILE — pass 1 tallies, per directory, the content-resolved type
     distribution and the binary ratio. Pass 2 uses that profile to classify members the
     content couldn't resolve: a member in a folder that is predominantly one source type
     inherits it (folder-inferred); a member in a predominantly-binary folder is treated
     as binary. New or renamed folders therefore "just work" with no code change.
  4. Thin conventions — extension hints, and a small (env-extensible: MIP_BINARY_LIBS)
     list of well-known compiled-library names as a last-resort safety net for the rare
     text-looking member inside a conventionally-binary library.

`profile_estate(root)` exposes the learned per-folder map for inspection.
See docs/MAINFRAME_ARTIFACTS.md for the artifact taxonomy and IMS/MQ scope.
"""

from __future__ import annotations

import os
import re
from collections import Counter, defaultdict
from pathlib import Path

from .records import Artifact, Evidence, make_id

# Only the first HEADER_CAP bytes of each file are read for classification.
HEADER_CAP = 64 * 1024

# content signatures (intrinsic language facts, not site/folder config)
_JOB_LINE = re.compile(r"(?mi)^//\w+\s+JOB\b")
_EXEC_PGM = re.compile(r"(?i)EXEC\s+PGM=")
_LEVEL_LINE = re.compile(r"(?m)^\s*\d{2}\s+[\w-]+")

# extension hints — a weak, last-resort per-file signal (real PDS members rarely have one)
_EXT_HINT = {
    ".cbl": "cobol", ".cob": "cobol", ".cpy": "copybook",
    ".jcl": "jcl", ".sql": "db2",
}

# Well-known compiled/binary library names. A thin convention fallback only — binary is
# normally decided by CONTENT (_looks_binary) and the learned folder binary-ratio. Extend
# at runtime without code changes via MIP_BINARY_LIBS="NAME1,NAME2".
_DEFAULT_BINARY_LIBS = {
    "LOADLIB", "LOAD", "LINKLIB", "CICSLOAD", "LSM", "DBRMLIB", "DBRM",
    "DBDLIB", "DBD", "PSBLIB", "PSB", "MAPLIB", "MAP", "LDV", "VOG",
}

_TEXT_BYTES = bytes(range(0x20, 0x7F)) + b"\t\n\r\f\x0b"
_NON_TEXT_RATIO = 0.30
_FOLDER_DOMINANCE = 0.5     # share of a folder that must be one type to infer it
_FOLDER_BINARY_RATIO = 0.8  # folders this binary => unresolved members are binary too


def _binary_libs() -> set[str]:
    extra = os.environ.get("MIP_BINARY_LIBS", "")
    return _DEFAULT_BINARY_LIBS | {x.strip().upper() for x in extra.split(",") if x.strip()}


def _looks_binary(chunk: bytes) -> bool:
    """Header-only binary test: NUL bytes, or too many non-text bytes."""
    if not chunk:
        return False
    if b"\x00" in chunk:
        return True
    non_text = sum(b not in _TEXT_BYTES for b in chunk)
    return (non_text / len(chunk)) > _NON_TEXT_RATIO


def _binary_library_hint(path: Path, libs: set[str]) -> bool:
    return any(part.upper() in libs for part in path.parts)


def _content_type(text: str) -> str | None:
    """Resolve a type from intrinsic content signatures, or None if unrecognised."""
    up = text.upper()
    if _JOB_LINE.search(text) or _EXEC_PGM.search(text):
        return "jcl"
    if "IDENTIFICATION DIVISION" in up and "PROGRAM-ID" in up:
        return "cobol"
    if "CREATE TABLE" in up:
        return "db2"
    if "DEFINE TRANSACTION" in up or "DEFINE PROGRAM" in up or "DFHCSDUP" in up:
        return "cics"
    if _LEVEL_LINE.search(text) and "PIC" in up:
        return "copybook"
    return None


def classify(text: str, path: Path) -> str:
    """Classify a single already-decoded TEXT member (content + extension only).

    Folder learning needs whole-estate context, so it lives in scan(); this helper is the
    per-file fallback used by callers that already hold the text.
    """
    return _content_type(text) or _EXT_HINT.get(path.suffix.lower(), "unknown")


# (rel, parent_dir, size, line_count, content_type|None, is_binary)
def _profile_pass(root: Path):
    """Pass 1: read each header once, content-classify, and learn per-folder profiles."""
    libs = _binary_libs()
    recs: list[tuple] = []
    text_counts: dict[str, Counter] = defaultdict(Counter)
    binary_count: dict[str, int] = defaultdict(int)
    total: dict[str, int] = defaultdict(int)

    for p in sorted(root.rglob("*")):
        if not p.is_file():
            continue
        try:
            with p.open("rb") as fh:
                head = fh.read(HEADER_CAP)
        except OSError:
            continue
        size = p.stat().st_size
        capped = size > len(head)
        rel = str(p.relative_to(root)).replace("\\", "/")
        parent = str(p.parent.relative_to(root)).replace("\\", "/")
        total[parent] += 1

        if _looks_binary(head) or _binary_library_hint(p, libs):
            binary_count[parent] += 1
            recs.append((rel, parent, size, None, None, True))
        else:
            text = head.decode("utf-8", errors="replace")
            ctype = _content_type(text)
            line_count = None if capped else head.count(b"\n") + 1
            recs.append((rel, parent, size, line_count, ctype, False))
            key = ctype or _EXT_HINT.get(Path(rel).suffix.lower())
            if key:
                text_counts[parent][key] += 1

    profile: dict[str, dict] = {}
    for d, members in total.items():
        tc = text_counts[d]
        dominant = tc.most_common(1)[0][0] if tc else None
        profile[d] = {
            "dominant_type": dominant,
            "type_counts": dict(tc),
            "binary_ratio": round(binary_count[d] / members, 3) if members else 0.0,
            "members": members,
        }
    return recs, profile


def profile_estate(root: str | Path) -> dict:
    """Learned per-folder profile: {folder: {dominant_type, type_counts, binary_ratio, members}}.

    A discovery artifact in its own right — shows which folders hold what, derived from the
    actual estate rather than any hardcoded assumption.
    """
    return _profile_pass(Path(root))[1]


def scan(root: str | Path) -> list[Artifact]:
    root = Path(root)
    recs, profile = _profile_pass(root)
    artifacts: list[Artifact] = []
    for rel, parent, size, line_count, ctype, is_binary in recs:
        if is_binary:
            atype = "binary"
        elif ctype:                                   # resolved by content
            atype = ctype
        else:                                         # learned-folder / extension fallback
            ext = _EXT_HINT.get(Path(rel).suffix.lower())
            prof = profile.get(parent, {})
            members = prof.get("members") or 0
            dom = prof.get("dominant_type")
            if ext:
                atype = ext
            elif members and prof.get("binary_ratio", 0.0) >= _FOLDER_BINARY_RATIO:
                atype = "binary"                      # folder is overwhelmingly binary
            elif dom and members and prof["type_counts"].get(dom, 0) / members >= _FOLDER_DOMINANCE:
                atype = dom                           # folder-inferred dominant source type
            else:
                atype = "unknown"
        artifacts.append(
            Artifact(
                artifact_id=make_id(rel),
                path=rel,
                artifact_type=atype,
                file_name=Path(rel).name,
                size_bytes=size,
                line_count=line_count,
                evidence=Evidence.confirmed(f"scan:{rel}", method="scan"),
            )
        )
    return artifacts
