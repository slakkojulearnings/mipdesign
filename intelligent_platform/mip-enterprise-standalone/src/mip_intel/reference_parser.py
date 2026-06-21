from __future__ import annotations

import re
from typing import Any, Callable

from .cobol_antlr import cobol_ast


PARSER_VERSION = "cobol-antlr4-proleap-4.13.2+mip-adapter-v2"


class CopybookResolver:
    def __init__(
        self,
        copybooks: dict[str, str],
        metadata: dict[str, dict[str, Any]] | None = None,
    ) -> None:
        self._copybooks = {_clean_name(name): text for name, text in copybooks.items()}
        self._metadata = {_clean_name(name): value for name, value in (metadata or {}).items()}
        self.resolved: set[str] = set()
        self.missing: set[str] = set()

    def __call__(self, name: str) -> str | None:
        key = _clean_name(name)
        text = self._copybooks.get(key)
        if text is None:
            self.missing.add(key)
            return None
        self.resolved.add(key)
        return text

    def diagnostics(self, copies: list[dict[str, Any]]) -> list[dict[str, Any]]:
        rows = []
        for copy in copies:
            name = _clean_name(str(copy.get("name", "")))
            if not name:
                continue
            info = dict(self._metadata.get(name, {}))
            resolved = name in self._copybooks
            rows.append(
                {
                    "name": name,
                    "resolved": resolved,
                    "source_path": info.get("source_path"),
                    "artifact_type": info.get("artifact_type"),
                    "confidence": 0.95 if resolved else 0.35,
                    "validation_status": "confirmed" if resolved else "needs_review",
                    "selected_by": info.get("selected_by"),
                    "candidate_count": info.get("candidate_count", 0),
                    "conflict": bool(info.get("conflict", False)),
                    "candidates": info.get("candidates", []),
                }
            )
        return rows


def _load_local_modules():
    try:
        from .cobol_antlr import antlr_adapter, cobol_ast, cobol_antlr
    except Exception:
        return None, None, None
    return antlr_adapter, cobol_ast, cobol_antlr


def available() -> bool:
    antlr_adapter, cobol_ast, _ = _load_local_modules()
    return antlr_adapter is not None and cobol_ast is not None


def antlr4_ready() -> bool:
    _, _, cobol_antlr = _load_local_modules()
    return bool(cobol_antlr and cobol_antlr.available())


def copybook_resolver(
    copybooks: dict[str, str],
    metadata: dict[str, dict[str, Any]] | None = None,
) -> CopybookResolver:
    return CopybookResolver(copybooks, metadata)


def parse_cobol(text: str, resolver: Callable[[str], str | None] | None = None) -> dict[str, Any]:
    """Return a canonical parser payload using the vendored parser package.

    When `antlr4-python3-runtime` is installed, the generated COBOL-85 grammar is used.
    If the runtime is missing or a source member falls outside grammar coverage, the
    local COPY/REPLACING preprocessor plus local AST parser still recovers evidence and
    records the degraded parser mode in the payload.
    """
    antlr_adapter, cobol_ast, cobol_antlr = _load_local_modules()
    if cobol_ast is None:
        return _fallback_parse(text)

    raw_unit = cobol_ast.parse(text)
    expanded_text = text
    parser_backend_info = {
        "requested": "local-antlr4",
        "source": "mip_intel.cobol_antlr",
        "version": PARSER_VERSION,
        "antlr4_available": bool(cobol_antlr and cobol_antlr.available()),
        "effective": "local-cobol_ast",
    }
    if cobol_antlr is not None and cobol_antlr.available():
        try:
            expanded_text = antlr_adapter.preprocess(text, resolver=resolver)
            # Reuse the preprocessed text so cobol_antlr does not preprocess a second time.
            expanded_unit = cobol_antlr.parse(text, resolver=resolver, pre=expanded_text)
            parser_backend_info["effective"] = "local-antlr4-full-grammar"
            return _unit_payload(raw_unit, expanded_unit, text, expanded_text, parser_backend_info, resolver)
        except Exception as exc:
            parser_backend_info["antlr4_error"] = type(exc).__name__
    if antlr_adapter is not None:
        expanded_text = antlr_adapter.preprocess(text, resolver=resolver)
        parser_backend_info["effective"] = "local-copy-replacing-preprocessor+cobol_ast"
    expanded_unit = cobol_ast.parse(expanded_text)
    return _unit_payload(raw_unit, expanded_unit, text, expanded_text, parser_backend_info, resolver)


