"""Performance + regression guard for the scan -> load pipeline.

Two concerns:
  1. Correctness preservation — the bulk/transactional load must yield exactly the same
     rows, edges and counts as before (guards against the optimization changing results).
  2. A small-scale timing sanity — a 2k-file synthetic estate must load under a generous
     threshold. Deliberately loose so it is not flaky on CI / slow disks.

Runs under pytest OR as a plain script.
"""

from __future__ import annotations

import shutil
import sys
import tempfile
import time
from pathlib import Path

# make the package importable without installing (portable)
_SRC = Path(__file__).resolve().parent.parent / "src"
sys.path.insert(0, str(_SRC))

from mip import store              # noqa: E402
from mip.pipeline import build_db   # noqa: E402

ESTATE = Path(__file__).resolve().parent.parent / "sample_estate"

# Pinned baseline for sample_estate (the per-row pipeline produced exactly these).
# If the extractor legitimately changes, update these alongside test_groundtruth.py.
EXPECTED_COUNTS = {
    "artifacts": 24,
    "programs": 12,
    "jobs": 4,
    "steps": 4,
}


def _all_edges(conn) -> set[tuple[str, str, str, str]]:
    rows = conn.execute(
        "SELECT source_id, rel_type, target_id, validation_status FROM relationship"
    )
    return {(r["source_id"], r["rel_type"], r["target_id"], r["validation_status"])
            for r in rows}


def test_counts_unchanged_on_sample_estate():
    """build_db over sample_estate yields the pinned program/job/step/artifact counts."""
    with tempfile.TemporaryDirectory() as d:
        counts = build_db(ESTATE, str(Path(d) / "mip.db"))
        for k, v in EXPECTED_COUNTS.items():
            assert counts[k] == v, f"{k}: got {counts[k]}, expected {v}"
        # edges are non-empty and counted consistently with the relationship table.
        conn = store.connect(str(Path(d) / "mip.db"))
        n_rel = conn.execute("SELECT COUNT(*) AS c FROM relationship").fetchone()["c"]
        conn.close()
        assert counts["edges"] == n_rel
        assert counts["edges"] > 0


def test_bulk_load_matches_per_row_rows():
    """The bulk pipeline writes exactly the same relationship rows a per-row load would.

    We rebuild via build_db (bulk) and re-load the SAME artifacts/edges per-row into a
    second DB, then assert identical edge sets — proving the optimization is row-preserving.
    """
    from mip import cics_csd, cobol, jcl, scanner
    from mip.records import Program

    with tempfile.TemporaryDirectory() as d:
        bulk_db = str(Path(d) / "bulk.db")
        build_db(ESTATE, bulk_db)
        bconn = store.connect(bulk_db)
        bulk_edges = _all_edges(bconn)
        bconn.close()

        # Per-row reference load.
        ref_db = str(Path(d) / "ref.db")
        conn = store.connect(ref_db)
        for a in scanner.scan(ESTATE):
            store.insert_artifact(conn, a)
            if a.artifact_type not in {"cobol", "jcl", "cics"}:
                continue
            text = (ESTATE / a.path).read_text(encoding="utf-8", errors="replace")
            if a.artifact_type == "cobol":
                prog = cobol.program_id(text)
                if not prog:
                    continue
                store.insert_program(conn, Program(
                    program_id=prog, program_name=prog, language="cobol",
                    artifact_id=a.artifact_id, line_count=a.line_count, evidence=a.evidence))
                for e in cobol.extract_edges(text, prog, a.path):
                    store.insert_edge(conn, e)
            elif a.artifact_type == "jcl":
                job, steps, edges = jcl.parse_jcl(text, a.artifact_id, a.path)
                if not job:
                    continue
                store.insert_job(conn, job)
                for s in steps:
                    store.insert_job_step(conn, s)
                for e in edges:
                    store.insert_edge(conn, e)
            elif a.artifact_type == "cics":
                for e in cics_csd.extract_edges(text, a.path):
                    store.insert_edge(conn, e)
        conn.commit()
        ref_edges = _all_edges(conn)
        conn.close()

        assert bulk_edges == ref_edges, (
            f"bulk-only: {bulk_edges - ref_edges}; per-row-only: {ref_edges - bulk_edges}")


def test_small_scale_timing_sanity():
    """~2k synthetic files load comfortably under a generous threshold (not flaky)."""
    src_dirs = [p for p in ("COBOL", "JCL", "CICS", "COPYLIB", "DB2")
                if (ESTATE / p).is_dir()]
    files_per_replica = sum(
        1 for d in src_dirs for f in (ESTATE / d).rglob("*") if f.is_file())
    replicas = max(1, 2000 // files_per_replica)   # ~2k files

    with tempfile.TemporaryDirectory() as d:
        estate = Path(d) / "estate"
        estate.mkdir()
        for i in range(replicas):
            for sd in src_dirs:
                shutil.copytree(ESTATE / sd, estate / f"rep{i:04d}" / sd)
        n_files = sum(1 for f in estate.rglob("*") if f.is_file())

        t0 = time.perf_counter()
        counts = build_db(estate, str(Path(d) / "mip.db"))
        elapsed = time.perf_counter() - t0

        assert n_files >= 1500, f"expected ~2k files, generated {n_files}"
        assert counts["programs"] == 12 * replicas
        # Generous ceiling: even slow CI disks load ~2k tiny files well under this.
        assert elapsed < 30.0, f"2k-file load took {elapsed:.1f}s (>30s ceiling)"


if __name__ == "__main__":
    test_counts_unchanged_on_sample_estate()
    test_bulk_load_matches_per_row_rows()
    test_small_scale_timing_sanity()
    print("ALL PERF CHECKS PASSED")
