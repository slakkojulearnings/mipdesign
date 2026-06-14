"""Tests for the EXEC CICS (online layer) extractor."""

from __future__ import annotations

import sys
import tempfile
from pathlib import Path

_SRC = Path(__file__).resolve().parent.parent / "src"
sys.path.insert(0, str(_SRC))

from mip import cobol, queries, store      # noqa: E402
from mip.pipeline import build_db           # noqa: E402

ESTATE = Path(__file__).resolve().parent.parent / "sample_estate"


def _edges(pid):
    text = (ESTATE / "COBOL" / pid).read_text(encoding="utf-8")
    return {(e.rel_type, e.target_type, e.target_id) for e in cobol.extract_edges(text, pid, pid)}


def test_cics_link_is_a_call():
    # EXEC CICS LINK PROGRAM('AUTHVAL') -> online program call
    assert ("CALLS", "program", "AUTHVAL") in _edges("AUTHTRAN")


def test_cics_file_screen_queue():
    auth = _edges("AUTHTRAN")
    assert ("READS", "dataset", "CARDFILE") in auth     # READ FILE
    assert ("USES", "screen", "AUTHMAP") in auth        # SEND/RECEIVE MAP
    assert ("WRITES", "queue", "AUTHLOG") in _edges("AUTHVAL")  # WRITEQ TS


def test_comment_mentioning_exec_cics_is_ignored():
    # AUTHVAL has a comment containing "EXEC CICS LINK" — must NOT create an edge.
    assert ("CALLS", "program", "LINK") not in _edges("AUTHVAL")


def test_online_program_is_root_not_dead():
    with tempfile.TemporaryDirectory() as d:
        db = str(Path(d) / "mip.db")
        build_db(ESTATE, db)
        conn = store.connect(db)
        roots = set(queries.roots(conn))
        dead = set(queries.dead_code(conn))
        conn.close()
    assert "AUTHTRAN" in roots          # online entry point
    assert "AUTHTRAN" not in dead        # not mistaken for dead code
    assert "AUTHVAL" not in dead         # reachable via CICS LINK
