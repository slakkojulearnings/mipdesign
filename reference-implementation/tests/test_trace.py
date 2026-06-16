"""Tests for the bidirectional call trace (queries.trace): upstream + downstream, the DB
touchpoints, depth/direction/include_data controls, and the honesty contract (unresolved
branches kept and flagged)."""

from __future__ import annotations

import sys
import tempfile
from pathlib import Path

_SRC = Path(__file__).resolve().parent.parent / "src"
sys.path.insert(0, str(_SRC))

from mip import queries, store        # noqa: E402
from mip.pipeline import build_db      # noqa: E402

ESTATE = Path(__file__).resolve().parent.parent / "sample_estate"


def _trace(pid, **kw):
    with tempfile.TemporaryDirectory() as d:
        db = str(Path(d) / "mip.db")
        build_db(ESTATE, db)
        conn = store.connect(db)
        out = queries.trace(conn, pid, **kw)
        conn.close()
    return out


def _ids(node):
    """All node ids in a trace tree."""
    if not node:
        return set()
    out = {node["id"]}
    for c in node.get("children", []):
        out |= _ids(c["node"])
    return out


def test_downstream_includes_calls_and_data():
    t = _trace("CRDPOST")
    assert t["found"]
    down = _ids(t["downstream"])
    assert {"CRDVAL", "BALUPD"} <= down           # called programs
    assert "CARDREC" in down                        # copybook (USES)
    assert "CARD_MASTER" in down                    # DB2 table (WRITES)


def test_upstream_reaches_the_job():
    t = _trace("CRDPOST")
    up = _ids(t["upstream"])
    assert "DAILYCRD" in up                         # the job that EXECUTES it


def test_db_touchpoints_direction():
    t = _trace("CRDPOST")
    assert "CARD_MASTER" in t["db_touchpoints"]["writes"]


def test_unresolved_branch_is_kept_and_flagged():
    """INTDRV calls INTRATE1 via constant propagation -> inferred. It must appear in the
    trace, flagged (kept, not dropped)."""
    t = _trace("INTDRV")
    down_edges = [e for e in t["edges"] if e["direction"] == "down"]
    int = next(e for e in down_edges if e["target"] == "INTRATE1")
    assert int["validation_status"] == "inferred"
    assert t["stats"]["unresolved_count"] >= 1


def test_include_data_false_drops_tables_and_copybooks():
    t = _trace("CRDPOST", include_data=False)
    ids = _ids(t["downstream"])
    assert "CARD_MASTER" not in ids and "CARDREC" not in ids
    assert {"CRDVAL", "BALUPD"} <= ids              # control flow still present


def test_direction_and_depth_controls():
    down_only = _trace("CRDPOST", direction="down")
    assert down_only["upstream"] is None and down_only["downstream"] is not None
    shallow = _trace("CRDPOST", depth=1)
    # depth 1 reaches direct callees but not their data leaves two hops down
    assert "CRDVAL" in _ids(shallow["downstream"])


def test_unknown_program_not_found():
    t = _trace("NOPE")
    assert t["found"] is False
