#!/usr/bin/env python3
"""Export per-entry-point and per-entity EVIDENCE PACKS from a MIP database.

Why: GitHub Copilot (or any LLM) cannot reach your DB without MCP. This script writes
plain JSON files into the workspace that Copilot reads as context to propose
capabilities / domains / sub-domains / customer journeys (see the prompt files).

It is read-only on the DB. Grounded in the real MIP schema:
  asset(asset_id, run_id, asset_type, technical_name, attributes_json, member_id, ...)
  relationship(relationship_type, source_asset_id, target_asset_id, attributes_json, ...)
  source_member(member_id, relative_path, ...)

Usage:
  python export_evidence.py --db data/estate.db [--run-id RUN] \
         [--out journey-discovery/evidence] [--depth 6]
"""
from __future__ import annotations
import argparse, json, re, sqlite3
from collections import deque
from pathlib import Path

# Real MIP relationship vocabulary (verified in ingestion.py)
CONTROL_RELS = ("CALLS", "DYNAMIC_CALL", "EXECUTES", "INVOKES_PROC",
                "STARTS_PROGRAM", "STARTS_TRANSACTION", "TRIGGERS")
DATA_RELS = ("READS_TABLE", "WRITES_TABLE", "READS_FILE", "WRITES_FILE",
             "USES_DATASET", "READS_DATASET", "WRITES_DATASET")
SCREEN_RELS = ("USES_MAP", "SENDS_MAP", "RECEIVES_MAP")
ENTRY_TYPES = ("TRANSACTION", "JOB")
ENTITY_TYPES = ("TABLE", "FILE", "DATASET")


def safe(name: str) -> str:
    return re.sub(r"[^A-Za-z0-9._-]", "_", str(name))[:120] or "unnamed"


def connect(db: str) -> sqlite3.Connection:
    c = sqlite3.connect(db)
    c.row_factory = sqlite3.Row
    return c


def latest_run(c) -> str | None:
    r = c.execute("SELECT run_id FROM run_manifest ORDER BY started_at DESC LIMIT 1").fetchone()
    return r["run_id"] if r else None


def asset(c, run, aid):
    return c.execute("SELECT * FROM asset WHERE run_id=? AND asset_id=?", (run, aid)).fetchone()


def out_edges(c, run, aid, types):
    q = ",".join("?" * len(types))
    return c.execute(
        f"""SELECT r.relationship_type rel, r.attributes_json attrs, r.confidence conf,
                   r.validation_status status, t.asset_id tid, t.asset_type ttype, t.technical_name tname
            FROM relationship r JOIN asset t ON t.asset_id = r.target_asset_id
            WHERE r.run_id=? AND r.source_asset_id=? AND r.relationship_type IN ({q})""",
        (run, aid, *types)).fetchall()


def rel_path(c, run, member_id):
    if not member_id:
        return None
    r = c.execute("SELECT relative_path FROM source_member WHERE run_id=? AND member_id=?",
                  (run, member_id)).fetchone()
    return r["relative_path"] if r else None


def trace(c, run, start_id, depth):
    """Bounded downstream control-flow BFS; returns program asset ids reached, in order."""
    seen, order, q = {start_id}, [], deque([(start_id, 0)])
    while q:
        aid, d = q.popleft()
        if d >= depth:
            continue
        for e in out_edges(c, run, aid, CONTROL_RELS):
            if e["tid"] not in seen:
                seen.add(e["tid"]); order.append(e["tid"]); q.append((e["tid"], d + 1))
    return order


def program_signals(c, run, aid):
    a = asset(c, run, aid)
    if not a:
        return None
    attrs = json.loads(a["attributes_json"] or "{}")
    return {
        "technical_name": a["technical_name"],
        "asset_type": a["asset_type"],
        "relative_path": rel_path(c, run, a["member_id"]),
        "program_id": (attrs.get("ast_summary") or {}).get("program_id"),
        "paragraphs": (attrs.get("ast_summary") or {}).get("paragraphs", [])[:25],
        "validation_status": a["validation_status"],
    }


def collect(c, run, prog_ids):
    """Gather screens, data touched, and business rules (with evidence) for a program set."""
    screens, data, rules = set(), [], []
    for pid in prog_ids:
        a = asset(c, run, pid)
        if not a:
            continue
        for e in out_edges(c, run, pid, SCREEN_RELS):
            screens.add(e["tname"])
        for e in out_edges(c, run, pid, DATA_RELS):
            data.append({"program": a["technical_name"], "rel": e["rel"], "entity": e["tname"],
                         "entity_type": e["ttype"], "confidence": e["conf"], "status": e["status"]})
        for e in out_edges(c, run, pid, ("DEFINES_BUSINESS_RULE",)):
            attrs = json.loads(e["attrs"] or "{}")
            rules.append({"program": a["technical_name"], "rule_id": attrs.get("rule_id"),
                          "kind": attrs.get("kind"), "statement": attrs.get("statement"),
                          "condition": attrs.get("condition"), "confidence": e["conf"], "status": e["status"]})
    return sorted(screens), data, rules


