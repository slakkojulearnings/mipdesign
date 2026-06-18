from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any

_PROC_START = re.compile(r"^//([A-Z0-9@$#]+)\s+PROC\b(.*)$", re.I)
_PEND = re.compile(r"^//\s*PEND\b", re.I)
_SET = re.compile(r"^//\s*SET\s+(.+)$", re.I)
_INCLUDE = re.compile(r"^//\s*INCLUDE\s+MEMBER\s*=\s*([A-Z0-9@$#]+)", re.I)
_EXEC_PROC = re.compile(r"^//([A-Z0-9@$#.]*)\s+EXEC\s+(?:PROC\s*=\s*)?([A-Z0-9@$#]+)(.*)$", re.I)
_EXEC_PGM = re.compile(r"^//([A-Z0-9@$#.]*)\s+EXEC\s+PGM\s*=", re.I)
_SYMBOL = re.compile(r"&([A-Z0-9@$#]+)\.?", re.I)
_ASSIGNMENT = re.compile(r"(?:^|,)\s*([A-Z0-9@$#]+)\s*=\s*([^,]+)", re.I)
_OVERRIDE = re.compile(r"^//([A-Z0-9@$#]+)\.([A-Z0-9@$#]+)\s+DD\b(.*)$", re.I)


@dataclass(frozen=True)
class JclLine:
    source: str
    line: int
    text: str
    expansion_stack: tuple[str, ...] = ()


@dataclass
class Procedure:
    name: str
    parameters: dict[str, str]
    body: list[JclLine]
    source: str


