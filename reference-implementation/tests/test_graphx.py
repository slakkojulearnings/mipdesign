"""Tests for the NetworkX graph layer (blast radius + centrality)."""

from __future__ import annotations

import sys
import tempfile
from pathlib import Path

_SRC = Path(__file__).resolve().parent.parent / "src"
sys.path.insert(0, str(_SRC))

from mip import graphx, store          # noqa: E402
from mip.pipeline import build_db       # noqa: E402

ESTATE = Path(__file__).resolve().parent.parent / "sample_estate"


def _conn():
    d = tempfile.mkdtemp()
    db = str(Path(d) / "mip.db")
    build_db(ESTATE, db)
    return store.connect(db)


def test_blast_radius_of_table():
    # Changing CARD_MASTER should impact its writer (BALUPD) and reader (STMTDRV),
    # plus their callers/jobs (CRDPOST, DAILYCRD, STMTGEN).
    conn = _conn()
    r = graphx.blast_radius(conn, "CARD_MASTER")
    conn.close()
    assert r["found"]
    impacted = {x["id"] for x in r["impacted"]}
    assert {"BALUPD", "STMTDRV", "CRDPOST", "DAILYCRD", "STMTGEN"} <= impacted
    assert r["blast_radius_score"] > 0


def test_blast_radius_of_called_program():
    # Changing CRDVAL impacts CRDPOST (caller) and DAILYCRD (job above it).
    conn = _conn()
    r = graphx.blast_radius(conn, "CRDVAL")
    conn.close()
    impacted = {x["id"] for x in r["impacted"]}
    assert {"CRDPOST", "DAILYCRD"} <= impacted


def test_centrality_ranks_programs():
    conn = _conn()
    ranked = graphx.centrality(conn, top=5)
    conn.close()
    assert ranked and all("pagerank" in x for x in ranked)
    # every ranked node is a real program
    assert all(x["program"].isupper() for x in ranked)


def test_unknown_target_is_graceful():
    conn = _conn()
    r = graphx.blast_radius(conn, "NOSUCHPGM")
    conn.close()
    assert r["found"] is False and r["impacted"] == []
