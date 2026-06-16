"""MIP REST API (FastAPI) — serves the metadata store to the React frontend.

Reuses the same engine as the CLI (pipeline + queries + store). Scans the real
mainframe source at <repo-root>/source_mf_code by default (override with MIP_SOURCE
or the ?path= query param on /api/scan).

Run:  uv run uvicorn mip.api:app --reload --port 8000
"""

from __future__ import annotations

import os
from pathlib import Path

from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import Response
from pydantic import BaseModel

from . import cobol, export, graphx, parser_backend, qlog, queries, runtime, store
from .pipeline import build_db

_PKG_ROOT = Path(__file__).resolve().parents[2]          # reference-implementation/
_REPO_ROOT = Path(__file__).resolve().parents[3]         # repo root
_DEFAULT_SOURCE = Path(os.environ.get("MIP_SOURCE") or (_REPO_ROOT / "source_mf_code"))
_DB_PATH = _PKG_ROOT / "mip.api.db"

app = FastAPI(title="MIP API", version="0.1.0")
app.add_middleware(
    CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"],
)

# current source root (mutable via /api/scan)
_state = {"source": _DEFAULT_SOURCE}


def _conn():
    return store.connect(_DB_PATH)


def _structure_for(source_path: str | None):
    if not source_path:
        return None
    target = _state["source"] / source_path
    if target.is_file():
        return cobol.structure(target.read_text(encoding="utf-8", errors="replace"))
    return None


def _full_profile(conn, pid: str) -> dict:
    prof = queries.program_profile(conn, pid)
    prof["structure"] = _structure_for(prof.get("source_path"))
    return prof


def _ensure_scanned():
    """Build the DB on first use if the source exists and nothing is loaded yet."""
    conn = _conn()
    has = conn.execute("SELECT COUNT(*) FROM program").fetchone()[0]
    conn.close()
    if not has and _state["source"].exists():
        build_db(_state["source"], _DB_PATH)


def _runtime_path() -> Path:
    return _state["source"] / "runtime" / "runtime.json"


def _ensure_runtime():
    """Auto-load runtime/runtime.json from the source root on first use if present and
    nothing is loaded yet (mirrors _ensure_scanned). No-op if the file is absent —
    runtime data is optional external evidence."""
    conn = _conn()
    has = conn.execute("SELECT COUNT(*) FROM runtime_metric").fetchone()[0]
    conn.close()
    rt_path = _runtime_path()
    if not has and rt_path.is_file():
        conn = _conn()
        runtime.load_into_db(conn, runtime.load_runtime(rt_path))
        conn.close()


class ScanResult(BaseModel):
    source: str
    summary: dict


class QueryIn(BaseModel):
    question: str


@app.get("/api/health")
def health() -> dict:
    return {"status": "ok", "source": str(_state["source"]),
            "source_exists": _state["source"].exists(),
            "parser": parser_backend.backend_info()}


@app.post("/api/scan", response_model=ScanResult)
def scan(path: str | None = Query(default=None)) -> ScanResult:
    src = Path(path) if path else _DEFAULT_SOURCE
    if not src.exists():
        raise HTTPException(404, f"source path not found: {src}")
    _state["source"] = src
    build_db(src, _DB_PATH)
    conn = _conn()
    summ = queries.summary(conn)
    conn.close()
    return ScanResult(source=str(src), summary=summ)


@app.get("/api/summary")
def get_summary() -> dict:
    _ensure_scanned()
    conn = _conn()
    out = queries.summary(conn)
    out["source"] = str(_state["source"])
    conn.close()
    return out


@app.get("/api/programs")
def get_programs() -> list[dict]:
    _ensure_scanned()
    conn = _conn()
    out = queries.programs_overview(conn)
    conn.close()
    return out


@app.get("/api/program/{pid}")
def get_program(pid: str) -> dict:
    _ensure_scanned()
    conn = _conn()
    pid = pid.upper()
    deps = queries.program_dependencies(conn, pid)
    callers = queries.callers(conn, pid)
    row = conn.execute(
        "SELECT p.program_id, p.language, p.line_count, a.path AS source_path"
        " FROM program p LEFT JOIN artifact a ON a.artifact_id=p.artifact_id"
        " WHERE p.program_id=?", (pid,)).fetchone()
    conn.close()
    if not row and not callers:
        raise HTTPException(404, f"unknown program: {pid}")
    source_path = row["source_path"] if row else None
    struct = None
    if source_path:
        target = (_state["source"] / source_path)
        if target.is_file():
            struct = cobol.structure(target.read_text(encoding="utf-8", errors="replace"))
    return {
        "program_id": pid,
        "language": row["language"] if row else None,
        "line_count": row["line_count"] if row else None,
        "source_path": source_path,
        "dependencies": deps,
        "callers": callers,
        "structure": struct,
    }


