"""Runtime Correlation Layer — correlate external operational evidence with the
static graph (CORE_ALGORITHMS.md §Runtime Correlation).

Runtime data is *optional, observed external evidence* (e.g. SMF batch records, the
CICS monitor) for one reporting window. It is never parsed from source, so it can both
*confirm* static facts (a program really ran) and *contradict* them (a dynamically- or
externally-invoked program that static analysis missed actually executed). MIP keeps
both, evidence-based:

  - Present + exec_count>0  -> "confirmed-at-runtime"  (direct execution evidence)
  - Present + exec_count==0 -> "cold"                  (observed but never ran in window)
  - Absent                  -> "unknown"               (no runtime data; never fabricated)

Honesty (MIP Principle 1): absent data is "unknown", not "dead". A statically-dead
program that *ran* is a HIGH-VALUE finding — static analysis missed an invoker; we flag
it for review rather than silently trusting either side.
"""

from __future__ import annotations

import json
import sqlite3
from pathlib import Path

from . import graphx, queries, store
from .records import now_iso

# entity types we accept from the runtime feed
_TYPES = {"program", "job", "transaction"}


def load_runtime(path: str | Path) -> dict:
    """Read and lightly normalize a runtime-evidence JSON file.

    Schema:
        {"window": "2026-05",
         "entities": [{"id","type","exec_count","last_run","avg_elapsed_ms"}, ...]}
    Unknown types are dropped (kept honest: we only correlate program|job|transaction).
    """
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    window = data.get("window")
    src = data.get("source") or f"runtime:{Path(path).name}"
    entities = []
    for e in data.get("entities", []):
        etype = (e.get("type") or "program").lower()
        if etype not in _TYPES:
            continue
        entities.append({
            "id": str(e["id"]).upper(),
            "type": etype,
            "exec_count": e.get("exec_count"),
            "last_run": e.get("last_run"),
            "avg_elapsed_ms": e.get("avg_elapsed_ms"),
        })
    return {"window": window, "source": src, "entities": entities}


def load_into_db(conn: sqlite3.Connection, runtime: dict) -> int:
    """Upsert runtime metrics into the runtime_metric table. Returns rows written."""
    window = runtime.get("window") or "unknown"
    src = runtime.get("source") or "runtime"
    ts = now_iso()
    n = 0
    for e in runtime["entities"]:
        store.insert_runtime_metric(
            conn, e["type"], e["id"], e.get("exec_count"), e.get("last_run"),
            e.get("avg_elapsed_ms"), window,
            f"{src} (window {window})", ts)
        n += 1
    conn.commit()
    return n


def _status(exec_count) -> str:
    if exec_count is None:
        return "unknown"
    return "confirmed-at-runtime" if exec_count > 0 else "cold"


def _index(runtime: dict) -> dict[str, dict]:
    """id -> runtime entity (uppercased ids)."""
    return {e["id"]: e for e in runtime["entities"]}


def correlate(conn: sqlite3.Connection, runtime: dict) -> list[dict]:
    """Attach runtime evidence to every static entity (programs, jobs, transactions),
    plus any runtime-only entity not present in the static model.

    Each row gets execution_frequency, last_run, avg_elapsed_ms and a runtime_status of
    confirmed-at-runtime | cold | unknown (absent data => unknown, never fabricated).
    """
    rt = _index(runtime)
    out: list[dict] = []
    seen: set[str] = set()

    def emit(eid: str, etype: str, in_static: bool) -> None:
        seen.add(eid)
        m = rt.get(eid)
        ec = m["exec_count"] if m else None
        out.append({
            "id": eid,
            "type": etype,
            "in_static": in_static,
            "execution_frequency": ec,
            "last_run": m["last_run"] if m else None,
            "avg_elapsed_ms": m["avg_elapsed_ms"] if m else None,
            "runtime_status": _status(ec),
            "window": runtime.get("window"),
            "evidence": (m and f"runtime:{runtime.get('source')}") or None,
            "confidence": 1.0 if m else 0.0,
            "validation_status": "confirmed" if (m and ec is not None) else "needs_review",
        })

    for p in queries.all_programs(conn):
        emit(p, "program", True)
    for r in conn.execute("SELECT job_id FROM job"):
        emit(r["job_id"], "job", True)
    for r in conn.execute(
            "SELECT DISTINCT source_id FROM relationship WHERE source_type='transaction'"):
        if r["source_id"] not in seen:
            emit(r["source_id"], "transaction", True)

    # runtime-only entities (observed but unknown to the static model) — keep & flag.
    for eid, m in rt.items():
        if eid not in seen:
            emit(eid, m["type"], False)

    out.sort(key=lambda x: (x["type"], x["id"]))
    return out


