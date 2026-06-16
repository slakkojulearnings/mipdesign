"""Queries over the metadata store + a tiny natural-language router.

The reasoning here is intentionally SQL/Python over the graph edges — the LLM layer
(later) narrates these answers, it does not invent them.
"""

from __future__ import annotations

import re
import sqlite3


def all_programs(conn: sqlite3.Connection) -> list[str]:
    return [r["program_id"] for r in conn.execute("SELECT program_id FROM program")]


def jobs_executing(conn: sqlite3.Connection, program: str) -> list[str]:
    rows = conn.execute(
        "SELECT DISTINCT job_id FROM job_step WHERE program_name = ? ORDER BY job_id",
        (program.upper(),),
    )
    return [r["job_id"] for r in rows]


def program_calls(conn: sqlite3.Connection, program: str) -> list[dict]:
    rows = conn.execute(
        "SELECT target_id, validation_status, confidence FROM relationship"
        " WHERE source_id = ? AND rel_type = 'CALLS' ORDER BY target_id",
        (program.upper(),),
    )
    return [dict(r) for r in rows]


def program_dependencies(conn: sqlite3.Connection, program: str) -> list[dict]:
    rows = conn.execute(
        "SELECT rel_type, target_type, target_id, validation_status, confidence"
        " FROM relationship WHERE source_id = ? ORDER BY rel_type, target_id",
        (program.upper(),),
    )
    return [dict(r) for r in rows]


def callers(conn: sqlite3.Connection, program: str) -> list[dict]:
    rows = conn.execute(
        "SELECT source_id, rel_type, validation_status, confidence FROM relationship"
        " WHERE target_id = ? AND rel_type IN ('CALLS','EXECUTES','STARTS') ORDER BY source_id",
        (program.upper(),),
    )
    return [dict(r) for r in rows]


def roots(conn: sqlite3.Connection) -> list[str]:
    # batch roots: executed by a job. online roots: programs that issue EXEC CICS
    # (discovery_method='cics') — entered via a transaction, not a job. Either way, a
    # root is an entry point that nothing else calls.
    executed = {r["target_id"] for r in conn.execute(
        "SELECT target_id FROM relationship WHERE rel_type='EXECUTES' AND target_type='program'")}
    # online entry programs: issue EXEC CICS themselves, OR are the PROGRAM of a CSD
    # transaction (STARTS). Either is an entry point even with no EXEC CICS of its own.
    online = {r["source_id"] for r in conn.execute(
        "SELECT DISTINCT source_id FROM relationship WHERE discovery_method='cics'")}
    started = {r["target_id"] for r in conn.execute(
        "SELECT target_id FROM relationship WHERE rel_type='STARTS' AND target_type='program'")}
    called = {r["target_id"] for r in conn.execute(
        "SELECT target_id FROM relationship WHERE rel_type='CALLS'")}
    return sorted((executed | online | started) - called)


def dead_code(conn: sqlite3.Connection) -> list[str]:
    # reachability from roots over EXECUTES + CALLS (confirmed edges only)
    adj: dict[str, set[str]] = {}
    for r in conn.execute(
        "SELECT source_id, target_id FROM relationship"
        " WHERE rel_type IN ('EXECUTES','CALLS') AND validation_status='confirmed'"):
        adj.setdefault(r["source_id"], set()).add(r["target_id"])

    reachable: set[str] = set()
    stack = list(roots(conn))
    while stack:
        n = stack.pop()
        if n in reachable:
            continue
        reachable.add(n)
        stack.extend(adj.get(n, ()))
    return sorted(p for p in all_programs(conn) if p not in reachable)


def programs_overview(conn: sqlite3.Connection) -> list[dict]:
    """One row per program with quick flags for the UI table."""
    root_set = set(roots(conn))
    dead_set = set(dead_code(conn))
    out = []
    for r in conn.execute(
        "SELECT p.program_id, p.language, p.line_count, a.path AS source_path"
        " FROM program p LEFT JOIN artifact a ON a.artifact_id = p.artifact_id"
        " ORDER BY p.program_id"):
        pid = r["program_id"]
        calls_out = conn.execute(
            "SELECT COUNT(*) c FROM relationship WHERE source_id=? AND rel_type='CALLS'", (pid,)
        ).fetchone()["c"]
        called_by = len(callers(conn, pid))
        out.append({
            "program_id": pid, "language": r["language"], "line_count": r["line_count"],
            "source_path": r["source_path"], "calls_out": calls_out, "called_by": called_by,
            "is_root": pid in root_set, "is_dead": pid in dead_set,
        })
    return out


