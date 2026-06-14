"""NetworkX graph layer — realizes the algorithms specified in
02-algorithms/CORE_ALGORITHMS.md (impact/blast-radius §2, centrality/criticality).

Builds a directed multigraph from the relationship rows and runs real graph algorithms.
networkx is imported lazily so the core engine stays stdlib-only; install with the
`graph` (or `api`) extra: `uv pip install -e ".[graph]"`.

Edge direction convention: an edge points source -> target meaning *source depends on
target* (CALLS, USES, READS, WRITES, EXECUTES). So for a change to node X:
  - who is impacted  = ancestors(X)   (everything that can reach X)
  - what X relies on = descendants(X)
Confidence along a path is the weakest link (min), per CORE_ALGORITHMS §0.
"""

from __future__ import annotations

import sqlite3

_DEP_RELS = ("CALLS", "EXECUTES", "USES", "READS", "WRITES")


def build_graph(conn: sqlite3.Connection):
    import networkx as nx

    g = nx.MultiDiGraph()
    # node kinds from programs/jobs tables (targets like tables/copybooks added via edges)
    for r in conn.execute("SELECT program_id FROM program"):
        g.add_node(r["program_id"], kind="program")
    for r in conn.execute("SELECT job_id FROM job"):
        g.add_node(r["job_id"], kind="job")
    for r in conn.execute(
        "SELECT source_id, source_type, rel_type, target_id, target_type,"
        " confidence, validation_status FROM relationship"):
        if r["source_id"] not in g:
            g.add_node(r["source_id"], kind=r["source_type"])
        if r["target_id"] not in g:
            g.add_node(r["target_id"], kind=r["target_type"])
        g.add_edge(r["source_id"], r["target_id"], rel_type=r["rel_type"],
                   confidence=r["confidence"], validation_status=r["validation_status"])
    return g


def _hop_best(g, u, v) -> dict:
    """Best (highest-confidence) parallel edge between u and v."""
    best = None
    for data in g.get_edge_data(u, v).values():
        if best is None or data["confidence"] > best["confidence"]:
            best = data
    return best


def _path_summary(g, src, dst):
    """(distance, weakest confidence, any-needs-review) along the shortest src->dst path."""
    import networkx as nx

    path = nx.shortest_path(g, src, dst)
    conf, review = 1.0, False
    for u, v in zip(path, path[1:]):
        e = _hop_best(g, u, v)
        conf = min(conf, e["confidence"])
        if e["validation_status"] != "confirmed":
            review = True
    return len(path) - 1, round(conf, 3), review


def blast_radius(conn: sqlite3.Connection, target: str) -> dict:
    """Impact analysis for a change to `target` (program or table/copybook)."""
    import networkx as nx

    g = build_graph(conn)
    target = target.upper()
    if target not in g:
        return {"target": target, "found": False, "impacted": [], "depends_on": [],
                "blast_radius_score": 0.0, "review": []}

    impacted = []
    for n in nx.ancestors(g, target):
        dist, conf, review = _path_summary(g, n, target)
        impacted.append({"id": n, "kind": g.nodes[n].get("kind", "?"),
                         "distance": dist, "confidence": conf, "via_needs_review": review})
    depends_on = []
    for n in nx.descendants(g, target):
        dist, conf, review = _path_summary(g, target, n)
        depends_on.append({"id": n, "kind": g.nodes[n].get("kind", "?"),
                           "distance": dist, "confidence": conf, "via_needs_review": review})

    impacted.sort(key=lambda x: (x["distance"], -x["confidence"], x["id"]))
    depends_on.sort(key=lambda x: (x["distance"], x["id"]))
    score = round(sum(x["confidence"] for x in impacted), 2)  # confidence-weighted reach
    return {
        "target": target, "found": True, "target_kind": g.nodes[target].get("kind", "?"),
        "impacted": impacted, "depends_on": depends_on,
        "blast_radius_score": score,
        "review": [x["id"] for x in impacted if x["via_needs_review"]],
    }


def centrality(conn: sqlite3.Connection, top: int = 5,
               damping: float = 0.85, iters: int = 50) -> list[dict]:
    """Most critical programs by PageRank over the call/execution subgraph.

    Pure-Python power iteration (no numpy/scipy) — keeps the footprint to networkx core.
    """
    g = build_graph(conn)
    out: dict[str, list[str]] = {}
    nodes: set[str] = set()
    for u, v, d in g.edges(data=True):
        if d["rel_type"] in ("CALLS", "EXECUTES"):
            out.setdefault(u, []).append(v)
            nodes.add(u)
            nodes.add(v)
    if not nodes:
        return []

    n = len(nodes)
    pr = {x: 1.0 / n for x in nodes}
    outdeg = {x: len(out.get(x, [])) for x in nodes}
    for _ in range(iters):
        dangling = damping * sum(pr[x] for x in nodes if outdeg[x] == 0) / n
        new = {x: (1.0 - damping) / n + dangling for x in nodes}
        for u, outs in out.items():
            share = damping * pr[u] / len(outs)
            for v in outs:
                new[v] += share
        pr = new

    ranked = sorted(((x, s) for x, s in pr.items()
                     if g.nodes.get(x, {}).get("kind") == "program"),
                    key=lambda kv: -kv[1])[:top]
    return [{"program": x, "pagerank": round(s, 4)} for x, s in ranked]
