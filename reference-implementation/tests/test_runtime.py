"""Tests for the Runtime Correlation Layer (engine + reconciliation + criticality).

Runtime data is optional external evidence; correlation is evidence-based and
confidence-scored; absent data => 'unknown' (never fabricated).
"""

from __future__ import annotations

import sys
import tempfile
from pathlib import Path

_SRC = Path(__file__).resolve().parent.parent / "src"
sys.path.insert(0, str(_SRC))

from mip import runtime, store          # noqa: E402
from mip.pipeline import build_db        # noqa: E402

ESTATE = Path(__file__).resolve().parent.parent / "sample_estate"
RUNTIME = ESTATE / "runtime" / "runtime.json"


def _conn():
    d = tempfile.mkdtemp()
    db = str(Path(d) / "mip.db")
    build_db(ESTATE, db)
    return store.connect(db)


def _by_id(rows):
    return {r["id"]: r for r in rows}


def test_sample_loads_and_persists():
    rt = runtime.load_runtime(RUNTIME)
    assert rt["window"] == "2026-05"
    conn = _conn()
    n = runtime.load_into_db(conn, rt)
    assert n == len(rt["entities"])
    # persisted and upsert is idempotent (re-load doesn't duplicate)
    runtime.load_into_db(conn, rt)
    cnt = conn.execute("SELECT COUNT(*) FROM runtime_metric").fetchone()[0]
    conn.close()
    assert cnt == n


def test_deadprog_is_confirmed_dead():
    rt = runtime.load_runtime(RUNTIME)
    conn = _conn()
    rec = runtime.reconcile(conn, rt)
    conn.close()
    confirmed = {r["program"] for r in rec["confirmed-dead"]}
    assert "DEADPROG" in confirmed
    # and it is NOT in the "ran" bucket
    ran = {r["program"] for r in rec["static-dead but ran"]}
    assert "DEADPROG" not in ran


def test_contradiction_intrate1_flagged_as_static_miss():
    # INTRATE1 is a dynamic CALL target with no source member: static analysis cannot
    # confirm it, but runtime shows it executed. It must surface either as
    # "static-dead but ran" or be flagged as a static miss.
    rt = runtime.load_runtime(RUNTIME)
    conn = _conn()
    rec = runtime.reconcile(conn, rt)
    conn.close()
    ran = {r["program"] for r in rec["static-dead but ran"]}
    miss = {r["program"] for r in rec["static-miss"]}
    assert "INTRATE1" in (ran | miss)
    # it should be recognized as a known dynamic target, confirmed by runtime
    hit = next(r for r in rec["static-miss"] if r["program"] == "INTRATE1")
    assert hit["known_as_dynamic_target"] is True
    assert hit["exec_count"] > 0


def test_criticality_ranks_authtran_highly():
    # AUTHTRAN has a huge exec_count (online auth). Runtime-weighted criticality must
    # surface it near the very top. The two auth programs (AUTHTRAN + the AUTHVAL it
    # calls) share the max exec_count and dominate the ranking; AUTHTRAN is top-2.
    rt = runtime.load_runtime(RUNTIME)
    conn = _conn()
    ranked = runtime.runtime_criticality(conn, rt, top=12)
    conn.close()
    top2 = {r["program"] for r in ranked[:2]}
    assert {"AUTHTRAN", "AUTHVAL"} == top2          # busy auth path is on top
    authtran = next(r for r in ranked if r["program"] == "AUTHTRAN")
    # ranked above every non-auth program (its exec_count is the estate max)
    others = [r["runtime_criticality"] for r in ranked
              if r["program"] not in ("AUTHTRAN", "AUTHVAL")]
    assert authtran["runtime_criticality"] > max(others)
    assert authtran["runtime_status"] == "confirmed-at-runtime"


def test_absent_data_is_unknown_not_fabricated():
    # Build a runtime feed that omits some programs; those must correlate as 'unknown'
    # with no fabricated exec_count.
    partial = {"window": "2026-05", "source": "test",
               "entities": [{"id": "CRDPOST", "type": "program",
                             "exec_count": 5, "last_run": "2026-05-31",
                             "avg_elapsed_ms": 100}]}
    conn = _conn()
    rows = _by_id(runtime.correlate(conn, partial))
    conn.close()
    # CRDPOST has data
    assert rows["CRDPOST"]["runtime_status"] == "confirmed-at-runtime"
    # a program with no runtime row must be 'unknown', not fabricated
    assert rows["PAYUPD"]["runtime_status"] == "unknown"
    assert rows["PAYUPD"]["execution_frequency"] is None
    assert rows["PAYUPD"]["confidence"] == 0.0


def test_correlate_status_buckets():
    rt = runtime.load_runtime(RUNTIME)
    conn = _conn()
    rows = _by_id(runtime.correlate(conn, rt))
    conn.close()
    assert rows["AUTHTRAN"]["runtime_status"] == "confirmed-at-runtime"
    assert rows["DEADPROG"]["runtime_status"] == "cold"          # exec_count == 0
    assert rows["DEADPROG"]["execution_frequency"] == 0
