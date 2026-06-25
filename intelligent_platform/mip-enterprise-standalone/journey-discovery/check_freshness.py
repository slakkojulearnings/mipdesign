#!/usr/bin/env python3
"""Freshness-check an org glossary (mined from SME docs/PPTs) against the live DB.

The docs/PPTs hold what the business CALLS things and what it BELIEVES the journeys are
— but some are stale. This sorts them automatically: a glossary term whose named
programs/transactions still exist in the database is RELEVANT; one whose assets are
gone is OBSOLETE. Mismatch is signal, not noise.

Input glossary JSON (produced by prompts/01-mine-glossary.prompt.md):
  {"terms": [
     {"term": "Card Onboarding", "kind": "capability",
      "named_assets": ["CARDACT", "CRDACT01", "CARD_MASTER"], "source_doc": "deck_2019.pptx"}
  ]}

Usage:
  python check_freshness.py --db data/estate.db --glossary journey-discovery/glossary.json \
         [--run-id RUN] [--out journey-discovery/glossary_freshness.json]
"""
from __future__ import annotations
import argparse, json, sqlite3
from pathlib import Path


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--db", required=True)
    ap.add_argument("--glossary", required=True)
    ap.add_argument("--run-id")
    ap.add_argument("--out", default="journey-discovery/glossary_freshness.json")
    args = ap.parse_args()

    c = sqlite3.connect(args.db)
    c.row_factory = sqlite3.Row
    run = args.run_id or (c.execute("SELECT run_id FROM run_manifest ORDER BY started_at DESC LIMIT 1").fetchone() or {})
    run = run["run_id"] if run else None
    if not run:
        raise SystemExit("No run found.")

    live = {r["technical_name"].upper()
            for r in c.execute("SELECT technical_name FROM asset WHERE run_id=?", (run,))}

    glossary = json.loads(Path(args.glossary).read_text(encoding="utf-8"))
    report = []
    for term in glossary.get("terms", []):
        named = [str(a).upper() for a in term.get("named_assets", [])]
        present = [a for a in named if a in live]
        missing = [a for a in named if a not in live]
        freshness = round(len(present) / len(named), 2) if named else 0.0
        status = "relevant" if freshness >= 0.5 else ("stale" if present else "obsolete")
        report.append({**term, "present": present, "missing": missing,
                       "freshness": freshness, "status": status})

    counts = {}
    for r in report:
        counts[r["status"]] = counts.get(r["status"], 0) + 1
    Path(args.out).write_text(json.dumps({"run_id": run, "summary": counts, "terms": report}, indent=2),
                              encoding="utf-8")
    print(f"run={run}  {counts}  -> {args.out}")
    print("relevant = use its words & journeys; stale = verify; obsolete = exclude from the live journey map.")


if __name__ == "__main__":
    main()