def ast_tree(payload: dict[str, Any]) -> dict[str, Any]:
    program = payload.get("program_id") or "UNKNOWN"
    divisions = [
        {"type": "division", "label": division, "children": []}
        for division in payload.get("divisions", [])
    ]
    data_by_section: dict[str, list[dict[str, Any]]] = {}
    for item in payload.get("data_items", []):
        data_by_section.setdefault(item.get("section") or "UNSECTIONED", []).append(
            {
                "type": "data_item",
                "label": item.get("name"),
                "level": item.get("level"),
                "pic": item.get("pic"),
                "line": item.get("line"),
                "redefines": item.get("redefines"),
                "occurs": item.get("occurs"),
                "occurs_to": item.get("occurs_to"),
                "depending_on": item.get("depending_on"),
                "usage": item.get("usage"),
                "value": item.get("value"),
                "condition_name": item.get("condition_name"),
            }
        )
    data_children = [
        {"type": "section", "label": section, "children": rows}
        for section, rows in sorted(data_by_section.items())
    ]
    procedure_children = [
        {"type": "paragraph", "label": name, "children": []}
        for name in payload.get("paragraphs", [])
    ]
    dependency_children = []
    for copy in payload.get("copies", []):
        dependency_children.append(
            {"type": "copybook", "label": copy.get("name"), "line": copy.get("line")}
        )
    for call in payload.get("calls", []):
        dependency_children.append(
            {
                "type": "call",
                "label": call.get("target"),
                "line": call.get("line"),
                "confidence": call.get("confidence"),
                "validation_status": call.get("validation"),
            }
        )
    for sql in payload.get("sql", []):
        dependency_children.append(
            {"type": "sql", "label": f"{sql.get('op')} {sql.get('table')}", "line": sql.get("line")}
        )
    return {
        "type": "program",
        "label": program,
        "children": [
            {"type": "divisions", "label": "Divisions", "children": divisions},
            {"type": "data", "label": "Data Division", "children": data_children},
            {"type": "procedure", "label": "Procedure Division", "children": procedure_children},
            {"type": "dependencies", "label": "Dependencies", "children": dependency_children},
        ],
        "counts": payload.get("counts", {}),
        "complexity": payload.get("complexity", 1),
        "parser": payload.get("parser", {}),
    }


def _unit_payload(
    raw_unit,
    expanded_unit,
    raw_text: str,
    expanded_text: str,
    parser: dict[str, Any],
    resolver: Callable[[str], str | None] | None = None,
) -> dict[str, Any]:
    copy_resolution = (
        resolver.diagnostics(list(raw_unit.copies))
        if hasattr(resolver, "diagnostics")
        else []
    )
    parser["confidence"] = _parser_confidence(parser, copy_resolution)
    parser["validation_status"] = "needs_review" if parser["confidence"] < 0.7 else "confirmed"
    return {
        "program_id": expanded_unit.program_id or raw_unit.program_id,
        "divisions": list(expanded_unit.divisions or raw_unit.divisions),
        "paragraphs": list(expanded_unit.paragraphs),
        "data_items": list(expanded_unit.data_items),
        "calls": list(expanded_unit.calls),
        "copies": list(raw_unit.copies),
        "sql": list(expanded_unit.sql or raw_unit.sql),
        "cics": list(expanded_unit.cics or raw_unit.cics),
        "field_flows": list(expanded_unit.field_flows),
        "counts": dict(expanded_unit.counts or raw_unit.counts),
        "complexity": int(expanded_unit.complexity or raw_unit.complexity or 1),
        "expanded": expanded_text != "",
        "copy_replacing": _copy_replacing(raw_text),
        "copy_resolution": copy_resolution,
        "dialect_profile": _dialect_profile(raw_text),
        "data_layout": cobol_ast.data_layout(list(expanded_unit.data_items)),
        "procedure_outline": cobol_ast.procedure_outline(expanded_text),
        "business_rules": cobol_ast.business_rules(
            expanded_text,
            expanded_unit.program_id or raw_unit.program_id or "UNKNOWN",
            "",
        ),
        "parser": parser,
    }


