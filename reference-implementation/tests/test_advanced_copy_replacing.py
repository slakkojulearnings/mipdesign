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
import tempfile
from pathlib import Path

import pytest

_SRC = Path(__file__).resolve().parent.parent / "src"
sys.path.insert(0, str(_SRC))

from mip import antlr_adapter, cobol, cobol_antlr, cobol_ast, store   # noqa: E402
from mip.pipeline import build_db                                      # noqa: E402

EXAMPLES = Path(__file__).resolve().parent.parent / "examples" / "advanced_parser"
PROGRAM = EXAMPLES / "CARDADV"


def _scan_edges(monkeypatch, mode):
    """Scan the example estate with the given parser backend; return (source,rel,target) edges."""
    monkeypatch.setenv("MIP_PARSER", mode)
    with tempfile.TemporaryDirectory() as d:
        db = str(Path(d) / "ex.db")
        build_db(EXAMPLES, db)
        conn = store.connect(db)
        rows = list(conn.execute("SELECT source_id, rel_type, target_id FROM relationship"))
        conn.close()
    return {(r["source_id"], r["rel_type"], r["target_id"]) for r in rows}


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


def test_scan_default_does_not_expand(monkeypatch):
    """A full scan with the default backend: the COPY edge is recorded but the hidden CALL
    is not (no copybook expansion)."""
    edges = _scan_edges(monkeypatch, "default")
    assert ("CARDADV", "USES", "CALLBOOK") in edges
    assert ("CARDADV", "CALLS", "REALSUB") not in edges


def test_scan_advanced_resolver_recovers_call(monkeypatch):
    """A full scan with the advanced backend now wires a copybook resolver into the pipeline,
    so COPY ... REPLACING expands and the hidden CALL becomes a real graph edge — while the
    COPY (USES) edge is still recorded. This is the production divergence."""
    pytest.importorskip("antlr4")
    if not cobol_antlr.available():
        pytest.skip("ANTLR grammar not generated (run scripts/gen_grammar.py)")
    edges = _scan_edges(monkeypatch, "advanced")
    assert ("CARDADV", "CALLS", "REALSUB") in edges      # recovered from the copybook
    assert ("CARDADV", "USES", "CALLBOOK") in edges       # COPY edge still recorded