@app.get("/api/program/{pid}/profile")
def get_program_profile(pid: str) -> dict:
    _ensure_scanned()
    conn = _conn()
    out = _full_profile(conn, pid.upper())
    conn.close()
    return out


@app.get("/api/program/{pid}/lineage")
def get_lineage(pid: str) -> dict:
    """Field-level data lineage for a program (grammar parser: MOVE + SQL host-var<->column)."""
    _ensure_scanned()
    conn = _conn()
    pid = pid.upper()
    row = conn.execute(
        "SELECT a.path AS src FROM program p JOIN artifact a ON a.artifact_id=p.artifact_id"
        " WHERE p.program_id=?", (pid,)).fetchone()
    conn.close()
    if not row or not row["src"]:
        return {"program_id": pid, "flows": []}
    target = _state["source"] / row["src"]
    text = target.read_text(encoding="utf-8", errors="replace") if target.is_file() else ""
    return {"program_id": pid, "flows": cobol.field_lineage(text, pid, row["src"])}


@app.get("/api/program/{pid}/rules")
def get_rules(pid: str) -> dict:
    """Business rules extracted from a program (IF / EVALUATE WHEN / COMPUTE).

    Conditions are confirmed facts (real source line); kind + plain-English statement are
    interpretation, flagged validation_status='inferred'."""
    _ensure_scanned()
    conn = _conn()
    pid = pid.upper()
    row = conn.execute(
        "SELECT a.path AS src FROM program p JOIN artifact a ON a.artifact_id=p.artifact_id"
        " WHERE p.program_id=?", (pid,)).fetchone()
    conn.close()
    if not row or not row["src"]:
        return {"program_id": pid, "rules": []}
    target = _state["source"] / row["src"]
    text = target.read_text(encoding="utf-8", errors="replace") if target.is_file() else ""
    return {"program_id": pid, "rules": cobol.business_rules(text, pid, row["src"])}


@app.get("/api/program/{pid}/trace")
def get_trace(pid: str, direction: str = Query(default="both"),
              depth: int = Query(default=8), include_data: bool = Query(default=True)) -> dict:
    """Complete call trace for a program — upstream (who triggers it) and downstream (what it
    calls + the DB tables/copybooks it touches), as a tree + a flat graph, each hop carrying
    evidence (file:line) and confidence. Unresolved/dynamic branches are kept and flagged."""
    _ensure_scanned()
    conn = _conn()
    out = queries.trace(conn, pid.upper(), direction=direction, depth=depth, include_data=include_data)
    conn.close()
    if not out["found"]:
        raise HTTPException(404, f"program not found: {pid}")
    return out


@app.get("/api/program/{pid}/spec")
def get_spec(pid: str) -> dict:
    """Granular developer spec: data structures (by section), procedure outline (pseudocode),
    I/O contract, and business rules with real source snippets + typed fields. Detailed
    enough to re-implement the program; every fact is source-cited."""
    _ensure_scanned()
    conn = _conn()
    pid = pid.upper()
    row = conn.execute(
        "SELECT a.path AS src FROM program p JOIN artifact a ON a.artifact_id=p.artifact_id"
        " WHERE p.program_id=?", (pid,)).fetchone()
    conn.close()
    if not row or not row["src"]:
        raise HTTPException(404, f"program not found or has no source: {pid}")
    target = _state["source"] / row["src"]
    text = target.read_text(encoding="utf-8", errors="replace") if target.is_file() else ""
    return cobol.program_spec(text, pid, row["src"])


@app.get("/api/jobs")
def get_jobs() -> list[dict]:
    _ensure_scanned()
    conn = _conn()
    out = queries.jobs_overview(conn)
    conn.close()
    return out


@app.get("/api/roots")
def get_roots() -> list[str]:
    _ensure_scanned()
    conn = _conn()
    out = queries.roots(conn)
    conn.close()
    return out


@app.get("/api/deadcode")
def get_deadcode() -> list[str]:
    _ensure_scanned()
    conn = _conn()
    out = queries.dead_code(conn)
    conn.close()
    return out


