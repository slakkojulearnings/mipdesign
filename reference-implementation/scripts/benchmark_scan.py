"""Benchmark the MIP scan -> load pipeline at scale.

Generates a synthetic estate by replicating the sample COBOL/JCL/CICS/copybook/DB2
members N times into a temp dir, then times build_db end-to-end and reports
files/sec, total seconds, and rows inserted.

It also isolates the STORE-layer speedup by re-running the load two ways over the same
scanned+parsed artifacts: the new bulk path (one transaction + executemany + load PRAGMAs
+ deferred indexes) vs a legacy per-row path (per-statement INSERT with default PRAGMAs).
This is a tool, not a test — it just runs and prints a summary.

Usage:
    uv run python scripts/benchmark_scan.py [N] [--no-store-compare]

N is the number of replicas of the sample estate (default 1000, ~24 files each
=> ~24k files). Use a smaller N for a quick smoke run.
"""

from __future__ import annotations

import shutil
import sys
import tempfile
import time
from pathlib import Path

_SRC = Path(__file__).resolve().parent.parent / "src"
sys.path.insert(0, str(_SRC))

from mip import cics_csd, cobol, jcl, scanner, store  # noqa: E402
from mip.pipeline import build_db                       # noqa: E402
from mip.records import Program                          # noqa: E402

SAMPLE = Path(__file__).resolve().parent.parent / "sample_estate"


def make_estate(dst: Path, replicas: int) -> int:
    """Replicate the sample source members `replicas` times under dst/repNNN/.

    Returns the number of files written. Each replica is a full copy of the sample's
    source directories (COBOL/JCL/CICS/COPYLIB/DB2) so the type mix mirrors reality.
    """
    src_dirs = [p for p in ("COBOL", "JCL", "CICS", "COPYLIB", "DB2")
                if (SAMPLE / p).is_dir()]
    count = 0
    for i in range(replicas):
        base = dst / f"rep{i:05d}"
        for d in src_dirs:
            target = base / d
            shutil.copytree(SAMPLE / d, target)
            count += sum(1 for f in target.rglob("*") if f.is_file())
    return count


def _scan_and_parse(estate: Path):
    """Scan + parse once, returning the records the store would receive.

    Mirrors pipeline.build_db's extraction (including the skip-read for non-parsed types)
    so the store-layer comparison loads identical rows both ways.
    """
    parsed_types = {"cobol", "jcl", "cics"}
    artifacts = scanner.scan(estate)
    programs, jobs, steps, edges = [], [], [], []
    for a in artifacts:
        if a.artifact_type not in parsed_types:
            continue
        text = (estate / a.path).read_text(encoding="utf-8", errors="replace")
        if a.artifact_type == "cobol":
            prog = cobol.program_id(text)
            if not prog:
                continue
            programs.append(Program(program_id=prog, program_name=prog, language="cobol",
                                    artifact_id=a.artifact_id, line_count=a.line_count,
                                    evidence=a.evidence))
            edges.extend(cobol.extract_edges(text, prog, a.path))
        elif a.artifact_type == "jcl":
            job, st, ed = jcl.parse_jcl(text, a.artifact_id, a.path)
            if not job:
                continue
            jobs.append(job)
            steps.extend(st)
            edges.extend(ed)
        elif a.artifact_type == "cics":
            edges.extend(cics_csd.extract_edges(text, a.path))
    return artifacts, programs, jobs, steps, edges


def _load_bulk(db_path: Path, recs) -> float:
    artifacts, programs, jobs, steps, edges = recs
    t0 = time.perf_counter()
    conn = store.connect(db_path, load_mode=True)
    with store.BatchWriter(conn) as w:
        for a in artifacts:
            w.add_artifact(a)
        for p in programs:
            w.add_program(p)
        for j in jobs:
            w.add_job(j)
        for s in steps:
            w.add_job_step(s)
        for e in edges:
            w.add_edge(e)
    store.create_relationship_indexes(conn)
    conn.commit()
    conn.close()
    return time.perf_counter() - t0


def _load_per_row(db_path: Path, recs) -> float:
    artifacts, programs, jobs, steps, edges = recs
    t0 = time.perf_counter()
    conn = store.connect(db_path, load_mode=False)   # default PRAGMAs (the old path)
    for a in artifacts:
        store.insert_artifact(conn, a)
    for p in programs:
        store.insert_program(conn, p)
    for j in jobs:
        store.insert_job(conn, j)
    for s in steps:
        store.insert_job_step(conn, s)
    for e in edges:
        store.insert_edge(conn, e)
    conn.commit()
    conn.close()
    return time.perf_counter() - t0


def _row_total(recs) -> int:
    return sum(len(x) for x in recs)


def main() -> None:
    args = [a for a in sys.argv[1:] if a != "--no-store-compare"]
    store_compare = "--no-store-compare" not in sys.argv[1:]
    replicas = int(args[0]) if args else 1000

    with tempfile.TemporaryDirectory(prefix="mip_bench_") as d:
        tmp = Path(d)
        estate = tmp / "estate"
        estate.mkdir()

        print(f"Generating synthetic estate: {replicas} replicas of sample_estate ...")
        t0 = time.perf_counter()
        n_files = make_estate(estate, replicas)
        gen_s = time.perf_counter() - t0
        print(f"  {n_files} files generated in {gen_s:.2f}s")

        # End-to-end pipeline (scan -> parse -> bulk load).
        print("\n[end-to-end] build_db (scan + parse + bulk load) ...")
        t0 = time.perf_counter()
        counts = build_db(estate, tmp / "e2e.db")
        e2e_s = time.perf_counter() - t0
        rows = (counts["artifacts"] + counts["programs"] + counts["jobs"]
                + counts["steps"] + counts["edges"])
        print(f"  files            : {n_files}")
        print(f"  total seconds    : {e2e_s:.2f}s")
        print(f"  files/sec        : {n_files / e2e_s:,.0f}")
        print(f"  rows inserted    : {rows:,} "
              f"(artifacts={counts['artifacts']:,} programs={counts['programs']:,} "
              f"jobs={counts['jobs']:,} steps={counts['steps']:,} edges={counts['edges']:,})")
        print(f"  by_type          : {counts['by_type']}")

        if store_compare:
            print("\n[store layer] bulk vs per-row over identical scanned+parsed rows ...")
            recs = _scan_and_parse(estate)
            total_rows = _row_total(recs)
            bulk_s = _load_bulk(tmp / "bulk.db", recs)
            perrow_s = _load_per_row(tmp / "perrow.db", recs)
            speedup = perrow_s / bulk_s if bulk_s else float("inf")
            print(f"  store rows       : {total_rows:,}")
            print(f"  per-row load     : {perrow_s:.2f}s  ({total_rows / perrow_s:,.0f} rows/s)")
            print(f"  bulk load        : {bulk_s:.2f}s  ({total_rows / bulk_s:,.0f} rows/s)")
            print(f"  INSERT SPEEDUP   : {speedup:.1f}x")


if __name__ == "__main__":
    main()
