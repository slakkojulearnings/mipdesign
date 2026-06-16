"""COBOL extraction — thin layer over the grammar-based parser (cobol_ast).

Turns a parsed Unit into MIP relationships + the structure/lineage the platform uses.
Dynamic CALLs resolved by constant propagation become `inferred` edges (not dropped,
not asserted); truly unresolved ones stay `needs_review`.
"""

from __future__ import annotations

from . import cobol_ast, parser_backend
from .records import Edge, Evidence


def program_id(text: str) -> str | None:
    return parser_backend.parse(text).program_id


def structure(text: str) -> dict:
    u = parser_backend.parse(text)
    return {"divisions": u.divisions, "paragraphs": u.paragraphs,
            "counts": u.counts, "complexity": u.complexity}


def extract_edges(text: str, program: str, rel_path: str, resolver=None) -> list[Edge]:
    u = parser_backend.parse(text, resolver=resolver)
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
    """Field-level data lineage: MOVE/COMPUTE/ADD field->field and SQL host-var <-> column."""
    u = parser_backend.parse(text)
    return [{"program": program, "src": f["src"], "dst": f["dst"],
             "kind": f["kind"], "evidence": f"{rel_path}:{f['line']}"}
            for f in u.field_flows]


def business_rules(text: str, program: str, rel_path: str) -> list[dict]:
    """Rule-bearing PROCEDURE DIVISION logic (IF / EVALUATE WHEN / COMPUTE).

    The raw condition + its source line are confirmed facts; the kind classification and
    plain-English rendering are interpretation (flagged `inferred`). See cobol_ast.
    """
    return cobol_ast.business_rules(text, program, rel_path)


def program_spec(text: str, program: str, rel_path: str) -> dict:
    """Granular, developer-grade spec of one program — detailed enough to re-implement it,
    with every fact tied to source. Deterministic (uses the canonical grammar parser):

      data_structures : record layouts grouped by DATA DIVISION section (level/name/PIC)
      procedure_outline: per-paragraph step list (verb + source line) ≈ pseudocode
      io               : tables read/written, copybooks used, programs called
      rules            : business rules, each with its real source snippet + typed fields

    Conditions/snippets/line numbers are confirmed; rule kind + plain-English statement are
    inferred (carried through from business_rules)."""
    u = cobol_ast.parse(text)
    pic = {d["name"]: d["pic"] for d in u.data_items}
    rules = cobol_ast.business_rules(text, program, rel_path)
    for r in rules:
        ln = int(r["source_evidence"].rsplit(":", 1)[-1])
        r["snippet"] = cobol_ast.snippet(text, ln)
        r["typed_fields"] = [{"name": f, "pic": pic.get(f)} for f in r["fields"]]
    return {
        "program": program,
        "complexity": u.complexity,
        "data_structures": cobol_ast.data_layout(u.data_items),
        "procedure_outline": cobol_ast.procedure_outline(text),
        "io": {
            "reads": sorted({s["table"] for s in u.sql if s["op"] == "READS"}),
            "writes": sorted({s["table"] for s in u.sql if s["op"] == "WRITES"}),
            "copybooks": sorted({c["name"] for c in u.copies}),
            "calls": [{"target": c["target"], "validation": c["validation"], "via": c.get("via")}
                      for c in u.calls],
        },
        "rules": rules,
    }


# CICS rel -> the conventional online interaction verb shown in the diagram.
_CICS_VERB = {"CALLS": "LINK", "READS": "READS", "WRITES": "WRITES", "USES": "USES",
              "STARTS": "STARTS"}


def sequence(text: str, program: str) -> dict:
    """Mermaid sequenceDiagram of a program's interactions, in SOURCE-LINE ORDER.

    Merges the program's CALLs, embedded SQL, and EXEC CICS commands sorted by line and
    renders each as a message from the program to its distinct target. With no
    interactions, returns a minimal valid diagram declaring just the program participant.
    """
    u = parser_backend.parse(text)
    pid = (program or u.program_id or "PROGRAM").upper()

    events: list[tuple[int, str, str]] = []   # (line, target, label)
    for c in u.calls:
        target = c["target"].upper()
        label = "CALL"
        if c.get("validation") == "needs_review":
            label += " (dynamic)"
        elif c.get("kind") == "resolved":
            label += " (resolved)"
        events.append((c["line"], target, label))
    for s in u.sql:
        events.append((s["line"], s["table"].upper(), f"SQL {s['op']}"))
    for cx in u.cics:
        events.append((cx["line"], cx["target"].upper(),
                       f"CICS {_CICS_VERB.get(cx['rel'], cx['rel'])}"))

    events.sort(key=lambda e: e[0])

    participants = [pid]
    for _, target, _ in events:
        if target not in participants:
            participants.append(target)

    lines = ["sequenceDiagram"]
    for p in participants:
        lines.append(f"    participant {p}")
    for _, target, label in events:
        lines.append(f"    {pid}->>{target}: {label}")

    return {"program_id": pid, "participants": participants, "mermaid": "\n".join(lines)}
