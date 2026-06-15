"""Export the metadata store to portable formats for the frontend (downloads).

Three formats, all derived from the same evidence-carrying store so an export never
asserts more than the graph knows:
  - graphml : the call/execution graph (NetworkX), for graph tools (Gephi, yEd).
  - json    : a bundle {summary, programs, graph} reusing the existing queries.
  - csv     : a flat table of programs or relationships (kind=programs|edges).

graphml requires networkx (the `graph`/`api` extra).
"""

from __future__ import annotations

import csv
import io
import json as _json
import sqlite3

from . import graphx, queries


def graphml(conn: sqlite3.Connection) -> str:
    import networkx as nx

    g = graphx.build_graph(conn)
    return "\n".join(nx.generate_graphml(g))


def json_bundle(conn: sqlite3.Connection) -> str:
    bundle = {
        "summary": queries.summary(conn),
        "programs": queries.programs_overview(conn),
        "graph": queries.call_graph(conn),
    }
    return _json.dumps(bundle, indent=2)


def csv_programs(conn: sqlite3.Connection) -> str:
    buf = io.StringIO()
    w = csv.writer(buf)
    w.writerow(["program_id", "language", "line_count", "calls_out",
                "called_by", "is_root", "is_dead"])
    for p in queries.programs_overview(conn):
        w.writerow([p["program_id"], p["language"], p["line_count"], p["calls_out"],
                    p["called_by"], p["is_root"], p["is_dead"]])
    return buf.getvalue()


def csv_edges(conn: sqlite3.Connection) -> str:
    buf = io.StringIO()
    w = csv.writer(buf)
    w.writerow(["source_type", "source_id", "rel_type", "target_type", "target_id",
                "validation_status", "confidence", "source_evidence"])
    for r in conn.execute(
        "SELECT source_type, source_id, rel_type, target_type, target_id,"
        " validation_status, confidence, source_evidence FROM relationship"
        " ORDER BY source_id, rel_type, target_id"):
        w.writerow([r["source_type"], r["source_id"], r["rel_type"], r["target_type"],
                    r["target_id"], r["validation_status"], r["confidence"],
                    r["source_evidence"]])
    return buf.getvalue()