@app.get("/api/graph")
def get_graph() -> dict:
    _ensure_scanned()
    conn = _conn()
    out = queries.call_graph(conn)
    ins = queries.graph_insights(conn)
    ins["critical_by_pagerank"] = graphx.centrality(conn)   # NetworkX PageRank
    comm = graphx.communities(conn)                         # Louvain communities
    ins["community_count"] = len(comm["communities"])
    ins["modularity"] = comm["modularity"]
    nc = comm["node_community"]
    for node in out["nodes"]:
        node["community"] = nc.get(node["id"])
    out["insights"] = ins
    conn.close()
    return out


@app.get("/api/communities")
def get_communities() -> dict:
    """Inferred applications/domains via Louvain community detection."""
    _ensure_scanned()
    conn = _conn()
    out = graphx.communities(conn)
    conn.close()
    return out


@app.get("/api/program/{pid}/impact")
def get_impact(pid: str) -> dict:
    """Blast-radius / impact analysis via NetworkX (who breaks if this changes)."""
    _ensure_scanned()
    conn = _conn()
    out = graphx.blast_radius(conn, pid.upper())
    conn.close()
    return out


@app.get("/api/capabilities")
def get_capabilities() -> list[dict]:
    _ensure_scanned()
    conn = _conn()
    out = queries.capabilities(conn)
    conn.close()
    return out


@app.get("/api/capability/{name}/requirements")
def get_capability_requirements(name: str) -> dict:
    """Aggregated business + functional requirements for one capability.

    FR = triggers, member programs & roles, data touched (tables/access, copybooks).
    BR = every business rule extracted across the member programs (each citing file:line).
    Conditions/line numbers are confirmed; classifications, plain-English statements, and
    the capability grouping itself are inferred — see `disclaimer`."""
    _ensure_scanned()
    conn = _conn()
    detail = queries.capability_detail(conn, name)
    conn.close()
    if detail is None:
        raise HTTPException(404, f"capability not found: {name}")

    rules, fields = [], []
    for p in detail["programs"]:
        src = p.get("source_path")
        target = (_state["source"] / src) if src else None
        if not target or not target.is_file():
            p["spec"] = None
            continue
        text = target.read_text(encoding="utf-8", errors="replace")
        spec = cobol.program_spec(text, p["program"], src)   # granular developer detail
        p["spec"] = spec
        rules.extend(spec["rules"])
        fields.extend(cobol.field_lineage(text, p["program"], src))

    detail["business_rules"] = rules
    detail["field_flows"] = fields
    detail["summary"] = {
        "program_count": len(detail["programs"]),
        "rule_count": len(rules),
        "table_count": len(detail["tables"]),
        "trigger_count": len(detail["triggers"]),
    }
    detail["disclaimer"] = (
        "Reverse-engineered from source code: these requirements describe the system's "
        "implemented behavior, not its original intent. Rule conditions cite real source "
        "lines (confirmed); rule classifications, plain-English statements, and the "
        "capability grouping are inferred — review before relying on them.")
    return detail


@app.post("/api/parser")
def set_parser(mode: str = Query(...)) -> dict:
    """Switch the active COBOL parser backend (`default` | `advanced`) and re-scan so the
    new backend is reflected everywhere. If `advanced` is requested but its ANTLR runtime/
    grammar isn't installed, the engine stays on `default` — see `parser.effective`."""
    mode = mode.strip().lower()
    if mode not in ("default", "advanced"):
        raise HTTPException(400, "mode must be 'default' or 'advanced'")
    os.environ["MIP_PARSER"] = mode
    rescanned = _state["source"].exists()
    if rescanned:
        build_db(_state["source"], _DB_PATH)
    return {"parser": parser_backend.backend_info(), "rescanned": rescanned}


@app.get("/api/insights")
def get_insights() -> dict:
    _ensure_scanned()
    conn = _conn()
    out = queries.graph_insights(conn)
    conn.close()
    return out


@app.get("/api/search")
def get_search(q: str = Query(...)) -> dict:
    """Global search across programs, jobs, tables, copybooks, transactions, capabilities."""
    _ensure_scanned()
    conn = _conn()
    results = queries.search(conn, q)
    conn.close()
    return {"query": q, "results": results}


@app.post("/api/query")
def post_query(body: QueryIn) -> dict:
    _ensure_scanned()
    conn = _conn()
    kind, result, trace = queries.answer_with_trace(conn, body.question)
    profile = _full_profile(conn, trace["program"]) if trace.get("program") else None
    conn.close()
    entry = qlog.log_entry(trace)          # append to question_log.md (+ .jsonl)
    return {"kind": kind, "result": result, "trace": entry, "profile": profile}


