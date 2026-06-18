from __future__ import annotations

import re
from collections import defaultdict
from dataclasses import dataclass
from pathlib import Path
from typing import Any

_COPY = re.compile(r"\bCOPY\s+([A-Z0-9@$#-]+)(.*?)(?:\.|$)", re.I)
_REPLACING = re.compile(
    r"==([^=]+)==\s+BY\s+==([^=]+)==|\b([A-Z0-9@$#:-]+)\b\s+BY\s+\b([A-Z0-9@$#:-]+)\b",
    re.I,
)
_PROGRAM_ID = re.compile(r"\bPROGRAM-ID\s*\.\s*([A-Z0-9@$#-]+)", re.I)
_DATA_ENTRY = re.compile(r"^(\d{1,2}|66|77|78|88)\s+([A-Z0-9@$#-]+)\s*(.*?)(?:\.)?$", re.I)
_PIC = re.compile(r"\bPIC(?:TURE)?\s+([^\s.]+)", re.I)
_USAGE = re.compile(
    r"\b(?:USAGE\s+(?:IS\s+)?)?(COMP-1|COMP-2|COMP-3|COMP-4|COMP-5|COMP|BINARY|DISPLAY|NATIONAL|POINTER|INDEX)\b",
    re.I,
)
_VALUE = re.compile(
    r"\bVALUE(?:S)?(?:\s+IS|\s+ARE)?\s+(.+?)(?=\s+(?:PIC|USAGE|OCCURS|REDEFINES|RENAMES|SIGN|SYNC)\b|$)",
    re.I,
)
_REDEFINES = re.compile(r"\bREDEFINES\s+([A-Z0-9@$#-]+)", re.I)
_RENAMES = re.compile(r"\bRENAMES\s+([A-Z0-9@$#-]+)(?:\s+THRU\s+([A-Z0-9@$#-]+))?", re.I)
_OCCURS = re.compile(
    r"\bOCCURS\s+(\d+)(?:\s+TO\s+(\d+))?\s+TIMES(?:\s+DEPENDING\s+ON\s+([A-Z0-9@$#-]+))?", re.I
)
_CALL_STATIC = re.compile(r"\bCALL\s+['\"]([^'\"]+)['\"]", re.I)
_CALL_DYNAMIC = re.compile(r"\bCALL\s+([A-Z][A-Z0-9@$#-]*)", re.I)
_MOVE_LITERAL = re.compile(r"\bMOVE\s+['\"]([^'\"]+)['\"]\s+TO\s+([A-Z0-9@$#-]+)", re.I)
_SET_LITERAL = re.compile(
    r"\bSET\s+([A-Z0-9@$#-]+)\s+TO\s+(?:ADDRESS\s+OF\s+)?['\"]?([A-Z0-9@$#-]+)['\"]?", re.I
)
_PARAGRAPH = re.compile(r"^([A-Z0-9][A-Z0-9-]+)\s*\.\s*$", re.I)
_PERFORM = re.compile(r"\bPERFORM\s+([A-Z0-9-]+)(?:\s+THRU\s+([A-Z0-9-]+))?", re.I)
_GOTO = re.compile(r"\bGO\s+TO\s+([A-Z0-9-]+)(?:\s+DEPENDING\s+ON\s+([A-Z0-9-]+))?", re.I)
_ALTER = re.compile(r"\bALTER\s+([A-Z0-9-]+)\s+TO\s+PROCEED\s+TO\s+([A-Z0-9-]+)", re.I)
_IF = re.compile(r"\bIF\s+(.+?)(?:\s+THEN\b|$)", re.I)
_EVALUATE = re.compile(r"\bEVALUATE\s+(.+)$", re.I)
_WHEN = re.compile(r"\bWHEN\s+(.+)$", re.I)
_COMPUTE = re.compile(r"\bCOMPUTE\s+([A-Z0-9-]+)\s*=\s*(.+)$", re.I)
_ADD = re.compile(r"\b(ADD|SUBTRACT|MULTIPLY|DIVIDE)\s+(.+)$", re.I)
_DIRECTIVE = re.compile(r"^>>\s*(IF|ELSE|END-IF|DEFINE)\b\s*(.*)$", re.I)


@dataclass(frozen=True)
class ExpandedLine:
    source: str
    line: int
    text: str
    expansion_stack: tuple[str, ...] = ()