class EnterpriseJclExpander:
    """Deterministic JCL/PROC/INCLUDE symbolic expansion with traceability."""

    def __init__(self, proclib_dirs: list[Path] | None = None, max_depth: int = 32) -> None:
        self.proclib_dirs = [item.resolve() for item in (proclib_dirs or [])]
        self.max_depth = max_depth
        self._members = self._index_members()
        self._procedure_cache: dict[str, Procedure] = {}

    def expand_file(
        self, source_path: Path, symbols: dict[str, str] | None = None
    ) -> dict[str, Any]:
        source_path = source_path.resolve()
        initial = {key.upper(): value for key, value in (symbols or {}).items()}
        lines = self._read_lines(source_path)
        inline, executable = self._extract_inline_procs(lines)
        self._procedure_cache.update(inline)
        trace: list[dict[str, Any]] = []
        issues: list[dict[str, Any]] = []
        expanded = self._expand_lines(executable, initial, (), trace, issues, 0)
        return {
            "source": str(source_path),
            "symbols": initial,
            "expanded_lines": [
                {
                    "source": line.source,
                    "line": line.line,
                    "text": line.text,
                    "expansion_stack": list(line.expansion_stack),
                }
                for line in expanded
            ],
            "trace": trace,
            "issues": issues,
            "resolved_programs": self._resolved_programs(expanded),
        }

    def _index_members(self) -> dict[str, Path]:
        result: dict[str, Path] = {}
        for directory in self.proclib_dirs:
            if not directory.exists():
                continue
            for path in directory.rglob("*"):
                if path.is_file():
                    result[path.name.upper()] = path
                    result[path.stem.upper()] = path
        return result

    @staticmethod
    def _read_lines(path: Path) -> list[JclLine]:
        return [
            JclLine(str(path), number, line.rstrip())
            for number, line in enumerate(
                path.read_text(encoding="utf-8", errors="replace").splitlines(), 1
            )
            if line.strip()
        ]

    def _extract_inline_procs(
        self, lines: list[JclLine]
    ) -> tuple[dict[str, Procedure], list[JclLine]]:
        procedures: dict[str, Procedure] = {}
        executable: list[JclLine] = []
        current_name: str | None = None
        current_params: dict[str, str] = {}
        current_body: list[JclLine] = []
        current_source = ""
        for line in lines:
            if current_name is None:
                start = _PROC_START.match(line.text)
                if start:
                    current_name = start.group(1).upper()
                    current_params = self._assignments(start.group(2))
                    current_body = []
                    current_source = line.source
                else:
                    executable.append(line)
                continue
            if _PEND.match(line.text):
                procedures[current_name] = Procedure(
                    current_name, current_params, current_body, current_source
                )
                current_name = None
                current_params = {}
                current_body = []
            else:
                current_body.append(line)
        if current_name is not None:
            procedures[current_name] = Procedure(
                current_name, current_params, current_body, current_source
            )
        return procedures, executable

    def _load_member(self, name: str) -> Procedure | None:
        key = name.upper()
        if key in self._procedure_cache:
            return self._procedure_cache[key]
        path = self._members.get(key)
        if path is None:
            return None
        lines = self._read_lines(path)
        inline, executable = self._extract_inline_procs(lines)
        self._procedure_cache.update(inline)
        if key in inline:
            return inline[key]
        parameters: dict[str, str] = {}
        if executable and (match := _PROC_START.match(executable[0].text)):
            parameters = self._assignments(match.group(2))
            executable = executable[1:]
        procedure = Procedure(key, parameters, executable, str(path))
        self._procedure_cache[key] = procedure
        return procedure

    def _expand_lines(
        self,
        lines: list[JclLine],
        symbols: dict[str, str],
        stack: tuple[str, ...],
        trace: list[dict[str, Any]],
        issues: list[dict[str, Any]],
        depth: int,
    ) -> list[JclLine]:
        if depth > self.max_depth:
            issues.append({"kind": "DEPTH", "message": "maximum PROC expansion depth exceeded"})
            return []
        output: list[JclLine] = []
        local_symbols = dict(symbols)
        pending_overrides: dict[tuple[str, str], str] = {}
        for line in lines:
            raw = line.text
            if set_match := _SET.match(raw):
                local_symbols.update(self._assignments(set_match.group(1)))
                trace.append(
                    {
                        "kind": "SET",
                        "source": line.source,
                        "line": line.line,
                        "symbols": dict(local_symbols),
                    }
                )
                continue
            if include_match := _INCLUDE.match(raw):
                member = include_match.group(1).upper()
                path = self._members.get(member)
                if path is None:
                    issues.append(
                        {
                            "kind": "INCLUDE",
                            "member": member,
                            "source": line.source,
                            "line": line.line,
                            "message": "member not found",
                        }
                    )
                    continue
                included = self._read_lines(path)
                trace.append(
                    {"kind": "INCLUDE", "member": member, "source": line.source, "line": line.line}
                )
                output.extend(
                    self._expand_lines(
                        included,
                        local_symbols,
                        stack + (f"INCLUDE:{member}",),
                        trace,
                        issues,
                        depth + 1,
                    )
                )
                continue
            if override := _OVERRIDE.match(raw):
                pending_overrides[(override.group(1).upper(), override.group(2).upper())] = (
                    override.group(3).strip()
                )
                trace.append(
                    {
                        "kind": "DD_OVERRIDE",
                        "step": override.group(1).upper(),
                        "dd": override.group(2).upper(),
                        "source": line.source,
                        "line": line.line,
                    }
                )
                continue
            substituted = self._substitute(raw, local_symbols)
            exec_match = _EXEC_PROC.match(substituted)
            if exec_match and not _EXEC_PGM.match(substituted):
                invocation_step = exec_match.group(1).upper() or "PROCSTEP"
                proc_name = exec_match.group(2).upper()
                if proc_name in stack:
                    issues.append(
                        {
                            "kind": "PROC",
                            "member": proc_name,
                            "source": line.source,
                            "line": line.line,
                            "message": "recursive PROC cycle",
                        }
                    )
                    continue
                procedure = self._load_member(proc_name)
                if procedure is None:
                    issues.append(
                        {
                            "kind": "PROC",
                            "member": proc_name,
                            "source": line.source,
                            "line": line.line,
                            "message": "procedure not found",
                        }
                    )
                    output.append(JclLine(line.source, line.line, substituted, stack))
                    continue
                invocation = self._assignments(exec_match.group(3))
                proc_symbols = dict(local_symbols)
                proc_symbols.update(procedure.parameters)
                proc_symbols.update(invocation)
                trace.append(
                    {
                        "kind": "PROC",
                        "member": proc_name,
                        "invocation_step": invocation_step,
                        "source": line.source,
                        "line": line.line,
                        "symbols": proc_symbols,
                    }
                )
                expanded_body = self._expand_lines(
                    procedure.body, proc_symbols, stack + (proc_name,), trace, issues, depth + 1
                )
                for body_line in expanded_body:
                    text = body_line.text
                    # Apply invocation-level DD overrides such as //STEP1.SYSIN DD ...
                    body_step = self._step_name(text)
                    dd_name = self._dd_name(text)
                    override_text = pending_overrides.get(
                        (invocation_step, dd_name or "")
                    ) or pending_overrides.get((body_step or "", dd_name or ""))
                    if override_text and dd_name:
                        text = f"//{body_step or invocation_step}.{dd_name} DD {override_text}"
                    output.append(
                        JclLine(body_line.source, body_line.line, text, body_line.expansion_stack)
                    )
                continue
            output.append(JclLine(line.source, line.line, substituted, stack))
        return output

    @staticmethod
    def _assignments(text: str) -> dict[str, str]:
        return {
            match.group(1).upper(): match.group(2).strip().strip("'\"")
            for match in _ASSIGNMENT.finditer(text)
        }

    @staticmethod
    def _substitute(text: str, symbols: dict[str, str]) -> str:
        def replace(match: re.Match[str]) -> str:
            key = match.group(1).upper()
            return symbols.get(key, match.group(0))

        previous = text
        for _ in range(20):
            current = _SYMBOL.sub(replace, previous)
            if current == previous:
                break
            previous = current
        return previous

    @staticmethod
    def _step_name(text: str) -> str | None:
        match = re.match(r"^//([A-Z0-9@$#]+)\s+", text, re.I)
        return match.group(1).upper() if match else None

    @staticmethod
    def _dd_name(text: str) -> str | None:
        match = re.match(r"^//(?:[A-Z0-9@$#]+\.)?([A-Z0-9@$#]+)\s+DD\b", text, re.I)
        return match.group(1).upper() if match else None

    @staticmethod
    def _resolved_programs(lines: list[JclLine]) -> list[dict[str, Any]]:
        pattern = re.compile(r"^//([A-Z0-9@$#]+)\s+EXEC\s+PGM\s*=\s*([A-Z0-9@$#]+)", re.I)
        result: list[dict[str, Any]] = []
        for line in lines:
            if match := pattern.match(line.text):
                result.append(
                    {
                        "step": match.group(1).upper(),
                        "program": match.group(2).upper(),
                        "source": line.source,
                        "line": line.line,
                        "expansion_stack": list(line.expansion_stack),
                    }
                )
        return result
