"""Tests for the grammar-based COBOL parser: AST, dynamic-call resolution, field lineage."""

from __future__ import annotations

import sys
from pathlib import Path

_SRC = Path(__file__).resolve().parent.parent / "src"
sys.path.insert(0, str(_SRC))

from mip import cobol, cobol_ast        # noqa: E402

ESTATE = Path(__file__).resolve().parent.parent / "sample_estate"


def _src(p):
    return (ESTATE / p).read_text(encoding="utf-8")


def test_ast_structure():
    u = cobol_ast.parse(_src("COBOL/CRDPOST"))
    assert u.program_id == "CRDPOST"
    assert "PROCEDURE" in u.divisions and "DATA" in u.divisions
    assert "0000-MAIN" in u.paragraphs
    # GOBACK / END-IF are statements, not paragraphs
    assert "GOBACK" not in u.paragraphs and "END-IF" not in u.paragraphs


def test_static_calls_confirmed():
    u = cobol_ast.parse(_src("COBOL/CRDPOST"))
    calls = {(c["target"], c["validation"]) for c in u.calls}
    assert ("CRDVAL", "confirmed") in calls and ("BALUPD", "confirmed") in calls


def test_dynamic_call_resolved_by_constant_propagation():
    u = cobol_ast.parse(_src("COBOL/INTDRV"))
    by_target = {c["target"]: c for c in u.calls}
    assert by_target["INTCOMP"]["validation"] == "confirmed"     # static literal
    # MOVE 'INTRATE1' TO WS-RATE-PGM ; CALL WS-RATE-PGM  -> resolved to INTRATE1
    assert "INTRATE1" in by_target
    assert by_target["INTRATE1"]["kind"] == "resolved"
    assert by_target["INTRATE1"]["validation"] == "inferred"
    assert by_target["INTRATE1"]["via"] == "WS-RATE-PGM"


def test_sql_field_lineage_read_and_write():
    read = cobol.field_lineage(_src("COBOL/STMTDRV"), "STMTDRV", "COBOL/STMTDRV")
    assert {"src": "CARD_MASTER.CURRENT_BALANCE", "dst": "CARD-BALANCE",
            "kind": "sql-read", "program": "STMTDRV",
            "evidence": "COBOL/STMTDRV:12"} in read

    write = cobol.field_lineage(_src("COBOL/PAYUPD"), "PAYUPD", "COBOL/PAYUPD")
    flows = {(f["src"], f["dst"], f["kind"]) for f in write}
    assert ("PAY-AMOUNT", "PAYMENT.PAY_AMOUNT", "sql-write") in flows


def test_data_items_parsed():
    u = cobol_ast.parse(_src("COBOL/CRDVAL"))
    names = {d["name"] for d in u.data_items}
    assert "LK-RETURN-CODE" in names


_ARITH_SNIPPET = """\
       IDENTIFICATION DIVISION.
       PROGRAM-ID. ARITH.
       DATA DIVISION.
       WORKING-STORAGE SECTION.
       01 PRICE PIC 9(5).
       01 TAX   PIC 9(5).
       01 TOTAL PIC 9(6).
       PROCEDURE DIVISION.
       0000-MAIN.
           COMPUTE TOTAL = PRICE + TAX.
           ADD TAX TO TOTAL.
           GOBACK.
"""


def test_compute_and_add_lineage():
    flows = {(f["src"], f["dst"], f["kind"])
             for f in cobol.field_lineage(_ARITH_SNIPPET, "ARITH", "ARITH")}
    assert ("PRICE", "TOTAL", "compute") in flows
    assert ("TAX", "TOTAL", "compute") in flows
    assert ("TAX", "TOTAL", "arith") in flows           # ADD TAX TO TOTAL


def _lineage(src):
    return {(f["src"], f["dst"], f["kind"])
            for f in cobol.field_lineage(src, "T", "T")}


def _wrap(proc_body, data="01 A PIC 9(4).\n       01 B PIC 9(4).\n       01 C PIC 9(4)."):
    return (f"""\
       IDENTIFICATION DIVISION.
       PROGRAM-ID. T.
       DATA DIVISION.
       WORKING-STORAGE SECTION.
       {data}
       PROCEDURE DIVISION.
       0000-MAIN.
{proc_body}
           GOBACK.
""")


def test_arith_giving_does_not_leak_separator_keywords():
    # BUG 1 regression: TO/FROM/BY must never appear as a "source" field.
    flows = _lineage(_wrap("           ADD A TO B GIVING C.\n"
                           "           SUBTRACT A FROM B GIVING C."))
    bad = {(s, d, k) for (s, d, k) in flows if s in {"TO", "FROM", "BY", "INTO", "GIVING"}}
    assert not bad, f"separator keyword leaked as a field: {bad}"
    assert ("A", "C", "arith") in flows and ("B", "C", "arith") in flows


def test_compute_rounded_and_multi_receiver():
    # BUG 3 regression: ROUNDED isn't a source; receivers are left of '='.
    flows = _lineage(_wrap("           COMPUTE C ROUNDED = A + B."))
    assert ("A", "C", "compute") in flows and ("B", "C", "compute") in flows
    assert not any(s == "ROUNDED" for (s, _, _) in flows)


def test_move_with_qualifier_and_subscript_not_dropped():
    # BUG 4 regression: MOVE A OF REC TO B  and  MOVE T(IDX) TO B must still yield a flow.
    data = ("01 REC.\n          05 A PIC X(4).\n"
            "       01 T.\n          05 ELEM PIC X OCCURS 5 TIMES.\n"
            "       01 B PIC X(4).")
    flows = _lineage(_wrap("           MOVE A OF REC TO B.", data=data))
    assert ("A", "B", "move") in flows


def test_group_move_flagged():
    snippet = """\
       IDENTIFICATION DIVISION.
       PROGRAM-ID. GRP.
       DATA DIVISION.
       WORKING-STORAGE SECTION.
       01 IN-REC.
          05 IN-A PIC X(4).
       01 OUT-REC.
          05 OUT-A PIC X(4).
       PROCEDURE DIVISION.
       0000-MAIN.
           MOVE IN-REC TO OUT-REC.
           GOBACK.
"""
    flows = {(f["src"], f["dst"], f["kind"])
             for f in cobol.field_lineage(snippet, "GRP", "GRP")}
    assert ("IN-REC", "OUT-REC", "move-group") in flows  # group item move