def jobs_overview(conn: sqlite3.Connection) -> list[dict]:
    out = []
    for j in conn.execute("SELECT job_id FROM job ORDER BY job_id"):
        steps = conn.execute(
            "SELECT step_name, program_name FROM job_step WHERE job_id=? ORDER BY step_order",
            (j["job_id"],),
        )
        out.append({"job_id": j["job_id"],
                    "steps": [{"step": s["step_name"], "program": s["program_name"]} for s in steps]})
    return out


def call_graph(conn: sqlite3.Connection) -> dict:
    """Nodes + edges for the call/execution graph view."""
    root_set = set(roots(conn))
    dead_set = set(dead_code(conn))
    nodes: dict[str, dict] = {}

    def add(node_id: str, ntype: str) -> None:
        if node_id not in nodes:
            nodes[node_id] = {"id": node_id, "type": ntype,
                              "is_root": node_id in root_set, "is_dead": node_id in dead_set}

    for p in all_programs(conn):
        add(p, "program")
    for j in conn.execute("SELECT job_id FROM job"):
        add(j["job_id"], "job")

    edges = []
    for r in conn.execute(
        "SELECT source_id, target_id, rel_type, validation_status, confidence,"
        " source_evidence, discovery_method"
        " FROM relationship WHERE rel_type IN ('CALLS','EXECUTES') ORDER BY source_id"):
        # target may be an unresolved/dynamic program name not in the program table
        add(r["target_id"], "program" if r["rel_type"] == "CALLS" else "program")
        edges.append({"source": r["source_id"], "target": r["target_id"],
                      "rel_type": r["rel_type"], "validation_status": r["validation_status"],
                      "confidence": r["confidence"],
                      "source_evidence": r["source_evidence"],
                      "discovery_method": r["discovery_method"]})
    return {"nodes": list(nodes.values()), "edges": edges}


