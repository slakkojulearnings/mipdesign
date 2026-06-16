"""Picklable parse worker for the parallel pipeline.

This module is imported in BOTH the main process and every worker process. On
Windows (spawn start method) a worker re-imports this module from scratch, so all
mip dependencies are imported at module top level and the entry point `parse_one`
is a plain top-level function — both required for the function and its results to
pickle and for the worker to start cleanly.

`parse_one` does the CPU/IO-heavy part (read the file + parse it) inside the worker
and returns plain, picklable records (module-level dataclasses from `records`). The
MAIN process turns these into store writes; no SQLite handle ever crosses a process
boundary. The returned shapes mirror exactly what pipeline.build_db would build on
the serial path, so the written rows/edges/counts are byte-for-byte identical.
"""

from __future__ import annotations

from pathlib import Path

from . import antlr_adapter, cics_csd, cobol, jcl, parser_backend
from .records import Program


def parse_one(estate_str: str, rel_path: str, artifact_type: str,
              artifact_id: str, line_count, evidence) -> dict:
    """Read + parse a single parsed-type artifact in a worker process.

    Returns a dict tagged by `kind`. The `rel` key lets the main process write
    results back in deterministic (scanner) order regardless of completion order.

      cobol -> {"kind":"cobol","rel":rel,"program":Program|None,"edges":[Edge,...]}
      jcl   -> {"kind":"jcl","rel":rel,"job":Job|None,"steps":[JobStep,...],"edges":[Edge,...]}
      cics  -> {"kind":"cics","rel":rel,"edges":[Edge,...]}

    `program`/`job` are None when the parser found no PROGRAM-ID/JOB card (the serial
    path `continue`s in that case — the main process mirrors that by skipping).
    The dataclasses (Program/Job/JobStep/Edge + their Evidence) are module-level and
    pickle cleanly, so they are returned as-is and written unchanged in the main process.
    """
    text = (Path(estate_str) / rel_path).read_text(encoding="utf-8", errors="replace")

    if artifact_type == "cobol":
        prog = cobol.program_id(text)
        if not prog:
            return {"kind": "cobol", "rel": rel_path, "program": None, "edges": []}
        program = Program(
            program_id=prog, program_name=prog, language="cobol",
            artifact_id=artifact_id, line_count=line_count, evidence=evidence)
        # advanced backend: give it a copybook resolver so COPY ... REPLACING expands from
        # the estate's COPYLIB and facts hidden in copybooks are recovered. (default ignores it)
        resolver = (antlr_adapter.default_resolver(Path(estate_str))
                    if parser_backend.effective() == "advanced" else None)
        edges = cobol.extract_edges(text, prog, rel_path, resolver=resolver)
        return {"kind": "cobol", "rel": rel_path, "program": program, "edges": edges}

    if artifact_type == "jcl":
        job, steps, edges = jcl.parse_jcl(text, artifact_id, rel_path)
        if not job:
            return {"kind": "jcl", "rel": rel_path, "job": None, "steps": [], "edges": []}
        return {"kind": "jcl", "rel": rel_path, "job": job, "steps": steps, "edges": edges}

    # cics — CSD/RDO: transaction -> program
    edges = cics_csd.extract_edges(text, rel_path)
    return {"kind": "cics", "rel": rel_path, "edges": edges}
