"""COBOL extraction — thin layer over the grammar-based parser (cobol_ast).

Turns a parsed Unit into MIP relationships + the structure/lineage the platform uses.
Dynamic CALLs resolved by constant propagation become `inferred` edges (not dropped,
not asserted); truly unresolved ones stay `needs_review`.
"""

from __future__ import annotations

from . import cobol_ast
from .records import Edge, Evidence


def program_id(text: str) -> str | None:
    return cobol_ast.parse(text).program_id


def structure(text: str) -> dict:
    u = cobol_ast.parse(text)
    return {"divisions": u.divisions, "paragraphs": u.paragraphs,
            "counts": u.counts, "complexity": u.complexity}


def extract_edges(text: str, program: str, rel_path: str) -> list[Edge]:
    u = cobol_ast.parse(text)
    edges: list[Edge] = []

    def add(rel, ttype, target, ev):
        edges.append(Edge.build("program", program, rel, ttype, target, ev))

    for c in u.calls:
        src = f"{rel_path}:{c['line']}"
        if c["validation"] == "confirmed":
            ev = Evidence.confirmed(src)
        elif c["kind"] == "resolved":          # dynamic CALL resolved via constant propagation
            ev = Evidence(source_evidence=src, discovery_method="inference",
                          confidence=c["confidence"], validation_status="inferred")
        else:                                   # dynamic, unresolved — kept + flagged
            ev = Evidence.needs_review(src, confidence=c["confidence"])
        add("CALLS", "program", c["target"], ev)

    for cp in u.copies:
        add("USES", "copybook", cp["name"], Evidence.confirmed(f"{rel_path}:{cp['line']}"))

    for s in u.sql:
        add(s["op"], "db2_table", s["table"], Evidence.confirmed(f"{rel_path}:{s['line']}"))

    for cx in u.cics:                               # online layer (EXEC CICS)
        src = f"{rel_path}:{cx['line']}"
        ev = Evidence(source_evidence=src, discovery_method="cics",
                      confidence=cx["confidence"], validation_status=cx["validation"])
        add(cx["rel"], cx["ttype"], cx["target"], ev)

    seen = {e.relationship_id: e for e in edges}   # dedupe identical edges
    return list(seen.values())


def field_lineage(text: str, program: str, rel_path: str) -> list[dict]:
    """Field-level data lineage: MOVE field->field and SQL host-var <-> column."""
    u = cobol_ast.parse(text)
    return [{"program": program, "src": f["src"], "dst": f["dst"],
             "kind": f["kind"], "evidence": f"{rel_path}:{f['line']}"}
            for f in u.field_flows]