def trace(conn: sqlite3.Connection, program: str, direction: str = "both",
          depth: int = 8, include_data: bool = True) -> dict:
    """Complete bidirectional call trace for a program.

    upstream   = who triggers it (reverse CALLS/EXECUTES/STARTS up to jobs/transactions)
    downstream = what it calls (CALLS) + the data it touches (READS/WRITES tables, USES
                 copybooks) when include_data is set.

    Returns BOTH a nested tree (per direction) and a flat node/edge list (for a graph view),
    with per-hop evidence (file:line) + confidence + validation_status. Dynamic/unresolved
    branches are kept and flagged (never dropped); cycles render as DAG nodes marked
    `repeated`. Confidence is per-edge; a path is only as strong as its weakest hop."""
    program = program.upper()
    control = ("CALLS", "EXECUTES", "STARTS")
    data = ("READS", "WRITES", "USES")
    rels = list(control) + (list(data) if include_data else [])
    ph = ",".join("?" * len(rels))

    fwd: dict[str, list] = {}
    rev: dict[str, list] = {}
    kind: dict[str, str] = {}
    for r in conn.execute(
        f"SELECT source_id, source_type, rel_type, target_id, target_type, confidence,"
        f" validation_status, source_evidence, discovery_method"
        f" FROM relationship WHERE rel_type IN ({ph})", rels):
        kind.setdefault(r["source_id"], r["source_type"])
        kind.setdefault(r["target_id"], r["target_type"])
        edge = {"rel": r["rel_type"], "confidence": r["confidence"],
                "validation_status": r["validation_status"],
                "evidence": r["source_evidence"], "method": r["discovery_method"]}
        fwd.setdefault(r["source_id"], []).append((r["target_id"], r["target_type"], edge))
        rev.setdefault(r["target_id"], []).append((r["source_id"], r["source_type"], edge))

    programs = {row["program_id"] for row in conn.execute("SELECT program_id FROM program")}
    if program in programs:
        kind[program] = "program"
    found = program in kind

    nodes: dict[str, str] = {}
    edge_keys: set = set()
    flat_edges: list[dict] = []

    def note(nid, k):
        nodes.setdefault(nid, k or kind.get(nid, "program"))

    def add_edge(src, tgt, tag, edge):
        key = (src, tgt, edge["rel"], tag)
        if key not in edge_keys:
            edge_keys.add(key)
            flat_edges.append({"source": src, "target": tgt, "direction": tag, **edge})

    note(program, kind.get(program, "program"))

    down_seen: set = set()
    def go_down(nid, d):
        node = {"id": nid, "kind": nodes.get(nid, kind.get(nid, "program")), "repeated": False, "children": []}
        if d <= 0:
            return node
        if nid in down_seen:
            node["repeated"] = True
            return node
        down_seen.add(nid)
        for tgt, ttype, edge in sorted(fwd.get(nid, []), key=lambda e: (e[2]["rel"], e[0])):
            note(tgt, ttype)
            add_edge(nid, tgt, "down", edge)
            child = (go_down(tgt, d - 1) if edge["rel"] == "CALLS"
                     else {"id": tgt, "kind": ttype, "repeated": False, "children": [], "leaf": True})
            node["children"].append({**edge, "node": child})
        return node

    up_seen: set = set()
    def go_up(nid, d):
        node = {"id": nid, "kind": nodes.get(nid, kind.get(nid, "program")), "repeated": False, "children": []}
        if d <= 0:
            return node
        if nid in up_seen:
            node["repeated"] = True
            return node
        up_seen.add(nid)
        for src, stype, edge in sorted(rev.get(nid, []), key=lambda e: (e[2]["rel"], e[0])):
            if edge["rel"] not in control:           # upstream is control-flow only
                continue
            note(src, stype)
            add_edge(src, nid, "up", edge)
            child = (go_up(src, d - 1) if stype == "program"
                     else {"id": src, "kind": stype, "repeated": False, "children": [], "leaf": True})
            node["children"].append({**edge, "node": child})
        return node

    downstream = go_down(program, depth) if direction in ("both", "down") else None
    upstream = go_up(program, depth) if direction in ("both", "up") else None

    unresolved = [e for e in flat_edges if e["validation_status"] != "confirmed"]
    return {
        "program": program, "found": found, "kind": kind.get(program, "program"),
        "direction": direction, "depth": depth, "include_data": include_data,
        "upstream": upstream, "downstream": downstream,
        "nodes": [{"id": k, "kind": v} for k, v in sorted(nodes.items())],
        "edges": flat_edges,
        "db_touchpoints": {
            "reads": sorted({e["target"] for e in flat_edges if e["rel"] == "READS"}),
            "writes": sorted({e["target"] for e in flat_edges if e["rel"] == "WRITES"}),
        },
        "stats": {"node_count": len(nodes), "edge_count": len(flat_edges),
                  "unresolved_count": len(unresolved),
                  "unresolved": [{"source": e["source"], "target": e["target"],
                                  "rel": e["rel"], "validation_status": e["validation_status"]}
                                 for e in unresolved]},
    }


def summary(conn: sqlite3.Connection) -> dict:
    def scalar(sql: str) -> int:
        return conn.execute(sql).fetchone()[0]
    by_type = {r["artifact_type"]: r["c"] for r in conn.execute(
        "SELECT artifact_type, COUNT(*) c FROM artifact GROUP BY artifact_type")}
    return {
        "artifacts": scalar("SELECT COUNT(*) FROM artifact"),
        "by_type": by_type,
        "programs": scalar("SELECT COUNT(*) FROM program"),
        "jobs": scalar("SELECT COUNT(*) FROM job"),
        "steps": scalar("SELECT COUNT(*) FROM job_step"),
        "edges": scalar("SELECT COUNT(*) FROM relationship"),
        "needs_review_edges": scalar(
            "SELECT COUNT(*) FROM relationship WHERE validation_status='needs_review'"),
        "inferred_edges": scalar(
            "SELECT COUNT(*) FROM relationship WHERE validation_status='inferred'"),
        "roots": len(roots(conn)),
        "dead_code": len(dead_code(conn)),
    }


