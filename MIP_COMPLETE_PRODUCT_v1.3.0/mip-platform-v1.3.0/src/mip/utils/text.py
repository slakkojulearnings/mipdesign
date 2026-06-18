from __future__ import annotations

import string
from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class DecodedText:
    text: str | None
    encoding: str | None
    is_binary: bool
    printable_ratio: float


def _printable_ratio(text: str) -> float:
    if not text:
        return 1.0
    printable = sum(ch in string.printable or ch.isprintable() for ch in text)
    return printable / len(text)


def decode_source(data: bytes) -> DecodedText:
    if not data:
        return DecodedText("", "utf-8", False, 1.0)
    if b"\x00" in data[:4096]:
        return DecodedText(None, None, True, 0.0)

    candidates = ("utf-8", "cp1252", "latin-1", "cp037", "cp500")
    best: DecodedText | None = None
    for encoding in candidates:
        try:
            text = data.decode(encoding)
        except UnicodeDecodeError:
            continue
        ratio = _printable_ratio(text[:20000])
        candidate = DecodedText(text, encoding, ratio < 0.70, ratio)
        if best is None or candidate.printable_ratio > best.printable_ratio:
            best = candidate
        if encoding == "utf-8" and ratio > 0.95:
            break

    return best or DecodedText(None, None, True, 0.0)


def line_number_from_offset(text: str, offset: int) -> int:
    return text.count("\n", 0, max(offset, 0)) + 1