def export_entry_points(c, run, out, depth, glossary):
    rows = c.execute(
        "SELECT asset_id, asset_type, technical_name FROM asset "
        "WHERE run_id=? AND asset_type IN ('TRANSACTION','JOB') ORDER BY asset_type, technical_name",
        (run,)).fetchall()
    index = []
    for e in rows:
        prog_ids = trace(c, run, e["asset_id"], depth)
        screens, data, rules = collect(c, run, [e["asset_id"], *prog_ids])
        programs = [p for p in (program_signals(c, run, pid) for pid in prog_ids) if p]
        pack = {
            "run_id": run, "entry_point": e["technical_name"], "entry_type": e["asset_type"],
            "screens": screens, "programs": programs,
            "tables_written": sorted({d["entity"] for d in data if d["rel"].startswith("WRITES")}),
            "tables_read": sorted({d["entity"] for d in data if d["rel"].startswith(("READS", "USES"))}),
            "data_touched": data, "business_rules": rules,
        }
        (out / "entry_points" / f"{safe(e['asset_type'])}_{safe(e['technical_name'])}.json").write_text(
            json.dumps(pack, indent=2), encoding="utf-8")
        index.append({"entry_point": e["technical_name"], "type": e["asset_type"],
                      "programs": len(programs), "screens": len(screens), "rules": len(rules)})
        glossary["transactions" if e["asset_type"] == "TRANSACTION" else "jobs"].append(e["technical_name"])
        for s in screens:
            glossary["screens"].add(s)
        for p in programs:
            glossary["programs"].add(p["technical_name"])
    return index


def export_entities(c, run, out, glossary):
    rows = c.execute(
        "SELECT asset_id, asset_type, technical_name FROM asset "
        f"WHERE run_id=? AND asset_type IN ({','.join('?'*len(ENTITY_TYPES))}) ORDER BY asset_type, technical_name",
        (run, *ENTITY_TYPES)).fetchall()
    for ent in rows:
        q = ",".join("?" * len(DATA_RELS))
        touch = c.execute(
            f"""SELECT r.relationship_type rel, s.technical_name sname
                FROM relationship r JOIN asset s ON s.asset_id=r.source_asset_id
                WHERE r.run_id=? AND r.target_asset_id=? AND r.relationship_type IN ({q})""",
            (run, ent["asset_id"], *DATA_RELS)).fetchall()
        writers = sorted({t["sname"] for t in touch if t["rel"].startswith("WRITES")})
        readers = sorted({t["sname"] for t in touch if t["rel"].startswith(("READS", "USES"))})
        pack = {"run_id": run, "entity": ent["technical_name"], "entity_type": ent["asset_type"],
                "written_by": writers, "read_by": readers}
        (out / "entities" / f"{safe(ent['asset_type'])}_{safe(ent['technical_name'])}.json").write_text(
            json.dumps(pack, indent=2), encoding="utf-8")
        glossary["tables" if ent["asset_type"] == "TABLE" else "files"].append(ent["technical_name"])


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--db", required=True)
    ap.add_argument("--run-id")
    ap.add_argument("--out", default="journey-discovery/evidence")
    ap.add_argument("--depth", type=int, default=6)
    args = ap.parse_args()

    c = connect(args.db)
    run = args.run_id or latest_run(c)
    if not run:
        raise SystemExit("No run found in run_manifest — scan an estate first.")
    out = Path(args.out)
    (out / "entry_points").mkdir(parents=True, exist_ok=True)
    (out / "entities").mkdir(parents=True, exist_ok=True)

    glossary = {"transactions": [], "jobs": [], "tables": [], "files": [],
                "screens": set(), "programs": set()}
    index = export_entry_points(c, run, out, args.depth, glossary)
    export_entities(c, run, out, glossary)

    glossary = {k: sorted(v) for k, v in glossary.items()}
    (out / "glossary_seed.json").write_text(json.dumps(glossary, indent=2), encoding="utf-8")
    (out / "index.json").write_text(json.dumps({"run_id": run, "entry_points": index}, indent=2), encoding="utf-8")
    print(f"run={run}  entry_points={len(index)}  -> {out}")
    print("Next: open the JSON packs + glossary_seed.json in VS Code and run prompts/02-map-capability.prompt.md")


if __name__ == "__main__":
    main()
