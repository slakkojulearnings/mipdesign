"""Tests for global search (queries.search)."""

from __future__ import annotations

import sys
import tempfile
from pathlib import Path

_SRC = Path(__file__).resolve().parent.parent / "src"
sys.path.insert(0, str(_SRC))

from mip import queries, store        # noqa: E402
from mip.pipeline import build_db      # noqa: E402

ESTATE = Path(__file__).resolve().parent.parent / "sample_estate"


def _search(q):
    with tempfile.TemporaryDirectory() as d:
        db = str(Path(d) / "mip.db")
        build_db(ESTATE, db)
        conn = store.connect(db)
        results = queries.search(conn, q)
        conn.close()
    return results


def test_search_card_finds_table_and_card_assets():
    results = _search("CARD")
    by_id = {(r["kind"], r["id"]) for r in results}
    # the DB2 table CARD_MASTER
    assert ("table", "CARD_MASTER") in by_id
    # card-related assets surfaced for the term
    assert ("copybook", "CARDREC") in by_id
    assert ("capability", "Card Posting") in by_id
    # every result carries a kind
    assert all(r["kind"] for r in results)


def test_search_auth_finds_programs_and_transaction():
    results = _search("AUTH")
    by_id = {(r["kind"], r["id"]) for r in results}
    assert ("program", "AUTHTRAN") in by_id
    assert ("program", "AUTHVAL") in by_id
    assert ("transaction", "AUTH") in by_id
    assert all(r["kind"] for r in results)


def test_exact_match_ranks_highest():
    results = _search("AUTH")
    # the AUTH transaction is an exact match -> top result
    assert results[0]["id"] == "AUTH"
    assert results[0]["score"] >= results[-1]["score"]


def test_result_shape_and_cap():
    results = _search("A")          # broad term
    assert len(results) <= 25
    for r in results:
        assert set(r.keys()) == {"kind", "id", "detail", "score"}


def test_empty_query_returns_nothing():
    assert _search("") == []
    assert _search("   ") == []