# --- capabilities & functionality (inferred — Principle 1) ----------------
# Naming-convention dictionary used to label inferred capabilities/roles.
_CAP_TOKENS = {
    "CRD": "Card", "CARD": "Card", "PAY": "Payment", "STMT": "Statement",
    "INT": "Interest", "AUTH": "Authorization", "ACCT": "Account", "BAL": "Balance",
    "POST": "Posting", "UPD": "Update", "COMP": "Computation", "VAL": "Validation",
    "FMT": "Formatting", "GEN": "Generation", "PROC": "Processing", "CALC": "Calculation",
}


def _label(name: str) -> str:
    found = []
    for tok, word in _CAP_TOKENS.items():
        idx = name.find(tok)
        if idx >= 0:
            found.append((idx, word))
    found.sort()
    out, seen = [], set()
    for _, w in found:
        if w not in seen:
            seen.add(w); out.append(w)
    return " ".join(out) if out else name


def _reachable(conn: sqlite3.Connection, start: str, rels=("CALLS",)) -> set[str]:
    placeholders = ",".join(f"'{r}'" for r in rels)
    adj: dict[str, list[str]] = {}
    for r in conn.execute(
        f"SELECT source_id, target_id FROM relationship"
        f" WHERE rel_type IN ({placeholders}) AND validation_status='confirmed'"):
        adj.setdefault(r["source_id"], []).append(r["target_id"])
    seen, stack = set(), [start]
    while stack:
        u = stack.pop()
        if u in seen:
            continue
        seen.add(u)
        stack.extend(adj.get(u, ()))
    return seen


def capabilities(conn: sqlite3.Connection) -> list[dict]:
    """Derive business capabilities/functionality from the artifacts.

    Heuristic (honest, inferred): each root driver + its confirmed call-closure is a
    functional area; the label is inferred from naming conventions. Every capability is
    flagged `inferred` with a confidence so it is never mistaken for ground truth.
    """
    progs = set(all_programs(conn))

    def _data_for(members: list[str]) -> tuple[list[str], list[str]]:
        tables, copybooks = set(), set()
        for m in members:
            for r in conn.execute("SELECT rel_type, target_id FROM relationship WHERE source_id=?", (m,)):
                if r["rel_type"] in ("READS", "WRITES"):
                    tables.add(r["target_id"])
                elif r["rel_type"] == "USES":
                    copybooks.add(r["target_id"])
        return sorted(tables), sorted(copybooks)

    caps = []
    covered: set[str] = set()
    for root in roots(conn):
        members = sorted(m for m in _reachable(conn, root, ("CALLS",)) if m in progs)
        covered.update(members)
        jobs = sorted(r["source_id"] for r in conn.execute(
            "SELECT source_id FROM relationship WHERE rel_type='EXECUTES' AND target_id=?", (root,)))
        tables, copybooks = _data_for(members)
        caps.append({
            "capability": _label(root), "root": root, "rootless": False,
            "confidence": 0.5, "validation_status": "inferred",
            "jobs": jobs, "programs": members,
            "tables": tables, "copybooks": copybooks,
            "functions": [{"program": m, "role": _label(m)} for m in members],
            "reason": (f"Inferred from root driver {root} and its confirmed call-closure; "
                       f"capability name derived from naming conventions — review recommended."),
        })

    # Rootless capabilities: programs reachable from NO root driver (dead/orphaned, reached
    # only via unresolved dynamic CALLs, or shared utilities). Per the "kept and flagged,
    # never dropped" rule we surface them too — grouped by CALL-connectivity, flagged
    # inferred at a lower confidence so they are never mistaken for a real entry point.
    orphans = sorted(progs - covered)
    if orphans:
        adj: dict[str, set[str]] = {o: set() for o in orphans}
        for r in conn.execute("SELECT source_id, target_id FROM relationship WHERE rel_type='CALLS'"):
            s, t = r["source_id"], r["target_id"]
            if s in adj and t in adj:                      # edge between two orphans
                adj[s].add(t); adj[t].add(s)
        seen: set[str] = set()
        for start in orphans:                              # connected components (undirected)
            if start in seen:
                continue
            comp, stack = [], [start]
            while stack:
                u = stack.pop()
                if u in seen:
                    continue
                seen.add(u); comp.append(u)
                stack.extend(adj[u] - seen)
            members = sorted(comp)
            rep = members[0]
            tables, copybooks = _data_for(members)
            caps.append({
                "capability": _label(rep), "root": rep, "rootless": True,
                "confidence": 0.3, "validation_status": "inferred",
                "jobs": [], "programs": members,
                "tables": tables, "copybooks": copybooks,
                "functions": [{"program": m, "role": _label(m)} for m in members],
                "reason": ("Not reachable from any root driver (dead code, dynamically-invoked, "
                           "or a shared utility). Grouped by call-connectivity — kept and flagged "
                           "for review; not a confirmed entry point."),
            })
    return caps