@app.get("/api/log")
def get_log(limit: int = Query(default=100)) -> list[dict]:
    return qlog.read_entries(limit)


@app.get("/api/log/raw")
def get_log_raw() -> dict:
    return {"path": str(qlog.MD_PATH), "markdown": qlog.raw_md()}


@app.get("/api/program/{pid}/sequence")
def get_sequence(pid: str) -> dict:
    """Mermaid sequence diagram of a program's interactions in source-line order."""
    _ensure_scanned()
    conn = _conn()
    pid = pid.upper()
    row = conn.execute(
        "SELECT a.path AS src FROM program p JOIN artifact a ON a.artifact_id=p.artifact_id"
        " WHERE p.program_id=?", (pid,)).fetchone()
    conn.close()
    if not row or not row["src"]:
        return cobol.sequence("", pid)
    target = _state["source"] / row["src"]
    text = target.read_text(encoding="utf-8", errors="replace") if target.is_file() else ""
    return cobol.sequence(text, pid)


@app.get("/api/export")
def get_export(format: str = Query(...), kind: str = Query(default="programs")) -> Response:
    """Downloadable export of the estate: graphml | json | csv (kind=programs|edges)."""
    _ensure_scanned()
    conn = _conn()
    try:
        if format == "graphml":
            body, media, fname = export.graphml(conn), "application/xml", "mip-graph.graphml"
        elif format == "json":
            body, media, fname = export.json_bundle(conn), "application/json", "mip-export.json"
        elif format == "csv":
            if kind == "edges":
                body, fname = export.csv_edges(conn), "mip-edges.csv"
            else:
                body, fname = export.csv_programs(conn), "mip-programs.csv"
            media = "text/csv"
        else:
            raise HTTPException(400, f"unknown export format: {format}")
    finally:
        conn.close()
    return Response(content=body, media_type=media,
                    headers={"Content-Disposition": f'attachment; filename="{fname}"'})


@app.get("/api/source")
def get_source(path: str = Query(...)) -> dict:
    """Return raw member text for the evidence viewer (sandboxed to the source root)."""
    root = _state["source"].resolve()
    target = (root / path).resolve()
    if root not in target.parents and target != root:
        raise HTTPException(403, "path outside source root")
    if not target.is_file():
        raise HTTPException(404, f"not found: {path}")
    return {"path": path, "text": target.read_text(encoding="utf-8", errors="replace")}


@app.post("/api/runtime/load")
def post_runtime_load() -> dict:
    """Load runtime evidence from <source-root>/runtime/runtime.json and upsert it.

    Runtime data is optional external operational evidence. 404 with guidance if the
    file is absent so the caller knows where to put it."""
    _ensure_scanned()
    rt_path = _runtime_path()
    if not rt_path.is_file():
        raise HTTPException(
            404, f"no runtime evidence at {rt_path}. Place a runtime file at "
                 "<source-root>/runtime/runtime.json "
                 '({"window":"YYYY-MM","entities":[{"id","type","exec_count",'
                 '"last_run","avg_elapsed_ms"}]}).')
    rt = runtime.load_runtime(rt_path)
    conn = _conn()
    n = runtime.load_into_db(conn, rt)
    conn.close()
    return {"loaded": n, "window": rt.get("window"), "source": rt.get("source"),
            "path": str(rt_path)}


@app.get("/api/runtime")
def get_runtime() -> dict:
    """Correlated runtime view: per-entity metrics, static-vs-runtime reconciliation,
    and runtime-weighted criticality. Auto-loads runtime/runtime.json on first use."""
    _ensure_scanned()
    _ensure_runtime()
    rt_path = _runtime_path()
    if not rt_path.is_file():
        return {"window": None, "available": False,
                "message": f"no runtime evidence found at {rt_path}; "
                           "correlation skipped (all entities would be 'unknown').",
                "metrics": [], "reconciliation": {}, "criticality": []}
    rt = runtime.load_runtime(rt_path)
    conn = _conn()
    out = {
        "available": True,
        "window": rt.get("window"),
        "source": rt.get("source"),
        "metrics": runtime.correlate(conn, rt),
        "reconciliation": runtime.reconcile(conn, rt),
        "criticality": runtime.runtime_criticality(conn, rt),
    }
    conn.close()
    return out


# Serve the built frontend (production) if it has been built.
_DIST = _REPO_ROOT / "app" / "frontend" / "dist"
if _DIST.exists():
    from fastapi.staticfiles import StaticFiles

    app.mount("/", StaticFiles(directory=str(_DIST), html=True), name="frontend")
