"""Show what the default vs. advanced (ANTLR) parser backends extract from one COBOL file.

Answers the common question: "why do default and advanced give the same result?" On clean
COBOL inside the common subset they are at parity *by design* (there's a parity test). The
advanced backend's distinct value is its preprocessing stage — COPY ... REPLACING expansion,
EXEC folding, comment-paragraph stripping — which only changes the facts when a copybook
resolver is supplied. This script makes that visible.

It prints three columns of extracted facts for a file:
  1. default            — cobol_ast.parse(raw)                       (the default backend)
  2. advanced (raw)     — cobol_antlr.parse(raw), if the grammar is built   (parity → same)
  3. advanced+resolver  — parse AFTER COPY/REPLACING expansion with --copylib  (the difference)

Usage:
    uv run python scripts/parser_compare.py examples/advanced_parser/CARDADV \
        --copylib examples/advanced_parser
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_ROOT / "src"))

from mip import antlr_adapter, cobol_antlr, cobol_ast  # noqa: E402


def _facts(u) -> dict:
    return {
        "program_id": u.program_id,
        "calls": sorted((c["target"], c["validation"]) for c in u.calls),
        "copies": sorted(c["name"] for c in u.copies),
        "paragraphs": sorted(u.paragraphs),
        "data_items": len(u.data_items),
    }


def _show(title: str, facts: dict | None) -> None:
    print(f"\n[{title}]")
    if facts is None:
        print("  (unavailable)")
        return
    print(f"  program_id : {facts['program_id']}")
    print(f"  calls      : {facts['calls'] or '—'}")
    print(f"  copies     : {facts['copies'] or '—'}")
    print(f"  paragraphs : {facts['paragraphs'] or '—'}")
    print(f"  data_items : {facts['data_items']}")


def main() -> None:
    ap = argparse.ArgumentParser(description="Compare default vs advanced COBOL parser backends.")
    ap.add_argument("file", help="COBOL source file to parse")
    ap.add_argument("--copylib", help="directory whose copybooks the resolver should inline")
    args = ap.parse_args()

    text = Path(args.file).read_text(encoding="utf-8")

    _show("1. default — cobol_ast.parse(raw)", _facts(cobol_ast.parse(text)))

    adv = None
    if cobol_antlr.available():
        adv = _facts(cobol_antlr.parse(text))
    _show("2. advanced (raw) — ANTLR grammar, no resolver", adv)
    if adv is None:
        print("     ANTLR grammar not built (scripts/gen_grammar.py) — columns 1 and 2 are "
              "identical by parity when it is.")

    resolver = antlr_adapter.default_resolver(Path(args.copylib)) if args.copylib else None
    expanded = antlr_adapter.preprocess(text, resolver=resolver)
    _show("3. advanced + resolver — after COPY/REPLACING expansion", _facts(cobol_ast.parse(expanded)))

    print("\n--- the expansion the advanced backend performs (preprocess output) ---")
    for line in expanded.splitlines():
        if line.strip():
            print("  " + line)
    print("\nTakeaway: columns 1 and 2 match (parity on clean code). Column 3 shows the CALL the\n"
          "default parser cannot see — recovered by the advanced backend's COPY ... REPLACING\n"
          "expander once a copybook resolver is supplied.")


if __name__ == "__main__":
    main()