def capability_detail(conn: sqlite3.Connection, name: str) -> dict | None:
    """Structural requirements skeleton for one capability (matched by name or root).

    Returns the functional-requirement structure — triggers, member programs + roles,
    and the data each touches (tables with access direction, copybooks). Business rules
    and field flows are layered on in the API (they need the source text). None if no
    capability matches. Everything stays `inferred` (the capability itself is inferred)."""
    key = name.strip().lower()
    cap = next((c for c in capabilities(conn)
                if c["capability"].lower() == key or c["root"].lower() == key), None)
    if cap is None:
        return None
    root = cap["root"]

    # triggers: batch jobs that EXECUTE the root + online transactions that START it
    triggers = [{"type": "batch job", "id": j} for j in cap["jobs"]]
    for r in conn.execute(
        "SELECT source_id FROM relationship WHERE rel_type='STARTS' AND target_id=?", (root,)):
        triggers.append({"type": "online transaction (CICS)", "id": r["source_id"]})

    # member programs: role, size, source path, and what each one calls
    programs = []
    for m in cap["programs"]:
        row = conn.execute(
            "SELECT p.line_count, a.path AS src FROM program p"
            " LEFT JOIN artifact a ON a.artifact_id=p.artifact_id WHERE p.program_id=?", (m,)).fetchone()
        calls = [c["target_id"] for c in conn.execute(
            "SELECT target_id FROM relationship WHERE source_id=? AND rel_type='CALLS' ORDER BY target_id", (m,))]
        programs.append({"program": m, "role": _label(m),
                         "line_count": row["line_count"] if row else None,
                         "source_path": row["src"] if row else None,
                         "calls": calls})

    # data: tables (with access direction) + copybooks across all members
    access: dict[str, set] = {}
    copybooks: set[str] = set()
    for m in cap["programs"]:
        for r in conn.execute("SELECT rel_type, target_id FROM relationship WHERE source_id=?", (m,)):
            if r["rel_type"] in ("READS", "WRITES"):
                access.setdefault(r["target_id"], set()).add(r["rel_type"])
            elif r["rel_type"] == "USES":
                copybooks.add(r["target_id"])
    tables = [{"table": t, "access": sorted(a)} for t, a in sorted(access.items())]

    return {
        "capability": cap["capability"], "root": root,
        "confidence": cap["confidence"], "validation_status": cap["validation_status"],
        "reason": cap["reason"],
        "triggers": triggers, "programs": programs,
        "tables": tables, "copybooks": sorted(copybooks),
    }


