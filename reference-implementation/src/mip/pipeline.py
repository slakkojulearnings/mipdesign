"""Pipeline: scan -> parse (COBOL/JCL) -> SQLite store. Returns a summary."""

from __future__ import annotations

from pathlib import Path

from . import cics_csd, cobol, jcl, scanner, store
from .records import Program


def build_db(estate_path: str | Path, db_path: str | Path) -> dict:
    estate = Path(estate_path)
    conn = store.connect(db_path)
    counts = {"artifacts": 0, "programs": 0, "jobs": 0, "steps": 0,
              "edges": 0, "needs_review_edges": 0, "by_type": {}}

    artifacts = scanner.scan(estate)
    for a in artifacts:
        store.insert_artifact(conn, a)
        counts["artifacts"] += 1
        counts["by_type"][a.artifact_type] = counts["by_type"].get(a.artifact_type, 0) + 1
        text = (estate / a.path).read_text(encoding="utf-8", errors="replace")

        if a.artifact_type == "cobol":
            prog = cobol.program_id(text)
            if not prog:
                continue
            store.insert_program(conn, Program(
                program_id=prog, program_name=prog, language="cobol",
                artifact_id=a.artifact_id, line_count=a.line_count,
                evidence=a.evidence))
            counts["programs"] += 1
            for e in cobol.extract_edges(text, prog, a.path):
                store.insert_edge(conn, e)
                counts["edges"] += 1
                if e.evidence.validation_status == "needs_review":
                    counts["needs_review_edges"] += 1

        elif a.artifact_type == "jcl":
            job, steps, edges = jcl.parse_jcl(text, a.artifact_id, a.path)
            if not job:
                continue
            store.insert_job(conn, job)
            counts["jobs"] += 1
            for s in steps:
                store.insert_job_step(conn, s)
                counts["steps"] += 1
            for e in edges:
                store.insert_edge(conn, e)
                counts["edges"] += 1

        elif a.artifact_type == "cics":          # CSD/RDO: transaction -> program
            for e in cics_csd.extract_edges(text, a.path):
                store.insert_edge(conn, e)
                counts["edges"] += 1

    conn.commit()
    conn.close()
    return counts