class CobolSemanticAnalyzer:
    """Compiler-oriented, deterministic COBOL source understanding.

    It is not a replacement for a licensed compiler. It provides source expansion,
    symbol tables, control-flow edges, dynamic-call resolution, and structured rules
    for analysis and modernization workflows.
    """

    def __init__(
        self, copybook_dirs: list[Path] | None = None, defines: set[str] | None = None
    ) -> None:
        self.copybook_dirs = [path.resolve() for path in (copybook_dirs or [])]
        self.defines = {item.upper() for item in (defines or set())}
        self._copybook_index = self._index_copybooks()

    def analyze_file(self, source_path: Path) -> dict[str, Any]:
        source_path = source_path.resolve()
        expanded, issues = self.expand_source(source_path)
        statements = self._statements(expanded)
        text = "\n".join(item.text for item in expanded)
        program_match = _PROGRAM_ID.search(text)
        program_name = program_match.group(1).upper() if program_match else source_path.stem.upper()
        symbols = self._symbol_table(statements)
        cfg = self._control_flow(statements)
        calls = self._calls(statements, symbols)
        rules = self._rules(statements)
        return {
            "program": program_name,
            "source": str(source_path),
            "expanded_line_count": len(expanded),
            "copybooks": sorted({name for line in expanded for name in line.expansion_stack}),
            "symbols": symbols,
            "control_flow": cfg,
            "calls": calls,
            "business_rules": rules,
            "issues": issues,
            "expanded_source": [
                {
                    "source": line.source,
                    "line": line.line,
                    "text": line.text,
                    "expansion_stack": list(line.expansion_stack),
                }
                for line in expanded
            ],
        }

    def expand_source(self, source_path: Path) -> tuple[list[ExpandedLine], list[dict[str, Any]]]:
        issues: list[dict[str, Any]] = []
        lines = self._read_logical_lines(source_path)
        active_lines = self._apply_directives(lines, issues)
        expanded = self._expand_copy_lines(active_lines, (), issues, set())
        return expanded, issues

    def _index_copybooks(self) -> dict[str, Path]:
        result: dict[str, Path] = {}
        for directory in self.copybook_dirs:
            if not directory.exists():
                continue
            for path in directory.rglob("*"):
                if path.is_file():
                    result[path.stem.upper()] = path
                    result[path.name.upper()] = path
        return result

    def _read_logical_lines(self, path: Path) -> list[ExpandedLine]:
        raw = path.read_text(encoding="utf-8", errors="replace").splitlines()
        result: list[ExpandedLine] = []
        buffer = ""
        start = 1
        for number, line in enumerate(raw, 1):
            if len(line) >= 7 and line[:6].strip().isdigit():
                indicator = line[6:7]
                body = line[7:72]
                if indicator in {"*", "/"}:
                    continue
                if indicator == "-":
                    buffer += body.strip()
                    continue
                if buffer:
                    result.append(ExpandedLine(str(path), start, buffer.strip()))
                buffer = body.rstrip()
                start = number
            else:
                stripped = line.strip()
                if not stripped or stripped.startswith("*>"):
                    continue
                if buffer:
                    result.append(ExpandedLine(str(path), start, buffer.strip()))
                buffer = stripped
                start = number
        if buffer:
            result.append(ExpandedLine(str(path), start, buffer.strip()))
        return result

    def _apply_directives(
        self, lines: list[ExpandedLine], issues: list[dict[str, Any]]
    ) -> list[ExpandedLine]:
        output: list[ExpandedLine] = []
        active_stack = [True]
        for line in lines:
            match = _DIRECTIVE.match(line.text)
            if not match:
                if all(active_stack):
                    output.append(line)
                continue
            command, argument = match.group(1).upper(), match.group(2).strip()
            if command == "DEFINE":
                if all(active_stack) and argument:
                    self.defines.add(argument.split()[0].upper())
            elif command == "IF":
                symbol = re.sub(r"^DEFINED\s*\(|\)$", "", argument, flags=re.I).strip().upper()
                negate = symbol.startswith("NOT ")
                if negate:
                    symbol = symbol[4:].strip()
                state = symbol in self.defines
                active_stack.append((not state if negate else state) and all(active_stack))
            elif command == "ELSE":
                if len(active_stack) == 1:
                    issues.append(
                        {"kind": "DIRECTIVE", "line": line.line, "message": "orphan ELSE"}
                    )
                else:
                    parent = all(active_stack[:-1])
                    active_stack[-1] = parent and not active_stack[-1]
            elif command == "END-IF":
                if len(active_stack) == 1:
                    issues.append(
                        {"kind": "DIRECTIVE", "line": line.line, "message": "orphan END-IF"}
                    )
                else:
                    active_stack.pop()
        if len(active_stack) != 1:
            issues.append({"kind": "DIRECTIVE", "line": None, "message": "unclosed compiler IF"})
        return output

    def _expand_copy_lines(
        self,
        lines: list[ExpandedLine],
        stack: tuple[str, ...],
        issues: list[dict[str, Any]],
        visiting: set[str],
    ) -> list[ExpandedLine]:
        output: list[ExpandedLine] = []
        for line in lines:
            match = _COPY.search(line.text)
            if not match:
                output.append(ExpandedLine(line.source, line.line, line.text, stack))
                continue
            name = match.group(1).upper()
            path = self._copybook_index.get(name)
            replacements = self._replacement_pairs(match.group(2))
            if path is None:
                issues.append(
                    {
                        "kind": "COPY",
                        "line": line.line,
                        "member": name,
                        "message": "copybook not found",
                    }
                )
                output.append(ExpandedLine(line.source, line.line, line.text, stack))
                continue
            key = str(path)
            if key in visiting:
                issues.append(
                    {
                        "kind": "COPY",
                        "line": line.line,
                        "member": name,
                        "message": "copybook cycle detected",
                    }
                )
                continue
            visiting.add(key)
            copied = self._read_logical_lines(path)
            transformed = [
                ExpandedLine(
                    item.source,
                    item.line,
                    self._replace_text(item.text, replacements),
                    stack + (name,),
                )
                for item in copied
            ]
            output.extend(self._expand_copy_lines(transformed, stack + (name,), issues, visiting))
            visiting.remove(key)
        return output

    @staticmethod
    def _replacement_pairs(text: str) -> list[tuple[str, str]]:
        pairs: list[tuple[str, str]] = []
        for match in _REPLACING.finditer(text):
            old = (match.group(1) or match.group(3) or "").strip()
            new = (match.group(2) or match.group(4) or "").strip()
            if old:
                pairs.append((old, new))
        return pairs

    @staticmethod
    def _replace_text(text: str, pairs: list[tuple[str, str]]) -> str:
        value = text
        for old, new in pairs:
            value = value.replace(old, new)
            value = re.sub(rf"(?<![A-Z0-9-]){re.escape(old)}(?![A-Z0-9-])", new, value, flags=re.I)
        return value

    @staticmethod
    def _statements(lines: list[ExpandedLine]) -> list[dict[str, Any]]:
        result: list[dict[str, Any]] = []
        buffer: list[str] = []
        start: ExpandedLine | None = None
        for line in lines:
            if start is None:
                start = line
            buffer.append(line.text)
            joined = " ".join(buffer)
            while "." in joined:
                statement, joined = joined.split(".", 1)
                if statement.strip():
                    assert start is not None
                    result.append(
                        {
                            "source": start.source,
                            "line": start.line,
                            "text": " ".join(statement.split()),
                            "expansion_stack": list(start.expansion_stack),
                        }
                    )
                buffer = [joined] if joined.strip() else []
                start = line if buffer else None
        if buffer and start:
            result.append(
                {
                    "source": start.source,
                    "line": start.line,
                    "text": " ".join(" ".join(buffer).split()),
                    "expansion_stack": list(start.expansion_stack),
                }
            )
        return result

    def _symbol_table(self, statements: list[dict[str, Any]]) -> list[dict[str, Any]]:
        symbols: list[dict[str, Any]] = []
        parents: list[tuple[int, str]] = []
        for statement in statements:
            match = _DATA_ENTRY.match(statement["text"])
            if not match:
                continue
            level = int(match.group(1))
            name = match.group(2).upper()
            rest = match.group(3)
            while parents and parents[-1][0] >= level and level not in {66, 88}:
                parents.pop()
            parent = parents[-1][1] if parents else None
            if level not in {66, 77, 78, 88}:
                parents.append((level, name))
            occurs = _OCCURS.search(rest)
            redefines = _REDEFINES.search(rest)
            renames = _RENAMES.search(rest)
            pic = _PIC.search(rest)
            usage = _USAGE.search(rest)
            value = _VALUE.search(rest)
            symbols.append(
                {
                    "name": name,
                    "level": level,
                    "parent": parent,
                    "pic": pic.group(1).upper() if pic else None,
                    "usage": usage.group(1).upper() if usage else "DISPLAY",
                    "value": value.group(1).strip() if value else None,
                    "redefines": redefines.group(1).upper() if redefines else None,
                    "renames_from": renames.group(1).upper() if renames else None,
                    "renames_thru": renames.group(2).upper()
                    if renames and renames.group(2)
                    else None,
                    "occurs_min": int(occurs.group(1)) if occurs else None,
                    "occurs_max": int(occurs.group(2) or occurs.group(1)) if occurs else None,
                    "depending_on": occurs.group(3).upper() if occurs and occurs.group(3) else None,
                    "condition_name": level == 88,
                    "source": statement["source"],
                    "line": statement["line"],
                }
            )
        return symbols

    def _calls(
        self, statements: list[dict[str, Any]], symbols: list[dict[str, Any]]
    ) -> list[dict[str, Any]]:
        values: dict[str, set[str]] = defaultdict(set)
        for symbol in symbols:
            if symbol.get("value"):
                literal = str(symbol["value"]).strip("'\"").split()[0]
                if literal:
                    values[str(symbol["name"])].add(literal.upper())
        for statement in statements:
            text = statement["text"]
            if match := _MOVE_LITERAL.search(text):
                values[match.group(2).upper()].add(match.group(1).upper())
            if match := _SET_LITERAL.search(text):
                values[match.group(1).upper()].add(match.group(2).upper())
        calls: list[dict[str, Any]] = []
        for statement in statements:
            text = statement["text"]
            for match in _CALL_STATIC.finditer(text):
                calls.append(
                    {
                        "kind": "STATIC",
                        "target": match.group(1).upper(),
                        "confidence": 1.0,
                        "source": statement["source"],
                        "line": statement["line"],
                    }
                )
            if _CALL_STATIC.search(text):
                continue
            match = _CALL_DYNAMIC.search(text)
            if match:
                variable = match.group(1).upper()
                candidates = sorted(values.get(variable, set()))
                calls.append(
                    {
                        "kind": "DYNAMIC_RESOLVED" if candidates else "DYNAMIC_UNRESOLVED",
                        "variable": variable,
                        "targets": candidates,
                        "confidence": 0.9
                        if len(candidates) == 1
                        else (0.7 if candidates else 0.35),
                        "source": statement["source"],
                        "line": statement["line"],
                    }
                )
        return calls

    def _control_flow(self, statements: list[dict[str, Any]]) -> dict[str, Any]:
        paragraphs: list[str] = []
        current = "PROCEDURE-ENTRY"
        edges: list[dict[str, Any]] = []
        altered: dict[str, str] = {}
        for statement in statements:
            text = statement["text"]
            if match := _PARAGRAPH.match(text + "."):
                current = match.group(1).upper()
                paragraphs.append(current)
                continue
            for match in _PERFORM.finditer(text):
                edges.append(
                    {
                        "from": current,
                        "to": match.group(1).upper(),
                        "kind": "PERFORM",
                        "thru": match.group(2).upper() if match.group(2) else None,
                        "line": statement["line"],
                    }
                )
            for match in _GOTO.finditer(text):
                edges.append(
                    {
                        "from": current,
                        "to": match.group(1).upper(),
                        "kind": "GO_TO_DEPENDING" if match.group(2) else "GO_TO",
                        "depending_on": match.group(2).upper() if match.group(2) else None,
                        "line": statement["line"],
                    }
                )
            for match in _ALTER.finditer(text):
                altered[match.group(1).upper()] = match.group(2).upper()
                edges.append(
                    {
                        "from": current,
                        "to": match.group(2).upper(),
                        "kind": "ALTER",
                        "altered_paragraph": match.group(1).upper(),
                        "line": statement["line"],
                    }
                )
        return {"paragraphs": sorted(set(paragraphs)), "edges": edges, "alter_targets": altered}

    def _rules(self, statements: list[dict[str, Any]]) -> list[dict[str, Any]]:
        rules: list[dict[str, Any]] = []
        evaluate_subject: str | None = None
        for statement in statements:
            text = statement["text"]
            if match := _IF.search(text):
                rules.append(self._rule("CONDITION", match.group(1), statement))
            if match := _EVALUATE.search(text):
                evaluate_subject = match.group(1).strip()
                rules.append(self._rule("DECISION_TABLE", evaluate_subject, statement))
            if match := _WHEN.search(text):
                expression = f"{evaluate_subject or 'EVALUATE'} WHEN {match.group(1).strip()}"
                rules.append(self._rule("DECISION_BRANCH", expression, statement))
            if match := _COMPUTE.search(text):
                rules.append(
                    self._rule(
                        "CALCULATION",
                        f"{match.group(1).upper()} = {match.group(2).strip()}",
                        statement,
                    )
                )
            if match := _ADD.search(text):
                rules.append(
                    self._rule(
                        "ARITHMETIC",
                        f"{match.group(1).upper()} {match.group(2).strip()}",
                        statement,
                    )
                )
        return rules

    @staticmethod
    def _rule(kind: str, expression: str, statement: dict[str, Any]) -> dict[str, Any]:
        normalized = " ".join(expression.split())
        confidence = 0.98 if kind in {"CALCULATION", "CONDITION"} else 0.9
        return {
            "kind": kind,
            "expression": normalized,
            "source": statement["source"],
            "line": statement["line"],
            "confidence": confidence,
        }
