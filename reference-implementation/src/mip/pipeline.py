"""Pipeline: scan -> parse (COBOL/JCL/CICS) -> SQLite store. Returns a summary.

At enterprise scale (180k+ files) two things dominate the wall clock: per-row INSERT
overhead and reading + parsing file content. So this pipeline:
  * loads under one transaction with bulk (executemany) writers and load-mode PRAGMAs,
    deferring the relationship indexes until after the bulk insert;
  * reads a file's full text ONLY when its artifact_type is one MIP actually parses
    (cobol/jcl/cics). Everything else (copybook/db2/vsam/binary/unknown) is inventoried
    from the Artifact alone — no second full read, no parse; and
  * parses the read-heavy parsed types ACROSS CPU CORES via a process pool, while every
    SQLite write stays single-threaded in this (main) process — SQLite has no safe
    concurrent-writer model, so only the parse (pure CPU/IO) is parallelized.

Determinism: SQLite is the single writer and results are written back in the scanner's
artifact order (not completion order), so the rows/edges/counts are identical to the
serial path regardless of how the pool schedules work. Behavior — same rows, same edges,
same counts — is therefore unchanged whether the serial or parallel path runs.
"""

from __future__ import annotations

import concurrent.futures
import os
from pathlib import Path

from . import parse_worker, scanner, store

# artifact_types whose source we actually parse; everything else is inventory-only.
_PARSED_TYPES = {"cobol", "jcl", "cics"}

# Below this many parsed files the process-pool fixed costs (spawn + pickling) outweigh
# the parse work, so we stay serial. Tunable, but small scans should never pay for a pool.
_PARALLEL_MIN_FILES = 200


def _worker_count() -> int:
    """Workers to use: MIP_WORKERS if set (and valid), else os.cpu_count() (>=1)."""
    env = os.environ.get("MIP_WORKERS")
    if env:
        try:
            return max(1, int(env))
        except ValueError:
            pass
    return os.cpu_count() or 1


def _write_result(result: dict, writer: store.BatchWriter, counts: dict) -> None:
    """Write one parsed artifact's records and update counts.

    `result` is the dict shape produced by parse_worker.parse_one (also built inline by
    the serial path). This is the SINGLE place rows/edges/counts are derived from a parse
    result, so the serial and parallel paths are provably identical. Called only in the
    main process, in scanner order — so counts accumulate deterministically.
    """
    kind = result["kind"]
    if kind == "cobol":
        prog = result["program"]
        if prog is None:
            return
        writer.add_program(prog)
        counts["programs"] += 1
        for e in result["edges"]:
            writer.add_edge(e)
            counts["edges"] += 1
            if e.evidence.validation_status == "needs_review":
                counts["needs_review_edges"] += 1
            elif e.evidence.validation_status == "inferred":
                counts["inferred_edges"] += 1

    elif kind == "jcl":
        job = result["job"]
        if job is None:
            return
        writer.add_job(job)
        counts["jobs"] += 1
        for s in result["steps"]:
            writer.add_job_step(s)
            counts["steps"] += 1
        for e in result["edges"]:
            writer.add_edge(e)
            counts["edges"] += 1

    elif kind == "cics":
        for e in result["edges"]:
            writer.add_edge(e)
            counts["edges"] += 1


def _parse_one_serial(estate: Path, a) -> dict:
    """Serial in-process parse of one parsed-type artifact (no pool).

    Reads + parses in this process and returns the same dict shape as the worker, so it
    flows through the identical `_write_result`. Used for the serial path and as the
    fallback when a pool is not warranted (small scan / single worker / pool failure).
    """
    return parse_worker.parse_one(
        str(estate), a.path, a.artifact_type, a.artifact_id, a.line_count, a.evidence)


def build_db(estate_path: str | Path, db_path: str | Path) -> dict:
    estate = Path(estate_path)
    conn = store.connect(db_path, load_mode=True)
    counts = {"artifacts": 0, "programs": 0, "jobs": 0, "steps": 0,
              "edges": 0, "needs_review_edges": 0, "inferred_edges": 0, "by_type": {}}

    artifacts = scanner.scan(estate)
    writer = store.BatchWriter(conn)

    # Pass 1: write every artifact row (single writer) and split out the parsed types.
    # Artifacts are kept in scanner order so the parse results can be written back in
    # that same deterministic order regardless of pool completion order.
    parsed = []
    for a in artifacts:
        writer.add_artifact(a)
        counts["artifacts"] += 1
        counts["by_type"][a.artifact_type] = counts["by_type"].get(a.artifact_type, 0) + 1
        if a.artifact_type in _PARSED_TYPES:
            parsed.append(a)

    # Pass 2: parse the parsed types and write their records (still single writer).
    workers = _worker_count()
    use_pool = workers > 1 and len(parsed) >= _PARALLEL_MIN_FILES
    results = None
    if use_pool:
        results = _parse_parallel(estate, parsed, workers)
        # results is None if the pool failed to start -> fall back to serial below.

    if results is not None:
        for result in results:               # already in scanner (parsed) order
            _write_result(result, writer, counts)
    else:
        for a in parsed:                      # serial path (also the fallback)
            _write_result(_parse_one_serial(estate, a), writer, counts)

    writer.close()
    store.create_relationship_indexes(conn)      # deferred: build once, after the rows land
    conn.commit()
    conn.close()
    return counts


def _parse_parallel(estate: Path, parsed: list, workers: int):
    """Parse the parsed-type artifacts across `workers` processes.

    Returns the parse-result dicts in the SAME order as `parsed` (scanner order), so the
    caller writes them deterministically. Returns None if the pool can't start (e.g. a
    constrained/sandboxed environment) so the caller can fall back to the serial path.

    The executor is created here (never at module import) so importing this module has no
    side effects and Windows-spawn workers re-import cleanly.
    """
    futures_in_order = []
    try:
        ex = concurrent.futures.ProcessPoolExecutor(max_workers=workers)
    except (OSError, ValueError, NotImplementedError):
        return None
    try:
        with ex:
            for a in parsed:
                futures_in_order.append(ex.submit(
                    parse_worker.parse_one, str(estate), a.path, a.artifact_type,
                    a.artifact_id, a.line_count, a.evidence))
            # Resolve in submission (= scanner) order; .result() blocks per future but the
            # pool runs them concurrently, so total wall time is still parallelized.
            return [f.result() for f in futures_in_order]
    except (OSError, concurrent.futures.process.BrokenProcessPool):
        return None
