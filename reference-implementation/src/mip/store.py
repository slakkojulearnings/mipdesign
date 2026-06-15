"""SQLite store — creates the schema and persists entities + relationships.

Uses the packaged schema.sql (mirror of ../../01-metadata-model/schema.sql). Every row
carries the evidence envelope columns.

For enterprise-scale loads (180k+ files) the per-row helpers below are too slow because
every INSERT pays statement + (by default) fsync overhead. The pipeline therefore drives
the *bulk* path: a single transaction, `executemany` writers, and load-mode PRAGMAs
(`connect(..., load_mode=True)`). The per-row helpers are kept for compatibility.
"""

from __future__ import annotations

import sqlite3
from pathlib import Path

from .records import Artifact, Edge, Job, JobStep, Program

_SCHEMA = Path(__file__).with_name("schema.sql")

# Relationship indexes are the only ones large enough to matter on a bulk load.
# Creating them AFTER the rows are inserted (rather than maintaining them per-INSERT)
# is a clear win at scale. They are defined here, by name, so schema.sql stays the
# single owner of the table DDL — we only re-issue the (idempotent) CREATE INDEX.
_DEFERRABLE_REL_INDEXES = (
    "CREATE INDEX IF NOT EXISTS idx_rel_type   ON relationship(rel_type)",
    "CREATE INDEX IF NOT EXISTS idx_rel_source ON relationship(source_type, source_id)",
    "CREATE INDEX IF NOT EXISTS idx_rel_target ON relationship(target_type, target_id)",
    "CREATE INDEX IF NOT EXISTS idx_rel_validation ON relationship(validation_status)",
)


def connect(db_path: str | Path, load_mode: bool = False) -> sqlite3.Connection:
    """Open a connection and ensure the schema exists.

    load_mode=True applies bulk-load PRAGMAs tuned for one big ingest. Note
    `synchronous=OFF` trades crash-durability for speed: it is safe for a (re)build of a
    derived/disposable analysis DB, which is exactly the scan->load case. For a long-lived
    DB serving queries, use the default (load_mode=False) which keeps SQLite's defaults.
    """
    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row
    if load_mode:
        # WAL + no fsync + in-memory temp + larger page cache (~64 MB).
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA synchronous=OFF")     # load-phase only (durability traded for speed)
        conn.execute("PRAGMA temp_store=MEMORY")
        conn.execute("PRAGMA cache_size=-65536")
    conn.executescript(_SCHEMA.read_text(encoding="utf-8"))
    return conn


def create_relationship_indexes(conn: sqlite3.Connection) -> None:
    """(Re)create the relationship indexes — call after a bulk insert when deferred."""
    for ddl in _DEFERRABLE_REL_INDEXES:
        conn.execute(ddl)


def _ev(e) -> tuple:
    return (e.source_evidence, e.discovery_method, e.confidence,
            e.validation_status, e.discovered_at)


# ---------------------------------------------------------------------------
# Per-row helpers (kept for compatibility / small loads)
# ---------------------------------------------------------------------------

def insert_artifact(conn: sqlite3.Connection, a: Artifact) -> None:
    conn.execute(_SQL_ARTIFACT, _row_artifact(a))


def insert_program(conn: sqlite3.Connection, p: Program) -> None:
    conn.execute(_SQL_PROGRAM, _row_program(p))


def insert_job(conn: sqlite3.Connection, j: Job) -> None:
    conn.execute(_SQL_JOB, _row_job(j))


def insert_job_step(conn: sqlite3.Connection, s: JobStep) -> None:
    conn.execute(_SQL_JOB_STEP, _row_job_step(s))


def insert_edge(conn: sqlite3.Connection, e: Edge) -> None:
    conn.execute(_SQL_EDGE, _row_edge(e))


def insert_runtime_metric(conn: sqlite3.Connection, entity_type: str, entity_id: str,
                          exec_count, last_run, avg_elapsed_ms, window: str,
                          source_evidence: str, discovered_at: str) -> None:
    """Upsert one observed runtime metric (keyed by entity + window)."""
    conn.execute(
        "INSERT OR REPLACE INTO runtime_metric (entity_type, entity_id, exec_count,"
        " last_run, avg_elapsed_ms, window, source_evidence, discovered_at)"
        " VALUES (?,?,?,?,?,?,?,?)",
        (entity_type, entity_id, exec_count, last_run, avg_elapsed_ms, window,
         source_evidence, discovered_at),
    )


# ---------------------------------------------------------------------------
# Bulk helpers — same rows as the per-row path, written via executemany.
# Each *_many takes an iterable of records and issues a single executemany.
# ---------------------------------------------------------------------------

