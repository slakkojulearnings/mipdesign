"""Tests for the granular developer spec (cobol.program_spec) + DATA DIVISION section
tracking. The spec must be detailed enough to re-implement a program, with every fact
tied to source.
"""

from __future__ import annotations

import sys
from pathlib import Path

_SRC = Path(__file__).resolve().parent.parent / "src"
sys.path.insert(0, str(_SRC))

from mip import cobol, cobol_ast        # noqa: E402

ESTATE = Path(__file__).resolve().parent.parent / "sample_estate"


def _spec(pid):
    text = (ESTATE / "COBOL" / pid).read_text(encoding="utf-8")
    return cobol.program_spec(text, pid, f"COBOL/{pid}")


def test_data_items_carry_section():
    text = (ESTATE / "COBOL" / "CRDPOST").read_text(encoding="utf-8")
    u = cobol_ast.parse(text)
    assert u.data_items, "expected data items"
    # every parsed item records which DATA DIVISION section it came from
    assert all("section" in d for d in u.data_items)
    assert any(d["section"] == "WORKING-STORAGE" for d in u.data_items)


def test_data_structures_grouped_with_pic():
    s = _spec("CRDPOST")
    ws = next(g for g in s["data_structures"] if g["section"] == "WORKING-STORAGE")
    names = {it["name"]: it["pic"] for it in ws["items"]}
    assert names.get("WS-RETURN-CODE") == "S9(4)"


def test_procedure_outline_is_pseudocode():
    s = _spec("CRDPOST")
    main = next(o for o in s["procedure_outline"] if o["paragraph"] == "0000-MAIN")
    verbs = [step["verb"] for step in main["steps"]]
    assert "CALL" in verbs and "IF" in verbs
    # every step cites a source line
    assert all(isinstance(step["line"], int) for step in main["steps"])


def test_io_contract():
    s = _spec("CRDPOST")
    assert "CARDREC" in s["io"]["copybooks"]
    targets = {c["target"] for c in s["io"]["calls"]}
    assert {"CRDVAL", "BALUPD"} <= targets


def test_rules_have_snippet_and_typed_fields():
    s = _spec("CRDPOST")
    r = next(r for r in s["rules"] if r["condition"] == "WS-RETURN-CODE = 0")
    # real source snippet (list of {line, text}) around the rule
    assert r["snippet"] and all("line" in ln and "text" in ln for ln in r["snippet"])
    assert any("WS-RETURN-CODE" in ln["text"] for ln in r["snippet"])
    # the field is annotated with its PIC type, so a developer knows the format
    tf = {f["name"]: f["pic"] for f in r["typed_fields"]}
    assert tf.get("WS-RETURN-CODE") == "S9(4)"
