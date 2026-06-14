"""MIP v0.1 CLI (stdlib argparse — no external dependency, runs anywhere).

    mip scan  <estate_path> [--db mip.db]     inventory + parse + load SQLite
    mip query "<question>"   [--db mip.db]     ask the metadata store
    mip roots                [--db mip.db]     list root/driver programs
    mip dead                 [--db mip.db]     list dead-code candidates
"""

from __future__ import annotations

import argparse
import sys

from . import queries, store
from .pipeline import build_db


def _cmd_scan(args: argparse.Namespace) -> int:
    c = build_db(args.estate, args.db)
    print(f"Scanned '{args.estate}' -> {args.db}")
    print(f"  artifacts : {c['artifacts']}  {c['by_type']}")
    print(f"  programs  : {c['programs']}")
    print(f"  jobs      : {c['jobs']}  (steps: {c['steps']})")
    print(f"  edges     : {c['edges']}  (needs_review: {c['needs_review_edges']})")
    return 0


def _print_rows(kind: str, result: object) -> None:
    if kind == "jobs_executing":
        print("Jobs that execute it:" if result else "No job executes it.")
        for j in result:  # type: ignore[union-attr]
            print(f"  - {j}")
    elif kind == "calls":
        for r in result:  # type: ignore[union-attr]
            flag = "" if r["validation_status"] == "confirmed" else f"  [{r['validation_status']} conf={r['confidence']}]"
            print(f"  CALLS {r['target_id']}{flag}")
    elif kind == "dependencies":
        for r in result:  # type: ignore[union-attr]
            flag = "" if r["validation_status"] == "confirmed" else f"  [{r['validation_status']} conf={r['confidence']}]"
            print(f"  {r['rel_type']:9} {r['target_type']}:{r['target_id']}{flag}")
    elif kind in ("roots", "dead_code"):
        for p in result:  # type: ignore[union-attr]
            print(f"  - {p}")
    else:
        print('Ask e.g.: "which jobs execute CRDPOST", "what does PAYDRV call", '
              '"show roots", "show dead code".')


def _cmd_query(args: argparse.Namespace) -> int:
    conn = store.connect(args.db)
    kind, result = queries.answer(conn, args.question)
    _print_rows(kind, result)
    conn.close()
    return 0


def _cmd_roots(args: argparse.Namespace) -> int:
    conn = store.connect(args.db)
    print("Root / driver programs:")
    _print_rows("roots", queries.roots(conn))
    conn.close()
    return 0


def _cmd_dead(args: argparse.Namespace) -> int:
    conn = store.connect(args.db)
    print("Dead-code candidates (needs_review - may be invoked dynamically/externally):")
    _print_rows("dead_code", queries.dead_code(conn))
    conn.close()
    return 0


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="mip", description="MIP v0.1 — mainframe discovery spine")
    sub = p.add_subparsers(dest="cmd", required=True)

    s = sub.add_parser("scan", help="inventory + parse + load SQLite")
    s.add_argument("estate", help="path to the mainframe estate")
    s.add_argument("--db", default="mip.db")
    s.set_defaults(func=_cmd_scan)

    q = sub.add_parser("query", help="ask the metadata store")
    q.add_argument("question")
    q.add_argument("--db", default="mip.db")
    q.set_defaults(func=_cmd_query)

    r = sub.add_parser("roots", help="list root/driver programs")
    r.add_argument("--db", default="mip.db")
    r.set_defaults(func=_cmd_roots)

    d = sub.add_parser("dead", help="list dead-code candidates")
    d.add_argument("--db", default="mip.db")
    d.set_defaults(func=_cmd_dead)
    return p


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
