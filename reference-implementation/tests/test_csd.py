"""Tests for CICS CSD/RDO parsing (transaction -> entry program) and the backend switch."""

from __future__ import annotations

import sys
import tempfile
from pathlib import Path

_SRC = Path(__file__).resolve().parent.parent / "src"
sys.path.insert(0, str(_SRC))

from mip import cics_csd, parser_backend, queries, scanner, store  # noqa: E402
from mip.pipeline import build_db                                   # noqa: E402

ESTATE = Path(__file__).resolve().parent.parent / "sample_estate"


def test_csd_is_classified_cics():
    text = (ESTATE / "CICS" / "AUTHCSD").read_text(encoding="utf-8")
    assert scanner.classify(text, Path("CICS/AUTHCSD")) == "cics"


def test_csd_maps_transaction_to_program():
    text = (ESTATE / "CICS" / "AUTHCSD").read_text(encoding="utf-8")
    edges = {(e.source_type, e.source_id, e.rel_type, e.target_type, e.target_id)
             for e in cics_csd.extract_edges(text, "CICS/AUTHCSD")}
    assert ("transaction", "AUTH", "STARTS", "program", "AUTHTRAN") in edges


def test_transaction_shows_as_caller_of_entry_program():
    with tempfile.TemporaryDirectory() as d:
        db = str(Path(d) / "mip.db")
        build_db(ESTATE, db)
        conn = store.connect(db)
        callers = {c["source_id"] for c in queries.callers(conn, "AUTHTRAN")}
        roots = set(queries.roots(conn))
        conn.close()
    assert "AUTH" in callers              # transaction triggers the entry program
    assert "AUTHTRAN" in roots            # entry program is still the root-driver


def test_starts_only_program_is_root_not_dead():
    # BUG 2 regression: a program that is ONLY a CSD transaction's PROGRAM (STARTS target),
    # with no EXEC CICS of its own, must be an online root and never flagged dead.
    from mip.records import Edge, Evidence
    with tempfile.TemporaryDirectory() as d:
        db = str(Path(d) / "mip.db")
        conn = store.connect(db)
        conn.execute("INSERT INTO program (program_id, program_name, language, discovered_at)"
                     " VALUES ('ONLPGM','ONLPGM','cobol','t')")
        store.insert_edge(conn, Edge.build(
            "transaction", "TX", "STARTS", "program", "ONLPGM",
            Evidence(source_evidence="CICS/X:1", discovery_method="cics-csd",
                     confidence=1.0, validation_status="confirmed")))
        conn.commit()
        roots = set(queries.roots(conn))
        dead = set(queries.dead_code(conn))
        conn.close()
    assert "ONLPGM" in roots and "ONLPGM" not in dead


def test_parser_backend_switch_default():
    info = parser_backend.backend_info()
    assert info["requested"] == "default"
    assert info["effective"] == "default"      # advanced unavailable -> graceful default
