"""SQLite store — creates the schema and persists entities + relationships.

Uses the packaged schema.sql (mirror of ../../01-metadata-model/schema.sql). Every row
carries the evidence envelope columns.
"""

from __future__ import annotations

import sqlite3
from pathlib import Path

from .records import Artifact, Edge, Job, JobStep, Program

_SCHEMA = Path(__file__).with_name("schema.sql")


def connect(db_path: str | Path) -> sqlite3.Connection:
    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row
    conn.executescript(_SCHEMA.read_text(encoding="utf-8"))
    return conn


def _ev(e) -> tuple:
    return (e.source_evidence, e.discovery_method, e.confidence,
            e.validation_status, e.discovered_at)


def insert_artifact(conn: sqlite3.Connection, a: Artifact) -> None:
    conn.execute(
        "INSERT OR REPLACE INTO artifact (artifact_id, path, artifact_type, file_name,"
        " size_bytes, line_count, source_evidence, discovery_method, confidence,"
        " validation_status, discovered_at) VALUES (?,?,?,?,?,?,?,?,?,?,?)",
        (a.artifact_id, a.path, a.artifact_type, a.file_name, a.size_bytes,
         a.line_count, *_ev(a.evidence)),
    )


def insert_program(conn: sqlite3.Connection, p: Program) -> None:
    conn.execute(
        "INSERT OR REPLACE INTO program (program_id, program_name, language, artifact_id,"
        " line_count, source_evidence, discovery_method, confidence, validation_status,"
        " discovered_at) VALUES (?,?,?,?,?,?,?,?,?,?)",
        (p.program_id, p.program_name, p.language, p.artifact_id, p.line_count, *_ev(p.evidence)),
    )


def insert_job(conn: sqlite3.Connection, j: Job) -> None:
    conn.execute(
        "INSERT OR REPLACE INTO job (job_id, job_name, artifact_id, source_evidence,"
        " discovery_method, confidence, validation_status, discovered_at)"
        " VALUES (?,?,?,?,?,?,?,?)",
        (j.job_id, j.job_name, j.artifact_id, *_ev(j.evidence)),
    )


def insert_job_step(conn: sqlite3.Connection, s: JobStep) -> None:
    conn.execute(
        "INSERT OR REPLACE INTO job_step (step_id, job_id, step_name, program_name,"
        " step_order, source_evidence, discovery_method, confidence, validation_status,"
        " discovered_at) VALUES (?,?,?,?,?,?,?,?,?,?)",
        (s.step_id, s.job_id, s.step_name, s.program_name, s.step_order, *_ev(s.evidence)),
    )


def insert_edge(conn: sqlite3.Connection, e: Edge) -> None:
    conn.execute(
        "INSERT OR REPLACE INTO relationship (relationship_id, source_type, source_id,"
        " rel_type, target_type, target_id, source_evidence, discovery_method, confidence,"
        " validation_status, discovered_at) VALUES (?,?,?,?,?,?,?,?,?,?,?)",
        (e.relationship_id, e.source_type, e.source_id, e.rel_type, e.target_type,
         e.target_id, *_ev(e.evidence)),
    )