def program_profile(conn: sqlite3.Connection, program: str) -> dict:
    """A 360° profile: identity, dependencies, callers, the jobs that ultimately run it
    (transitively through CALLS), and its inferred capability."""
    prog = program.upper()
    row = conn.execute(
        "SELECT p.program_id, p.language, p.line_count, a.path AS src FROM program p"
        " LEFT JOIN artifact a ON a.artifact_id=p.artifact_id WHERE p.program_id=?", (prog,)).fetchone()
    direct = jobs_executing(conn, prog)
    executing, seen, stack = set(direct), {prog}, [prog]
    while stack:
        u = stack.pop()
        for c in callers(conn, u):
            if c["rel_type"] == "EXECUTES":
                executing.add(c["source_id"])
            elif c["source_id"] not in seen:
                seen.add(c["source_id"]); stack.append(c["source_id"])
    cap = next((c["capability"] for c in capabilities(conn) if prog in c["programs"]), None)
    return {
        "program_id": prog,
        "language": row["language"] if row else None,
        "line_count": row["line_count"] if row else None,
        "source_path": row["src"] if row else None,
        "dependencies": program_dependencies(conn, prog),
        "callers": callers(conn, prog),
        "direct_jobs": direct,
        "executing_jobs": sorted(executing),
        "capability": cap,
    }


def graph_insights(conn: sqlite3.Connection) -> dict:
    """Surfaced insights for the graph view (not just nodes/edges)."""
    g = call_graph(conn)
    indeg: dict[str, int] = {}
    for e in g["edges"]:
        if e["rel_type"] == "CALLS":
            indeg[e["target"]] = indeg.get(e["target"], 0) + 1
    most = sorted(indeg.items(), key=lambda x: -x[1])[:5]
    dynamic = [e for e in g["edges"] if e["validation_status"] != "confirmed"]
    return {
        "node_count": len(g["nodes"]), "edge_count": len(g["edges"]),
        "roots": roots(conn), "dead": dead_code(conn),
        "most_depended_on": [{"program": k, "called_by": v} for k, v in most if v > 0],
        "dynamic_edges": [{"source": e["source"], "target": e["target"]} for e in dynamic],
    }


# --- global search --------------------------------------------------------
def _score(needle: str, hay: str) -> int | None:
    """Rank a case-insensitive substring match: exact=100, prefix=50, contains=10."""
    h = hay.upper()
    if h == needle:
        return 100
    if h.startswith(needle):
        return 50
    if needle in h:
        return 10
    return None


def search(conn: sqlite3.Connection, q: str, limit: int = 25) -> list[dict]:
    """Case-insensitive substring search across the estate. Ranks exact > prefix > contains.

    Searches: program ids, job ids, DB2 tables, copybooks, transactions, and inferred
    capability names. Returns at most `limit` results, highest score first.
    """
    needle = (q or "").strip().upper()
    if not needle:
        return []
    out: list[dict] = []
    seen: set[tuple[str, str]] = set()

    def add(kind: str, ident: str, detail: str) -> None:
        key = (kind, ident)
        if key in seen:
            return
        sc = _score(needle, ident)
        if sc is None:
            return
        seen.add(key)
        out.append({"kind": kind, "id": ident, "detail": detail, "score": sc})

    for r in conn.execute("SELECT program_id, line_count FROM program"):
        add("program", r["program_id"], f"COBOL program ({r['line_count'] or 0} lines)")
    for r in conn.execute("SELECT job_id FROM job"):
        add("job", r["job_id"], "JCL job")
    for r in conn.execute(
        "SELECT DISTINCT target_id FROM relationship WHERE target_type='db2_table'"):
        add("table", r["target_id"], "DB2 table")
    for r in conn.execute(
        "SELECT DISTINCT target_id FROM relationship WHERE target_type='copybook'"):
        add("copybook", r["target_id"], "Copybook")
    for r in conn.execute(
        "SELECT DISTINCT source_id FROM relationship WHERE source_type='transaction'"):
        add("transaction", r["source_id"], "CICS transaction")
    for c in capabilities(conn):
        add("capability", c["capability"], f"Inferred capability (root {c['root']})")

    out.sort(key=lambda x: (-x["score"], x["kind"], x["id"]))
    return out[:limit]


# --- tiny NL router -------------------------------------------------------
def _program_in(text: str, known: list[str]) -> str | None:
    # Only ever return a real program name — never a stray uppercase word like SHOW/WHAT,
    # which would attach a confident-looking trace to a non-existent program.
    up = text.upper()
    for p in known:
        if re.search(rf"\b{re.escape(p)}\b", up):
            return p
    return None


