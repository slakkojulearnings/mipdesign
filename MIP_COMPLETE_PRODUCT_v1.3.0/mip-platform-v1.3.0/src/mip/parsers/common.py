from __future__ import annotations

import re


def cobol_code_lines(text: str) -> list[tuple[int, str]]:
    """Return source line numbers and normalized COBOL code areas.

    Fixed-format sequence and indicator columns are removed when detected. Comment
    lines are ignored. Free-form source is preserved.
    """
    result: list[tuple[int, str]] = []
    for number, raw in enumerate(text.splitlines(), 1):
        line = raw.rstrip("\r\n")
        if not line.strip():
            continue
        code = line
        if len(line) >= 7 and re.fullmatch(r"[ 0-9]{6}", line[:6]):
            indicator = line[6]
            if indicator in {"*", "/"}:
                continue
            code = line[7:72] if len(line) > 72 else line[7:]
        stripped = code.strip()
        if not stripped or stripped.startswith("*>"):
            continue
        result.append((number, stripped))
    return result


def compact_statements(lines: list[tuple[int, str]]) -> list[tuple[int, int, str]]:
    """Join lines into period-terminated statements while retaining line ranges."""
    statements: list[tuple[int, int, str]] = []
    buffer: list[str] = []
    start: int | None = None
    end = 0
    for line_number, code in lines:
        if start is None:
            start = line_number
        buffer.append(code)
        end = line_number
        joined = " ".join(buffer)
        while "." in joined:
            before, after = joined.split(".", 1)
            if before.strip():
                assert start is not None
                statements.append((start, end, before.strip() + "."))
            joined = after.strip()
            buffer = [joined] if joined else []
            start = line_number if joined else None
    if buffer and start is not None:
        statements.append((start, end, " ".join(buffer).strip()))
    return statements


def normalize_name(value: str) -> str:
    return value.strip().strip("'\"").rstrip(".,").upper()
