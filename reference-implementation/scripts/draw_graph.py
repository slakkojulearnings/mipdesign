"""Render the MIP call/execution graph (the NetworkX graph) to a picture.

The web app's "Call & Execution Graph" screen and the GraphML export already cover most
needs; this is for when you want a quick standalone image (e.g. for a slide) from the same
NetworkX graph the engine builds (graphx.build_graph).

It degrades gracefully:
  1. pyvis installed      -> interactive, draggable HTML  (recommended)
  2. else matplotlib      -> static PNG
  3. neither              -> prints how to install, or to use GraphML in Gephi/yEd/Cytoscape

Nodes are colored like the UI: jobs (orange ▸), roots (green), dead code (red), other
programs (purple). needs_review/inferred edges are dashed.

Usage:
    uv run python scripts/draw_graph.py                 # use existing mip.db (or mip.api.db)
    uv run python scripts/draw_graph.py --source ../source_mf_code   # scan fresh, then draw
    uv run python scripts/draw_graph.py --db mip.api.db --out graph.html
    uv pip install -e ".[viz]"                          # installs pyvis + matplotlib
"""

from __future__ import annotations

import argparse
import sys
import tempfile
from pathlib import Path

_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_ROOT / "src"))

from mip import graphx, queries, store  # noqa: E402
from mip.pipeline import build_db        # noqa: E402

# UI-matching palette (see app/frontend CallGraph): job / root / dead / program
_COLORS = {"job": "#ff9500", "root": "#248a3d", "dead": "#d70015", "program": "#5e5ce6"}


def _node_color(node_id: str, kind: str, roots: set[str], dead: set[str]) -> str:
    if kind == "job":
        return _COLORS["job"]
    if node_id in dead:
        return _COLORS["dead"]
    if node_id in roots:
        return _COLORS["root"]
    return _COLORS["program"]


def _resolve_db(args) -> Path:
    if args.source:
        tmp = Path(tempfile.gettempdir()) / "mip_draw.db"
        print(f"Scanning {args.source} -> {tmp} ...")
        build_db(Path(args.source), tmp)
        return tmp
    if args.db:
        return Path(args.db)
    for cand in (_ROOT / "mip.db", _ROOT / "mip.api.db"):
        if cand.exists():
            return cand
    sys.exit("No database found. Run `mip scan <estate>` first, or pass --source <estate>.")


def render_pyvis(g, roots, dead, out: Path) -> bool:
    try:
        from pyvis.network import Network
    except Exception:
        return False
    net = Network(height="820px", width="100%", directed=True, bgcolor="#ffffff", font_color="#1d1d1f")
    net.barnes_hut(spring_length=140)
    for n, d in g.nodes(data=True):
        kind = d.get("kind", "program")
        tag = " [ROOT]" if n in roots else (" [DEAD]" if n in dead else "")
        net.add_node(n, label=n, color=_node_color(n, kind, roots, dead),
                     shape="box" if kind == "job" else "ellipse",
                     title=f"{kind}: {n}{tag}")
    for u, v, d in g.edges(data=True):
        review = d.get("validation_status") != "confirmed"
        net.add_edge(u, v, title=f"{d.get('rel_type')} · {d.get('validation_status')} · {d.get('confidence')}",
                     dashes=review, color="#b25e00" if review else "#9aa6b2")
    net.write_html(str(out), notebook=False, open_browser=False)
    return True


def render_matplotlib(g, roots, dead, out: Path) -> bool:
    try:
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
        import networkx as nx
    except Exception:
        return False
    pos = nx.spring_layout(g, seed=42, k=0.9)
    node_colors = [_node_color(n, g.nodes[n].get("kind", "program"), roots, dead) for n in g.nodes]
    confirmed = [(u, v) for u, v, d in g.edges(data=True) if d.get("validation_status") == "confirmed"]
    review = [(u, v) for u, v, d in g.edges(data=True) if d.get("validation_status") != "confirmed"]
    plt.figure(figsize=(16, 11))
    nx.draw_networkx_nodes(g, pos, node_color=node_colors, node_size=900, alpha=0.95)
    nx.draw_networkx_edges(g, pos, edgelist=confirmed, edge_color="#9aa6b2", arrows=True, arrowsize=12)
    nx.draw_networkx_edges(g, pos, edgelist=review, edge_color="#b25e00", style="dashed", arrows=True, arrowsize=12)
    nx.draw_networkx_labels(g, pos, font_size=8, font_family="monospace")
    plt.axis("off")
    plt.tight_layout()
    plt.savefig(out, dpi=150, bbox_inches="tight")
    plt.close()
    return True


def main() -> None:
    ap = argparse.ArgumentParser(description="Render the MIP NetworkX graph to HTML/PNG.")
    ap.add_argument("--db", help="SQLite db to read (default: mip.db then mip.api.db)")
    ap.add_argument("--source", help="estate to scan fresh before drawing")
    ap.add_argument("--out", help="output file (default graph.html for pyvis, graph.png for matplotlib)")
    args = ap.parse_args()

    db = _resolve_db(args)
    conn = store.connect(db)
    g = graphx.build_graph(conn)
    roots, dead = set(queries.roots(conn)), set(queries.dead_code(conn))
    conn.close()
    print(f"Graph from {db.name}: {g.number_of_nodes()} nodes, {g.number_of_edges()} edges "
          f"({len(roots)} roots, {len(dead)} dead).")

    out = Path(args.out) if args.out else None
    if render_pyvis(g, roots, dead, out or Path("graph.html")):
        print(f"Wrote interactive HTML -> {out or 'graph.html'}  (open it in a browser)")
        return
    if render_matplotlib(g, roots, dead, out or Path("graph.png")):
        print(f"Wrote PNG -> {out or 'graph.png'}  (install pyvis for an interactive version)")
        return
    print("Neither pyvis nor matplotlib is installed.\n"
          "  -> uv pip install -e \".[viz]\"   to enable this script, OR\n"
          "  -> export GraphML from the app (or /api/export?format=graphml) and open it in\n"
          "     Gephi / yEd / Cytoscape for full interactive layouts.")


if __name__ == "__main__":
    main()
