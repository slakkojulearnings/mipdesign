"""Pluggable COBOL parser backend — choose `default` or `advanced`.

  MIP_PARSER=default   (out of the box) -> the self-contained grammar parser (cobol_ast)
  MIP_PARSER=advanced                    -> the ANTLR COBOL-85 backend (cobol_antlr) IF the
                                            grammar has been generated; otherwise it falls
                                            back to default with `effective=default`.

All call sites (cobol.py, api.py) go through `parse()` so the choice applies everywhere.
`backend_info()` reports what's requested vs. what's actually in effect — surfaced at
/api/health so the active parser is never a mystery.
"""

from __future__ import annotations

import os

from . import cobol_ast


def requested() -> str:
    return os.environ.get("MIP_PARSER", "default").strip().lower()


def _advanced_ready() -> bool:
    try:
        from . import cobol_antlr
        return cobol_antlr.available()
    except Exception:
        return False


def effective() -> str:
    return "advanced" if (requested() == "advanced" and _advanced_ready()) else "default"


def parse(text: str):
    if effective() == "advanced":
        from . import cobol_antlr
        return cobol_antlr.parse(text)
    return cobol_ast.parse(text)


def backend_info() -> dict:
    return {"requested": requested(), "advanced_available": _advanced_ready(),
            "effective": effective()}
