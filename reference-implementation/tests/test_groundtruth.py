"""Ground-truth corpus test over sample_estate/.

Hand-verified relationships are the ground truth; we measure the extractor's
precision/recall against them. Runs under pytest OR as a plain script:

    pytest
    python tests/test_groundtruth.py
"""

from __future__ import annotations

import sys
import tempfile
from pathlib import Path

# make the package importable without installing (portable)
_SRC = Path(__file__).resolve().parent.parent / "src"
sys.path.insert(0, str(_SRC))

from mip import queries, store          # noqa: E402
from mip.pipeline import build_db        # noqa: E402

ESTATE = Path(__file__).resolve().parent.parent / "sample_estate"

# --- hand-labeled ground truth (source, rel_type, target) -----------------
EXPECTED_CONFIRMED = {
    # job -> program (EXEC PGM=)
    ("DAILYCRD", "EXECUTES", "CRDPOST"),
    ("STMTGEN", "EXECUTES", "STMTDRV"),
    ("PAYPROC", "EXECUTES", "PAYDRV"),
    ("INTCALC", "EXECUTES", "INTDRV"),
    # program -> program (static CALL)
    ("CRDPOST", "CALLS", "CRDVAL"),
    ("CRDPOST", "CALLS", "BALUPD"),
    ("STMTDRV", "CALLS", "STMTFMT"),
    ("PAYDRV", "CALLS", "PAYUPD"),
    ("INTDRV", "CALLS", "INTCOMP"),
    # program -> copybook (COPY)
    ("CRDPOST", "USES", "CARDREC"),
    ("CRDVAL", "USES", "CARDREC"),
    ("STMTDRV", "USES", "CARDREC"),
    ("STMTFMT", "USES", "CARDREC"),
    ("DEADPROG", "USES", "CARDREC"),
    ("BALUPD", "USES", "ACCTREC"),
    ("INTDRV", "USES", "ACCTREC"),
    ("INTCOMP", "USES", "ACCTREC"),
    ("PAYDRV", "USES", "PAYREC"),
    ("PAYUPD", "USES", "PAYREC"),
    # program -> db2 table (EXEC SQL)
    ("STMTDRV", "READS", "CARD_MASTER"),
    ("BALUPD", "WRITES", "CARD_MASTER"),
    ("PAYUPD", "WRITES", "PAYMENT"),
    ("PAYUPD", "WRITES", "ACCT_MASTER"),
}
# The grammar parser resolves the dynamic CALL (MOVE 'INTRATE1' TO WS-RATE-PGM; CALL
# WS-RATE-PGM) by constant propagation -> an *inferred* edge to INTRATE1 (not asserted,
# not dropped).
EXPECTED_RESOLVED = ("INTDRV", "CALLS", "INTRATE1")
EXPECTED_ROOTS = {"CRDPOST", "STMTDRV", "PAYDRV", "INTDRV"}
EXPECTED_DEAD = {"DEADPROG"}


def _build(tmp: str):
    build_db(ESTATE, tmp)
    return store.connect(tmp)


def _extracted(conn, status: str) -> set[tuple[str, str, str]]:
    rows = conn.execute(
        "SELECT source_id, rel_type, target_id FROM relationship WHERE validation_status = ?",
        (status,),
    )
    return {(r["source_id"], r["rel_type"], r["target_id"]) for r in rows}


def _metrics():
    with tempfile.TemporaryDirectory() as d:
        conn = _build(str(Path(d) / "mip.db"))
        confirmed = _extracted(conn, "confirmed")
        inferred = _extracted(conn, "inferred")
        tp = len(confirmed & EXPECTED_CONFIRMED)
        precision = tp / len(confirmed) if confirmed else 0.0
        recall = tp / len(EXPECTED_CONFIRMED)
        result = {
            "precision": precision, "recall": recall,
            "confirmed": confirmed, "inferred": inferred,
            "roots": set(queries.roots(conn)),
            "dead": set(queries.dead_code(conn)),
            "jobs_for_crdpost": queries.jobs_executing(conn, "CRDPOST"),
        }
        conn.close()
        return result


def test_precision_recall_perfect():
    m = _metrics()
    assert m["recall"] == 1.0, f"missing edges: {EXPECTED_CONFIRMED - m['confirmed']}"
    assert m["precision"] == 1.0, f"spurious edges: {m['confirmed'] - EXPECTED_CONFIRMED}"


def test_dynamic_call_resolved():
    m = _metrics()
    # the grammar parser resolves the dynamic CALL to its literal target, as `inferred`
    assert EXPECTED_RESOLVED in m["inferred"], "dynamic CALL should resolve to INTRATE1 (inferred)"


def test_roots_detected():
    assert _metrics()["roots"] == EXPECTED_ROOTS


def test_dead_code_detected():
    assert _metrics()["dead"] == EXPECTED_DEAD


def test_root_driver_query():
    assert _metrics()["jobs_for_crdpost"] == ["DAILYCRD"]


if __name__ == "__main__":
    m = _metrics()
    print(f"precision = {m['precision']:.3f}   recall = {m['recall']:.3f}")
    print(f"roots     = {sorted(m['roots'])}")
    print(f"dead code = {sorted(m['dead'])}")
    print(f"resolved (inferred) edges = {sorted(m['inferred'])}")
    print(f"jobs executing CRDPOST = {m['jobs_for_crdpost']}")
    ok = (m["precision"] == 1.0 and m["recall"] == 1.0
          and m["roots"] == EXPECTED_ROOTS and m["dead"] == EXPECTED_DEAD
          and EXPECTED_RESOLVED in m["inferred"])
    print("ALL CHECKS PASSED" if ok else "CHECKS FAILED")
    sys.exit(0 if ok else 1)