def answer(conn: sqlite3.Connection, question: str) -> tuple[str, object]:
    """Return (kind, result) for a natural-language question."""
    q = question.lower()
    known = all_programs(conn)
    prog = _program_in(question, known)

    if "dead" in q or "orphan" in q or "retire" in q:
        return "dead_code", dead_code(conn)
    if "root" in q or "entry point" in q or "driver" in q:
        return "roots", roots(conn)
    if "call" in q and prog:
        return "calls", program_calls(conn, prog)
    if ("depend" in q or "use" in q or "read" in q or "write" in q) and prog:
        return "dependencies", program_dependencies(conn, prog)
    if ("job" in q or "execute" in q or "run" in q) and prog:
        return "jobs_executing", jobs_executing(conn, prog)
    if prog:  # default: full picture for the named program
        return "dependencies", program_dependencies(conn, prog)
    return "help", None


def _evidence_for(conn: sqlite3.Connection, where: str, params: tuple) -> list[dict]:
    rows = conn.execute(
        "SELECT source_id, rel_type, target_id, source_evidence, validation_status, confidence"
        f" FROM relationship WHERE {where}", params)
    return [dict(r) for r in rows]


def answer_with_trace(conn: sqlite3.Connection, question: str) -> tuple[str, object, dict]:
    """Like answer(), but also returns an explainable reasoning trace:
    intent + thought-process steps + the evidence rows + the reason for the conclusion.
    This is what makes the platform auditable (Principle 3: Explainability).
    """
    kind, result = answer(conn, question)
    prog = _program_in(question, all_programs(conn))
    steps: list[str] = [f'Parsed the question and routed it to intent: "{kind}".']
    evidence: list[dict] = []
    reason = ""

    if kind == "jobs_executing":
        steps.append(f"Identified the program token: {prog}.")
        steps.append("Looked up job_step rows whose EXEC PGM= names this program (EXECUTES edges).")
        evidence = _evidence_for(conn, "rel_type='EXECUTES' AND target_id=?", (prog,))
        reason = (f"{prog} is named in EXEC PGM= of {len(result)} job step(s); each is a "
                  f"confirmed EXECUTES edge traced to JCL source, so those jobs execute it."
                  if result else f"No JCL EXEC PGM= names {prog}, so no job executes it directly.")
    elif kind == "calls":
        steps.append(f"Identified the program token: {prog}.")
        steps.append("Collected CALLS edges originating from this program.")
        evidence = _evidence_for(conn, "rel_type='CALLS' AND source_id=?", (prog,))
        nr = [e for e in evidence if e["validation_status"] != "confirmed"]
        reason = (f"{prog} issues {len(evidence)} CALL(s). "
                  + (f"{len(nr)} is a dynamic/unresolved target kept as needs_review (not asserted)."
                     if nr else "All targets are static literals (confirmed)."))
    elif kind == "dependencies":
        steps.append(f"Identified the program token: {prog}.")
        steps.append("Collected every outgoing relationship (CALLS/USES/READS/WRITES).")
        evidence = _evidence_for(conn, "source_id=?", (prog,))
        reason = f"{prog} has {len(evidence)} outgoing relationship(s); listed with evidence and confidence."
    elif kind == "roots":
        steps.append("Computed programs that are EXECUTES-targets of a job but never CALLS-targets.")
        reason = ("Root/driver programs are external entry points: a job executes them and no program "
                  "calls them. Found: " + ", ".join(result) + ".")
    elif kind == "dead_code":
        steps.append("Computed reachability from confirmed roots over EXECUTES+CALLS; took the complement.")
        reason = ("Programs unreachable from any root are dead-code candidates (flagged needs_review — "
                  "they may still be invoked dynamically/externally). Found: " + (", ".join(result) or "none") + ".")
    else:
        reason = "No program or known intent detected; returned guidance."

    trace = {
        "question": question,
        "intent": kind,
        "program": prog,
        "thought_process": steps,
        "evidence": evidence,
        "reason": reason,
        "response": result,
    }
    return kind, result, trace