def _parser_confidence(parser: dict[str, Any], copy_resolution: list[dict[str, Any]]) -> float:
    effective = str(parser.get("effective", ""))
    confidence = 0.95 if effective == "local-antlr4-full-grammar" else 0.78
    if parser.get("antlr4_error"):
        confidence = min(confidence, 0.68)
    if effective == "fallback-regex":
        confidence = min(confidence, 0.45)
    if any(not row.get("resolved") for row in copy_resolution):
        confidence = min(confidence, 0.70)
    return round(confidence, 2)


def _dialect_profile(text: str) -> dict[str, Any]:
    upper = text.upper()
    signals = []
    if "EXEC CICS" in upper:
        signals.append("CICS")
    if "EXEC SQL" in upper:
        signals.append("DB2_SQL")
    if "ENTRY " in upper:
        signals.append("MULTI_ENTRY")
    if re.search(r"(?m)^\s{0,6}[*/-]", text):
        signals.append("FIXED_FORMAT_INDICATOR_AREA")
    if "EVALUATE " in upper:
        signals.append("COBOL85_EVALUATE")
    return {
        "source_format": "fixed-or-free",
        "signals": sorted(set(signals)),
        "confidence": 0.75 if signals else 0.5,
        "validation_status": "inferred",
    }


def _copy_replacing(source_text: str) -> list[dict[str, Any]]:
    rows = []
    for line_no, line in enumerate(source_text.splitlines(), 1):
        if " REPLACING " in line.upper():
            rows.append({"line": line_no, "text": line.strip()[:300]})
    return rows


def _fallback_parse(text: str) -> dict[str, Any]:
    program = None
    match = re.search(r"\bPROGRAM-ID\s*\.\s*([A-Z0-9#$@_-]+)", text, re.I)
    if match:
        program = match.group(1).upper()
    copies = [
        {"name": m.group(1).upper(), "line": text[: m.start()].count("\n") + 1}
        for m in re.finditer(r"\bCOPY\s+([A-Z0-9#$@_-]+)", text, re.I)
    ]
    calls = [
        {
            "target": m.group(1).upper(),
            "kind": "static",
            "line": text[: m.start()].count("\n") + 1,
            "confidence": 1.0,
            "validation": "confirmed",
        }
        for m in re.finditer(r"\bCALL\s+['\"]([A-Z0-9#$@_-]+)['\"]", text, re.I)
    ]
    counts = {"CALL": len(calls), "COPY": len(copies)}
    return {
        "program_id": program,
        "divisions": [name for name in ("IDENTIFICATION", "ENVIRONMENT", "DATA", "PROCEDURE") if f"{name} DIVISION" in text.upper()],
        "paragraphs": [],
        "data_items": [],
        "calls": calls,
        "copies": copies,
        "sql": [],
        "cics": [],
        "field_flows": [],
        "counts": counts,
        "complexity": 1,
        "expanded": False,
        "copy_replacing": [],
        "copy_resolution": [],
        "dialect_profile": _dialect_profile(text),
        "parser": {
            "requested": "fallback-regex",
            "effective": "fallback-regex",
            "version": PARSER_VERSION,
            "confidence": 0.45,
            "validation_status": "needs_review",
        },
    }


def _clean_name(value: str) -> str:
    return value.strip().strip("'\"()[],.").upper()
