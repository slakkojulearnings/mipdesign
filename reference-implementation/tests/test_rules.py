"""Tests for business-rule extraction (cobol.business_rules).

Honesty contract (Principle 1): the raw COBOL condition and its source line are
`confirmed` facts; the kind classification and plain-English statement are
interpretation, flagged validation_status='inferred'.
"""

from __future__ import annotations

import sys
from pathlib import Path

_SRC = Path(__file__).resolve().parent.parent / "src"
sys.path.insert(0, str(_SRC))

from mip import cobol        # noqa: E402

ESTATE = Path(__file__).resolve().parent.parent / "sample_estate"


def _rules(pid):
    text = (ESTATE / "COBOL" / pid).read_text(encoding="utf-8")
    return cobol.business_rules(text, pid, f"COBOL/{pid}")


def test_crdval_validation_rule_on_card_status():
    rules = _rules("CRDVAL")
    assert len(rules) == 1
    r = rules[0]
    # condition is the real source text and references CARD-STATUS
    assert r["condition"] == "CARD-STATUS = 'A'"
    assert "CARD-STATUS" in r["fields"]
    assert r["kind"] in ("validation", "decision")
    # CRDVAL IF is on line 13 — evidence points at the real line
    assert r["source_evidence"] == "COBOL/CRDVAL:13"
    # the interpretation (kind + plain-English statement) is inferred, not asserted
    assert r["validation_status"] == "inferred"
    assert r["confidence"] < 1.0
    assert r["statement"].startswith("When CARD-STATUS")


def test_intcomp_calculation_rule():
    rules = _rules("INTCOMP")
    assert len(rules) == 1
    r = rules[0]
    assert r["kind"] == "calculation"
    assert r["condition"] == "ACCT-BALANCE = ACCT-BALANCE * 1.015"
    assert "ACCT-BALANCE" in r["fields"]
    assert r["source_evidence"] == "COBOL/INTCOMP:11"
    assert r["validation_status"] == "inferred"


def test_crdpost_guard_rule():
    rules = _rules("CRDPOST")
    conds = {r["condition"] for r in rules}
    assert "WS-RETURN-CODE = 0" in conds
    r = next(r for r in rules if r["condition"] == "WS-RETURN-CODE = 0")
    assert r["source_evidence"] == "COBOL/CRDPOST:14"
    assert "WS-RETURN-CODE" in r["fields"]


def test_authval_rule_evidence_is_real():
    # the raw condition's evidence is a real line (line 13 of AUTHVAL)
    rules = _rules("AUTHVAL")
    assert rules
    r = rules[0]
    assert r["condition"] == "CARD-STATUS = 'A'"
    assert r["source_evidence"] == "COBOL/AUTHVAL:13"


def test_rule_shape_has_required_keys():
    r = _rules("CRDVAL")[0]
    for key in ("id", "kind", "condition", "action", "statement", "fields",
                "tables", "source_evidence", "confidence", "validation_status"):
        assert key in r, f"missing key: {key}"
    assert r["tables"] == []
    assert isinstance(r["fields"], list)