_SQL_ARTIFACT = (
    "INSERT OR REPLACE INTO artifact (artifact_id, path, artifact_type, file_name,"
    " size_bytes, line_count, source_evidence, discovery_method, confidence,"
    " validation_status, discovered_at) VALUES (?,?,?,?,?,?,?,?,?,?,?)"
)
_SQL_PROGRAM = (
    "INSERT OR REPLACE INTO program (program_id, program_name, language, artifact_id,"
    " line_count, source_evidence, discovery_method, confidence, validation_status,"
    " discovered_at) VALUES (?,?,?,?,?,?,?,?,?,?)"
)
_SQL_JOB = (
    "INSERT OR REPLACE INTO job (job_id, job_name, artifact_id, source_evidence,"
    " discovery_method, confidence, validation_status, discovered_at)"
    " VALUES (?,?,?,?,?,?,?,?)"
)
_SQL_JOB_STEP = (
    "INSERT OR REPLACE INTO job_step (step_id, job_id, step_name, program_name,"
    " step_order, source_evidence, discovery_method, confidence, validation_status,"
    " discovered_at) VALUES (?,?,?,?,?,?,?,?,?,?)"
)
_SQL_EDGE = (
    "INSERT OR REPLACE INTO relationship (relationship_id, source_type, source_id,"
    " rel_type, target_type, target_id, source_evidence, discovery_method, confidence,"
    " validation_status, discovered_at) VALUES (?,?,?,?,?,?,?,?,?,?,?)"
)


def _row_artifact(a: Artifact) -> tuple:
    return (a.artifact_id, a.path, a.artifact_type, a.file_name, a.size_bytes,
            a.line_count, *_ev(a.evidence))


def _row_program(p: Program) -> tuple:
    return (p.program_id, p.program_name, p.language, p.artifact_id, p.line_count,
            *_ev(p.evidence))


def _row_job(j: Job) -> tuple:
    return (j.job_id, j.job_name, j.artifact_id, *_ev(j.evidence))


def _row_job_step(s: JobStep) -> tuple:
    return (s.step_id, s.job_id, s.step_name, s.program_name, s.step_order, *_ev(s.evidence))


def _row_edge(e: Edge) -> tuple:
    return (e.relationship_id, e.source_type, e.source_id, e.rel_type, e.target_type,
            e.target_id, *_ev(e.evidence))


def insert_artifacts_many(conn: sqlite3.Connection, rows) -> None:
    conn.executemany(_SQL_ARTIFACT, [_row_artifact(a) for a in rows])


def insert_programs_many(conn: sqlite3.Connection, rows) -> None:
    conn.executemany(_SQL_PROGRAM, [_row_program(p) for p in rows])


def insert_jobs_many(conn: sqlite3.Connection, rows) -> None:
    conn.executemany(_SQL_JOB, [_row_job(j) for j in rows])


def insert_job_steps_many(conn: sqlite3.Connection, rows) -> None:
    conn.executemany(_SQL_JOB_STEP, [_row_job_step(s) for s in rows])


def insert_edges_many(conn: sqlite3.Connection, rows) -> None:
    conn.executemany(_SQL_EDGE, [_row_edge(e) for e in rows])


class BatchWriter:
    """Buffered bulk writer: accumulate records and flush in batches via executemany.

    All writes go through one connection on the calling thread (SQLite forbids concurrent
    writers). flush()/close() are idempotent; use as a context manager to guarantee a
    final flush.
    """

    def __init__(self, conn: sqlite3.Connection, batch_size: int = 5000):
        self.conn = conn
        self.batch_size = batch_size
        self._buffers: dict[str, list] = {
            "artifact": [], "program": [], "job": [], "job_step": [], "edge": [],
        }
        self._flushers = {
            "artifact": insert_artifacts_many,
            "program": insert_programs_many,
            "job": insert_jobs_many,
            "job_step": insert_job_steps_many,
            "edge": insert_edges_many,
        }

    def _add(self, kind: str, rec) -> None:
        buf = self._buffers[kind]
        buf.append(rec)
        # Flush ALL buffers (artifact first) when any one fills, so we never strand a
        # program/job whose parent artifact is still buffered (FK enforcement is ON).
        if len(buf) >= self.batch_size:
            self.flush()

    def add_artifact(self, a: Artifact) -> None:
        self._add("artifact", a)

    def add_program(self, p: Program) -> None:
        self._add("program", p)

    def add_job(self, j: Job) -> None:
        self._add("job", j)

    def add_job_step(self, s: JobStep) -> None:
        self._add("job_step", s)

    def add_edge(self, e: Edge) -> None:
        self._add("edge", e)

    def _flush_kind(self, kind: str) -> None:
        buf = self._buffers[kind]
        if buf:
            self._flushers[kind](self.conn, buf)
            buf.clear()

    def flush(self) -> None:
        # artifact first (FK target of program/job), then the rest.
        for kind in ("artifact", "program", "job", "job_step", "edge"):
            self._flush_kind(kind)

    def close(self) -> None:
        self.flush()

    def __enter__(self) -> "BatchWriter":
        return self

    def __exit__(self, *exc) -> None:
        self.flush()
