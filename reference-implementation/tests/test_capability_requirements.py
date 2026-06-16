"""Tests for capability requirements aggregation (queries.capability_detail + the rule
roll-up the API performs on top of it).

Honesty contract: the capability grouping is `inferred`; triggers / member programs /
data access are derived from confirmed edges; business rules cite real source lines.
"""

from __future__ import annotations

import sys
import tempfile
from pathlib import Path

_SRC = Path(__file__).resolve().parent.parent / "src"
sys.path.insert(0, str(_SRC))

from mip import cobol, queries, store      # noqa: E402
from mip.pipeline import build_db           # noqa: E402

ESTATE = Path(__file__).resolve().parent.parent / "sample_estate"


def _detail(name):
    with tempfile.TemporaryDirectory() as d:
        db = str(Path(d) / "mip.db")
        build_db(ESTATE, db)
        conn = store.connect(db)
        out = queries.capability_detail(conn, name)
        conn.close()
    return out


def _caps():
    with tempfile.TemporaryDirectory() as d:
        db = str(Path(d) / "mip.db")
        build_db(ESTATE, db)
        conn = store.connect(db)
        out = queries.capabilities(conn)
        conn.close()
    return out


def test_root_driven_capabilities_are_flagged_rootless_false():
    caps = _caps()
    root_driven = [c for c in caps if not c["rootless"]]
    assert {c["root"] for c in root_driven} >= {"CRDPOST", "AUTHTRAN", "STMTDRV"}


def test_dead_program_surfaces_as_a_rootless_capability():
    """DEADPROG is reachable from no root — instead of vanishing it must appear as a
    rootless capability (kept and flagged, lower confidence)."""
    caps = _caps()
    rootless = [c for c in caps if c["rootless"]]
    members = {p for c in rootless for p in c["programs"]}
    assert "DEADPROG" in members
    cap = next(c for c in rootless if "DEADPROG" in c["programs"])
    assert cap["validation_status"] == "inferred"
    assert cap["confidence"] < 0.5
    assert cap["jobs"] == []                       # no entry point


def test_resolvable_by_root_and_by_inferred_name():
    d = _detail("CRDPOST")
    assert d["root"] == "CRDPOST"
    assert d["capability"] == "Card Posting"
    assert d["validation_status"] == "inferred"
    # the same capability resolves by its inferred name too
    assert _detail("Card Posting")["root"] == "CRDPOST"


def test_unknown_capability_is_none():
    assert _detail("NO-SUCH-CAP") is None


def test_triggers_include_the_batch_job():
    d = _detail("CRDPOST")
    assert {"type": "batch job", "id": "DAILYCRD"} in d["triggers"]


def test_data_access_records_direction():
    d = _detail("CRDPOST")
    tables = {t["table"]: t["access"] for t in d["tables"]}
    assert "CARD_MASTER" in tables
    assert "WRITES" in tables["CARD_MASTER"]


def test_member_programs_carry_role_and_source_path():
    d = _detail("CRDPOST")
    progs = {p["program"] for p in d["programs"]}
    assert {"CRDPOST", "CRDVAL"} <= progs
    # every member has a source path so the API can read its rules
    assert all(p["source_path"] for p in d["programs"])


def test_requirements_rollup_aggregates_member_business_rules():
    """Mirror the API: rules across all member programs include CRDVAL's CARD-STATUS rule,
    each citing a real source line."""
    d = _detail("CRDPOST")
    rules = []
    for p in d["programs"]:
        text = (ESTATE / p["source_path"]).read_text(encoding="utf-8")
        rules.extend(cobol.business_rules(text, p["program"], p["source_path"]))
    conds = {r["condition"] for r in rules}
    assert "CARD-STATUS = 'A'" in conds          # from CRDVAL
    assert "WS-RETURN-CODE = 0" in conds          # from CRDPOST
    # every rolled-up rule keeps its honesty envelope
    assert all(r["validation_status"] == "inferred" and r["source_evidence"] for r in rules)
