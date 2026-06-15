"""Pipeline: scan -> parse (COBOL/JCL/CICS) -> SQLite store. Returns a summary.

At enterprise scale (180k+ files) two things dominate the wall clock: per-row INSERT
overhead and reading file content. So this pipeline:
  * loads under one transaction with bulk (executemany) writers and load-mode PRAGMAs,
    deferring the relationship indexes until after the bulk insert; and
  * reads a file's full text ONLY when its artifact_type is one MIP actually parses
    (cobol/jcl/cics). Everything else (copybook/db2/vsam/binary/unknown) is inventoried
    from the Artifact alone — no second full read, no parse.

Behavior is unchanged: same rows, same edges, same counts as the per-row path.
"""

from __future__ import annotations

from pathlib import Path

from . import cics_csd, cobol, jcl, scanner, store
from .records import Program

# artifact_types whose source we actually parse; everything else is inventory-only.
_PARSED_TYPES = {"cobol", "jcl", "cics"}


def build_db(estate_path: str | Path, db_path: str | Path) -> dict:
    estate = Path(estate_path)
    conn = store.connect(db_path, load_mode=True)
    counts = {"artifacts": 0, "programs": 0, "jobs": 0, "steps": 0,
              "edges": 0, "needs_review_edges": 0, "inferred_edges": 0, "by_type": {}}

    artifacts = scanner.scan(estate)
    writer = store.BatchWriter(conn)
    for a in artifacts:
        writer.add_artifact(a)
        counts["artifacts"] += 1
        counts["by_type"][a.artifact_type] = counts["by_type"].get(a.artifact_type, 0) + 1

        # Only parsed types need their content; skip the read for everything else.
        if a.artifact_type not in _PARSED_TYPES:
            continue
        text = (estate / a.path).read_text(encoding="utf-8", errors="replace")

        if a.artifact_type == "cobol":
            prog = cobol.program_id(text)
            if not prog:
                continue
            writer.add_program(Program(
                program_id=prog, program_name=prog, language="cobol",
                artifact_id=a.artifact_id, line_count=a.line_count,
                evidence=a.evidence))
            counts["programs"] += 1
            for e in cobol.extract_edges(text, prog, a.path):
                writer.add_edge(e)
                counts["edges"] += 1
                if e.evidence.validation_status == "needs_review":
                    counts["needs_review_edges"] += 1
                elif e.evidence.validation_status == "inferred":
                    counts["inferred_edges"] += 1

        elif a.artifact_type == "jcl":
            job, steps, edges = jcl.parse_jcl(text, a.artifact_id, a.path)
            if not job:
                continue
            writer.add_job(job)
            counts["jobs"] += 1
            for s in steps:
                writer.add_job_step(s)
                counts["steps"] += 1
            for e in edges:
                writer.add_edge(e)
                counts["edges"] += 1

        elif a.artifact_type == "cics":          # CSD/RDO: transaction -> program
            for e in cics_csd.extract_edges(text, a.path):
                writer.add_edge(e)
                counts["edges"] += 1

    writer.close()
    store.create_relationship_indexes(conn)      # deferred: build once, after the rows land
    conn.commit()
    conn.close()
    return counts
