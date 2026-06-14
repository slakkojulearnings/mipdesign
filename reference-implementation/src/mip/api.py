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
from pydantic import BaseModel

from . import cobol, graphx, parser_backend, qlog, queries, store
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


@app.get("/api/insights")
def get_insights() -> dict:
    _ensure_scanned()
    conn = _conn()
    out = queries.graph_insights(conn)
    conn.close()
    return out


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


# Serve the built frontend (production) if it has been built.
_DIST = _REPO_ROOT / "app" / "frontend" / "dist"
if _DIST.exists():
    from fastapi.staticfiles import StaticFiles

    app.mount("/", StaticFiles(directory=str(_DIST), html=True), name="frontend")
