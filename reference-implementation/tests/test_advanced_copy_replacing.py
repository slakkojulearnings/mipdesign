"""Demonstrates (and regression-guards) the visible difference between the default and
advanced parser backends: COPY ... REPLACING expansion.

The default parser does not expand copybooks, so a CALL hidden inside a copybook behind a
REPLACING placeholder is invisible to it. The advanced backend's preprocess() expander —
given a copybook resolver — inlines and rewrites it, and the CALL becomes a confirmed edge.

Uses examples/advanced_parser/ (kept OUT of sample_estate so it never affects ground-truth
counts). Backend-agnostic: exercises cobol_ast + antlr_adapter.preprocess directly, so it
runs without the generated ANTLR grammar.
"""

from __future__ import annotations

import sys
from pathlib import Path

_SRC = Path(__file__).resolve().parent.parent / "src"
sys.path.insert(0, str(_SRC))

from mip import antlr_adapter, cobol_ast        # noqa: E402

EXAMPLES = Path(__file__).resolve().parent.parent / "examples" / "advanced_parser"
PROGRAM = EXAMPLES / "CARDADV"


def _text():
    return PROGRAM.read_text(encoding="utf-8")


def test_default_parser_cannot_see_the_copybook_call():
    u = cobol_ast.parse(_text())
    assert [c["target"] for c in u.calls] == []        # CALL is inside the (un-expanded) copybook
    assert "CALLBOOK" in [c["name"] for c in u.copies]  # only the COPY is visible


def test_advanced_expander_recovers_the_call():
    resolver = antlr_adapter.default_resolver(EXAMPLES)
    expanded = antlr_adapter.preprocess(_text(), resolver=resolver)
    # COPY ... REPLACING ==:SUBPGM:== BY ==REALSUB== inlines CALL ':SUBPGM:' -> CALL 'REALSUB'
    assert "CALL 'REALSUB'" in expanded
    assert "COPY CALLBOOK" not in expanded
    u = cobol_ast.parse(expanded)
    by_target = {c["target"]: c for c in u.calls}
    assert "REALSUB" in by_target
    assert by_target["REALSUB"]["validation"] == "confirmed"
