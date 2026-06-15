"""Tests for the per-program Mermaid sequence diagram."""

from __future__ import annotations

import sys
from pathlib import Path

_SRC = Path(__file__).resolve().parent.parent / "src"
sys.path.insert(0, str(_SRC))

from fastapi.testclient import TestClient   # noqa: E402

from mip import cobol                         # noqa: E402
from mip.api import app                       # noqa: E402

ESTATE = Path(__file__).resolve().parent.parent / "sample_estate"


def _seq(pid: str) -> dict:
    text = (ESTATE / "COBOL" / pid).read_text(encoding="utf-8")
    return cobol.sequence(text, pid)


def test_authtran_cics_messages():
    s = _seq("AUTHTRAN")
    m = s["mermaid"]
    assert m.startswith("sequenceDiagram")
    assert "AUTHTRAN->>AUTHVAL: CICS LINK" in m       # EXEC CICS LINK PROGRAM('AUTHVAL')
    assert "AUTHTRAN->>CARDFILE: CICS READS" in m     # EXEC CICS READ FILE('CARDFILE')
    assert "AUTHVAL" in s["participants"]


def test_crdpost_call_order():
    s = _seq("CRDPOST")
    m = s["mermaid"]
    assert m.startswith("sequenceDiagram")
    assert "CRDPOST->>CRDVAL: CALL" in m
    assert "CRDPOST->>BALUPD: CALL" in m
    # CRDVAL is called before BALUPD in source order
    assert m.index("CRDPOST->>CRDVAL") < m.index("CRDPOST->>BALUPD")


def test_intdrv_marks_resolved_and_dynamic():
    s = _seq("INTDRV")
    m = s["mermaid"]
    # static call to INTCOMP, plus a dynamic call resolved by const propagation -> INTRATE1
    assert "INTDRV->>INTCOMP: CALL" in m
    assert "INTDRV->>INTRATE1: CALL (resolved)" in m


def test_endpoint_sequence():
    c = TestClient(app)
    assert c.post("/api/scan", params={"path": str(ESTATE)}).status_code == 200
    r = c.get("/api/program/AUTHTRAN/sequence")
    assert r.status_code == 200
    data = r.json()
    assert data["program_id"] == "AUTHTRAN"
    assert data["mermaid"].startswith("sequenceDiagram")
    assert "AUTHTRAN->>AUTHVAL: CICS LINK" in data["mermaid"]