def reconcile(conn: sqlite3.Connection, runtime: dict) -> dict:
    """Cross-check static analysis against runtime evidence.

    Buckets (each is evidence-based, confidence-scored):
      * static-dead but ran   : in dead_code() AND exec_count>0 — static missed an
                                 invoker; HIGH-VALUE, flag for review.
      * confirmed-dead         : statically dead AND exec_count==0 — dead-code confidence
                                 raised by corroborating runtime evidence.
      * cold-but-reachable     : statically reachable but exec_count==0 over the window —
                                 possibly-dead, needs_review.
      * static-miss            : ran at runtime but is unknown to the static program model
                                 (e.g. a dynamic CALL target with no source member, or an
                                 external invoker) — static analysis is incomplete here.
    """
    rt = _index(runtime)
    progs = set(queries.all_programs(conn))
    dead = set(queries.dead_code(conn))
    window = runtime.get("window")

    static_dead_but_ran: list[dict] = []
    confirmed_dead: list[dict] = []
    cold_but_reachable: list[dict] = []
    static_miss: list[dict] = []

    # programs known to the static model
    for p in sorted(progs):
        m = rt.get(p)
        ec = m["exec_count"] if m else None
        if p in dead:
            if ec is not None and ec > 0:
                static_dead_but_ran.append({
                    "program": p, "exec_count": ec, "last_run": m["last_run"],
                    "confidence": 0.9, "validation_status": "needs_review",
                    "reason": ("Statically unreachable from any root, but runtime shows it "
                               f"executed {ec} time(s) in {window}. Static analysis missed a "
                               "dynamic or external invoker — review before any retirement."),
                })
            elif ec == 0:
                confirmed_dead.append({
                    "program": p, "exec_count": 0,
                    "confidence": 0.85, "validation_status": "inferred",
                    "reason": (f"Statically unreachable AND not executed in {window}. Static + "
                               "runtime evidence agree — dead-code confidence raised."),
                })
            # dead + no runtime data -> stays a static-only candidate (unknown at runtime)
        else:
            if ec == 0:
                cold_but_reachable.append({
                    "program": p, "exec_count": 0,
                    "confidence": 0.5, "validation_status": "needs_review",
                    "reason": (f"Statically reachable but observed 0 executions in {window}. "
                               "Possibly-dead for this window — widen the window or review."),
                })

    # runtime entities that ran but are unknown to the static program model
    for eid, m in rt.items():
        if m["type"] != "program":
            continue
        ec = m["exec_count"]
        if eid not in progs and ec is not None and ec > 0:
            # is it at least known as an (unresolved) static call target?
            known_target = conn.execute(
                "SELECT 1 FROM relationship WHERE target_id=? LIMIT 1", (eid,)).fetchone()
            static_miss.append({
                "program": eid, "exec_count": ec, "last_run": m["last_run"],
                "known_as_dynamic_target": bool(known_target),
                "confidence": 0.9, "validation_status": "needs_review",
                "reason": (
                    f"Ran {ec} time(s) in {window} but has no resolved program in the static "
                    + ("model — appears only as an unresolved/dynamic CALL target; runtime "
                       "CONFIRMS the dynamic call actually fires."
                       if known_target else
                       "model at all — an external/unmapped invoker. Static analysis is "
                       "incomplete; capture this member.")),
            })

    return {
        "window": window,
        "source": runtime.get("source"),
        "static-dead but ran": static_dead_but_ran,
        "confirmed-dead": confirmed_dead,
        "cold-but-reachable": cold_but_reachable,
        "static-miss": static_miss,
        "summary": {
            "static_dead_but_ran": len(static_dead_but_ran),
            "confirmed_dead": len(confirmed_dead),
            "cold_but_reachable": len(cold_but_reachable),
            "static_miss": len(static_miss),
        },
    }


def runtime_criticality(conn: sqlite3.Connection, runtime: dict, top: int = 10) -> list[dict]:
    """Rank programs by combining structural centrality (PageRank) with observed
    execution frequency, so the busiest *and* most-connected programs surface.

    score = 0.5 * norm(pagerank) + 0.5 * norm(exec_count). Both factors are normalized to
    [0,1] over the estate. Programs with no runtime data contribute only their structural
    score (runtime_status='unknown') — we don't fabricate traffic.
    """
    rt = _index(runtime)
    pr = {d["program"]: d["pagerank"]
          for d in graphx.centrality(conn, top=10_000)}
    progs = set(queries.all_programs(conn))

    pr_max = max(pr.values()) if pr else 0.0
    ec_vals = [m["exec_count"] for m in rt.values()
               if m["type"] == "program" and m["exec_count"] is not None]
    ec_max = max(ec_vals) if ec_vals else 0

    rows = []
    for p in progs:
        m = rt.get(p)
        ec = m["exec_count"] if m else None
        npr = (pr.get(p, 0.0) / pr_max) if pr_max else 0.0
        nec = (ec / ec_max) if (ec_max and ec is not None) else 0.0
        rows.append({
            "program": p,
            "pagerank": round(pr.get(p, 0.0), 4),
            "exec_count": ec,
            "runtime_status": _status(ec),
            "norm_pagerank": round(npr, 4),
            "norm_exec": round(nec, 4),
            "runtime_criticality": round(0.5 * npr + 0.5 * nec, 4),
        })
    rows.sort(key=lambda x: (-x["runtime_criticality"], x["program"]))
    return rows[:top]
