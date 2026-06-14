"""COBOL extractor (v0.1, regex).

Extracts PROGRAM-ID and the relationships a program participates in:
  CALL 'LIT'      -> CALLS   (confirmed)
  CALL WS-VAR     -> CALLS   (needs_review, low confidence)  <-- the hard case, kept not dropped
  COPY name       -> USES    (copybook)
  EXEC SQL ...     -> READS / WRITES (db2_table)

Honest limits (see ../../00-foundation/ARCHITECTURE.md): regex, not a grammar; no
COPY ... REPLACING expansion; fixed-format comment lines (col-7 '*') are skipped.
"""

from __future__ import annotations

import re

from .records import Edge, Evidence

_PROGRAM_ID = re.compile(r"(?i)PROGRAM-ID\s*\.\s*([A-Z0-9][A-Z0-9-]*)")
_COPY = re.compile(r"(?i)\bCOPY\s+([A-Z0-9][A-Z0-9-]*)")
_CALL_LIT = re.compile(r"(?i)\bCALL\s+'([A-Z0-9][A-Z0-9-]*)'")
_CALL_DYN = re.compile(r"(?i)\bCALL\s+([A-Za-z][\w-]*)")  # unquoted => dynamic
_SQL_BLOCK = re.compile(r"(?is)EXEC\s+SQL(.*?)END-EXEC")
_SQL_UPDATE = re.compile(r"(?i)\bUPDATE\s+([A-Z0-9_]+)")
_SQL_INSERT = re.compile(r"(?i)\bINSERT\s+INTO\s+([A-Z0-9_]+)")
_SQL_DELETE = re.compile(r"(?i)\bDELETE\s+FROM\s+([A-Z0-9_]+)")
_SQL_FROM = re.compile(r"(?i)\bFROM\s+([A-Z0-9_]+)")


def _is_comment(line: str) -> bool:
    s = line.lstrip()
    return s.startswith("*") or s.startswith("/")


def _line_of(text: str, idx: int) -> int:
    return text.count("\n", 0, idx) + 1


def program_id(text: str) -> str | None:
    m = _PROGRAM_ID.search(text)
    return m.group(1).upper() if m else None


# Paragraph names begin in Area A (cols 8-11 => <=7 leading spaces); statements sit in
# Area B (col 12+). Restricting to Area A avoids counting terminators like GOBACK/END-IF.
_PARA = re.compile(r"^\s{0,7}([A-Z0-9][A-Z0-9-]+)\.\s*$")
_DIVISIONS = ("IDENTIFICATION", "ENVIRONMENT", "DATA", "PROCEDURE")
_NON_PARA = {"GOBACK", "STOP", "EXIT", "CONTINUE", "END-IF", "END-EVALUATE",
             "END-PERFORM", "END-EXEC", "END-CALL"}


def structure(text: str) -> dict:
    """A v0.1 structural / AST-lite outline of a COBOL program.

    Not a full grammar (see ARCHITECTURE.md) — it surfaces divisions, PROCEDURE-DIVISION
    paragraphs, a statement mix, and a cyclomatic-complexity proxy, which is enough to
    give the UI a meaningful 'structure' / complexity insight.
    """
    up = text.upper()
    divisions = [d for d in _DIVISIONS if f"{d} DIVISION" in up]
    code = "\n".join(l for l in text.splitlines() if not _is_comment(l))

    # paragraphs: only within the PROCEDURE DIVISION (avoid data-item lines)
    paragraphs: list[str] = []
    proc_idx = up.find("PROCEDURE DIVISION")
    if proc_idx >= 0:
        proc_lines = text[proc_idx:].splitlines()[1:]
        for line in proc_lines:
            if _is_comment(line):
                continue
            m = _PARA.match(line)
            if m:
                name = m.group(1).upper()
                if name not in _NON_PARA and not name.endswith(("DIVISION", "SECTION")):
                    paragraphs.append(name)

    counts = {
        "CALL": len(re.findall(r"(?i)\bCALL\b", code)),
        "PERFORM": len(re.findall(r"(?i)\bPERFORM\b", code)),
        "IF": len(re.findall(r"(?i)\bIF\b", code)),
        "COPY": len(_COPY.findall(code)),
        "EXEC_SQL": len(_SQL_BLOCK.findall(code)),
    }
    complexity = 1 + counts["IF"] + counts["PERFORM"]  # rough cyclomatic proxy
    return {"divisions": divisions, "paragraphs": paragraphs,
            "counts": counts, "complexity": complexity}


def extract_edges(text: str, program: str, rel_path: str) -> list[Edge]:
    edges: list[Edge] = []
    src = f"program:{program}"

    def ev(line_no: int, **kw) -> Evidence:
        return Evidence.confirmed(f"{rel_path}:{line_no}", **kw)

    # line-oriented: CALL (static + dynamic) and COPY, skipping comment lines
    for i, line in enumerate(text.splitlines(), start=1):
        if _is_comment(line):
            continue
        for m in _CALL_LIT.finditer(line):
            edges.append(Edge.build("program", program, "CALLS", "program",
                                    m.group(1).upper(), ev(i)))
        # dynamic calls: unquoted identifier after CALL -> kept but flagged
        for m in _CALL_DYN.finditer(line):
            target = m.group(1).upper()
            edges.append(Edge.build("program", program, "CALLS", "program", target,
                                    Evidence.needs_review(f"{rel_path}:{i}", confidence=0.3)))
        for m in _COPY.finditer(line):
            edges.append(Edge.build("program", program, "USES", "copybook",
                                    m.group(1).upper(), ev(i)))

    # SQL blocks: READS / WRITES tables
    for block in _SQL_BLOCK.finditer(text):
        body = block.group(1)
        line_no = _line_of(text, block.start())
        for rx, rel in ((_SQL_UPDATE, "WRITES"), (_SQL_INSERT, "WRITES"), (_SQL_DELETE, "WRITES")):
            for m in rx.finditer(body):
                edges.append(Edge.build("program", program, rel, "db2_table",
                                        m.group(1).upper(), ev(line_no)))
        # READS only when the block is a SELECT (avoid DELETE ... FROM double counting)
        if re.search(r"(?i)\bSELECT\b", body):
            for m in _SQL_FROM.finditer(body):
                edges.append(Edge.build("program", program, "READS", "db2_table",
                                        m.group(1).upper(), ev(line_no)))

    # dedupe identical edges (same id)
    seen: dict[str, Edge] = {}
    for e in edges:
        seen[e.relationship_id] = e
    return list(seen.values())
