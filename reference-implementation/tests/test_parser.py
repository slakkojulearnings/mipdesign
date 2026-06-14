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

