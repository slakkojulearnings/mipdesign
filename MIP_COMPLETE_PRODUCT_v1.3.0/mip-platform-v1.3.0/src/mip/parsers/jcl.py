from __future__ import annotations

import re

from mip.models import (
    AssetCandidate,
    AssetType,
    DiscoveredFile,
    EvidenceCandidate,
    ParseIssue,
    ParseResult,
    RelationshipCandidate,
    RelationshipType,
)
from mip.parsers.base import ArtifactParser
from mip.parsers.common import normalize_name

_JOB = re.compile(r"^//([A-Z0-9@$#]+)\s+JOB\b(.*)$", re.I)
_PROC = re.compile(r"^//([A-Z0-9@$#]+)\s+PROC\b(.*)$", re.I)
_PEND = re.compile(r"^//\s*PEND\b", re.I)
_SET = re.compile(r"^//(?:[A-Z0-9@$#]+\s+)?SET\s+(.+)$", re.I)
_EXEC = re.compile(r"^//([A-Z0-9@$#]+)\s+EXEC\s+(.*)$", re.I)
_DD = re.compile(r"^//([A-Z0-9@$#]+)\s+DD\s+(.*)$", re.I)
_PGM = re.compile(r"\bPGM\s*=\s*([^,\s]+)", re.I)
_PROC_KW = re.compile(r"\bPROC\s*=\s*([^,\s]+)", re.I)
_DSN = re.compile(r"\bDSN(?:AME)?\s*=\s*([^,\s]+)", re.I)
_DISP = re.compile(r"\bDISP\s*=\s*(?:\(([^,)]+)|([^,\s]+))", re.I)
_SYMBOL = re.compile(r"&([A-Z0-9_@$#]+)\b", re.I)
_PARAM = re.compile(r"\b([A-Z0-9_@$#]+)\s*=\s*([^,\s]+)", re.I)


class JclParser(ArtifactParser):
    name = "jcl-parser"

    def parse(self, source: DiscoveredFile) -> ParseResult:
        if source.text is None:
            return ParseResult(
                issues=[
                    ParseIssue(
                        severity="ERROR",
                        message="JCL source has no decodable text",
                        source_path=source.relative_path,
                    )
                ]
            )

        result = ParseResult()
        logical_lines = self._logical_lines(source.text)
        proc_bodies = self._collect_proc_bodies(logical_lines)
        global_symbols: dict[str, str] = {}
        current_job: str | None = None
        current_step: str | None = None
        step_sequence = 0
        in_proc: str | None = None

        for line_number, statement in logical_lines:
            if _PEND.match(statement):
                in_proc = None
                continue
            if match := _SET.match(statement):
                global_symbols.update(self._parse_params(match.group(1)))
                continue
            if match := _JOB.match(statement):
                current_job = normalize_name(match.group(1))
                current_step = None
                step_sequence = 0
                result.assets.append(
                    AssetCandidate(
                        asset_type=AssetType.JOB,
                        technical_name=current_job,
                        source_path=source.relative_path,
                        attributes={"parameters": match.group(2).strip()},
                        confidence=1.0,
                        evidence=[self._evidence(source, line_number, statement, 1.0)],
                    )
                )
                continue
            if match := _PROC.match(statement):
                procedure = normalize_name(match.group(1))
                in_proc = procedure
                params = self._parse_params(match.group(2))
                result.assets.append(
                    AssetCandidate(
                        asset_type=AssetType.PROCEDURE,
                        technical_name=procedure,
                        source_path=source.relative_path,
                        attributes={"parameters": params},
                        confidence=1.0,
                        evidence=[self._evidence(source, line_number, statement, 1.0)],
                    )
                )
                if current_job is None:
                    current_job = procedure
                continue
            if in_proc:
                # PROC body is represented by procedure asset; actual expansion happens on EXEC PROC call.
                continue
            if match := _EXEC.match(statement):
                step_name = normalize_name(match.group(1))
                expression = match.group(2).strip()
                step_sequence += 1
                parent = current_job or f"UNNAMED:{source.relative_path}"
                current_step = f"{parent}.{step_name}"
                evidence = self._evidence(source, line_number, statement, 0.98)
                result.assets.append(
                    AssetCandidate(
                        asset_type=AssetType.JOB_STEP,
                        technical_name=current_step,
                        source_path=source.relative_path,
                        attributes={
                            "step_name": step_name,
                            "sequence": step_sequence,
                            "exec_expression": expression,
                        },
                        confidence=0.98,
                        evidence=[evidence],
                    )
                )
                result.relationships.append(
                    RelationshipCandidate(
                        relationship_type=RelationshipType.CONTAINS_STEP,
                        source_type=AssetType.JOB,
                        source_name=parent,
                        target_type=AssetType.JOB_STEP,
                        target_name=current_step,
                        confidence=0.98,
                        evidence=[evidence],
                    )
                )
                self._resolve_exec(
                    source, result, current_step, expression, evidence, proc_bodies, global_symbols
                )
                continue
            if match := _DD.match(statement):
                dd_name = normalize_name(match.group(1))
                expression = self._substitute(match.group(2).strip(), global_symbols)
                dsn_match = _DSN.search(expression)
                if not dsn_match or current_step is None:
                    continue
                dataset = normalize_name(dsn_match.group(1))
                disp_match = _DISP.search(expression)
                disposition = normalize_name(
                    (disp_match.group(1) or disp_match.group(2)) if disp_match else "UNKNOWN"
                )
                relationship = self._dataset_relationship(disposition)
                evidence = self._evidence(source, line_number, statement, 0.92)
                result.assets.append(
                    AssetCandidate(
                        asset_type=AssetType.DATASET,
                        technical_name=dataset,
                        attributes={"temporary": dataset.startswith("&&")},
                        confidence=0.92,
                        evidence=[evidence],
                    )
                )
                result.relationships.append(
                    RelationshipCandidate(
                        relationship_type=relationship,
                        source_type=AssetType.JOB_STEP,
                        source_name=current_step,
                        target_type=AssetType.DATASET,
                        target_name=dataset,
                        attributes={
                            "dd_name": dd_name,
                            "disp": disposition,
                            "resolved_expression": expression,
                        },
                        confidence=0.92,
                        evidence=[evidence],
                    )
                )

        if current_job is None and not any(
            asset.asset_type == AssetType.PROCEDURE for asset in result.assets
        ):
            result.issues.append(
                ParseIssue(
                    severity="WARNING",
                    message="No JOB or PROC statement found",
                    source_path=source.relative_path,
                )
            )
        return result

    def _resolve_exec(
        self,
        source: DiscoveredFile,
        result: ParseResult,
        current_step: str,
        expression: str,
        evidence: EvidenceCandidate,
        proc_bodies: dict[str, list[tuple[int, str]]],
        global_symbols: dict[str, str],
    ) -> None:
        step_symbols = {**global_symbols, **self._parse_params(expression)}
        resolved_expression = self._substitute(expression, step_symbols)
        if pgm := _PGM.search(resolved_expression):
            program = normalize_name(pgm.group(1))
            result.relationships.append(
                RelationshipCandidate(
                    relationship_type=RelationshipType.EXECUTES,
                    source_type=AssetType.JOB_STEP,
                    source_name=current_step,
                    target_type=AssetType.PROGRAM,
                    target_name=program,
                    confidence=0.98,
                    evidence=[evidence],
                    attributes={"resolved_expression": resolved_expression},
                )
            )
            return
        proc_match = _PROC_KW.search(resolved_expression)
        procedure = (
            normalize_name(proc_match.group(1))
            if proc_match
            else normalize_name(resolved_expression.split(",", 1)[0].strip())
        )
        if procedure:
            result.relationships.append(
                RelationshipCandidate(
                    relationship_type=RelationshipType.USES_PROCEDURE,
                    source_type=AssetType.JOB_STEP,
                    source_name=current_step,
                    target_type=AssetType.PROCEDURE,
                    target_name=procedure,
                    confidence=0.85,
                    evidence=[evidence],
                    attributes={"symbols": step_symbols},
                )
            )
        if procedure in proc_bodies:
            for proc_line, proc_statement in proc_bodies[procedure]:
                expanded = self._substitute(proc_statement, step_symbols)
                proc_evidence = EvidenceCandidate(
                    source_path=source.relative_path,
                    line_start=proc_line,
                    line_end=proc_line,
                    evidence_text=proc_statement[:1000],
                    extractor=self.name,
                    confidence=0.82,
                )
                if pgm := _PGM.search(expanded):
                    program = normalize_name(pgm.group(1))
                    result.relationships.append(
                        RelationshipCandidate(
                            relationship_type=RelationshipType.EXECUTES,
                            source_type=AssetType.JOB_STEP,
                            source_name=current_step,
                            target_type=AssetType.PROGRAM,
                            target_name=program,
                            confidence=0.82,
                            evidence=[proc_evidence],
                            attributes={
                                "expanded_from_proc": procedure,
                                "expanded_statement": expanded,
                            },
                        )
                    )
                    result.relationships.append(
                        RelationshipCandidate(
                            relationship_type=RelationshipType.EXPANDS_TO,
                            source_type=AssetType.PROCEDURE,
                            source_name=procedure,
                            target_type=AssetType.PROGRAM,
                            target_name=program,
                            confidence=0.82,
                            evidence=[proc_evidence],
                            attributes={"caller_step": current_step, "symbols": step_symbols},
                        )
                    )
                for symbol, value in step_symbols.items():
                    if f"&{symbol}" in proc_statement.upper():
                        result.relationships.append(
                            RelationshipCandidate(
                                relationship_type=RelationshipType.RESOLVES_SYMBOL,
                                source_type=AssetType.JOB_STEP,
                                source_name=current_step,
                                target_type=AssetType.PROCEDURE,
                                target_name=procedure,
                                confidence=0.75,
                                evidence=[proc_evidence],
                                attributes={"symbol": symbol, "value": value},
                            )
                        )

    @staticmethod
    def _collect_proc_bodies(
        logical_lines: list[tuple[int, str]],
    ) -> dict[str, list[tuple[int, str]]]:
        bodies: dict[str, list[tuple[int, str]]] = {}
        current: str | None = None
        for line_number, statement in logical_lines:
            if match := _PROC.match(statement):
                current = normalize_name(match.group(1))
                bodies[current] = []
                continue
            if _PEND.match(statement):
                current = None
                continue
            if current and _EXEC.match(statement):
                bodies[current].append((line_number, statement))
        return bodies

    @staticmethod
    def _parse_params(text: str) -> dict[str, str]:
        return {
            normalize_name(match.group(1)): normalize_name(match.group(2).strip("'\""))
            for match in _PARAM.finditer(text)
        }

    @staticmethod
    def _substitute(text: str, symbols: dict[str, str]) -> str:
        def repl(match: re.Match[str]) -> str:
            key = normalize_name(match.group(1))
            return symbols.get(key, match.group(0))

        return _SYMBOL.sub(repl, text)

    @staticmethod
    def _logical_lines(text: str) -> list[tuple[int, str]]:
        result: list[tuple[int, str]] = []
        current_number: int | None = None
        current = ""
        for number, raw in enumerate(text.splitlines(), 1):
            if raw.startswith("//*") or not raw.strip():
                continue
            if raw.startswith("//") and len(raw) > 2 and not raw[2].isspace():
                if current and current_number is not None:
                    result.append((current_number, current))
                current_number = number
                current = raw.rstrip()
            elif raw.startswith("//") and current:
                current += " " + raw[2:].strip()
            elif current:
                current += " " + raw.strip()
        if current and current_number is not None:
            result.append((current_number, current))
        return result

    @staticmethod
    def _dataset_relationship(disposition: str) -> RelationshipType:
        primary = disposition.split(",", 1)[0].strip("()")
        if primary in {"NEW", "MOD"}:
            return RelationshipType.WRITES_DATASET
        if primary == "SHR":
            return RelationshipType.READS_DATASET
        return RelationshipType.USES_DATASET

    def _evidence(
        self, source: DiscoveredFile, line: int, text: str, confidence: float
    ) -> EvidenceCandidate:
        return EvidenceCandidate(
            source_path=source.relative_path,
            line_start=line,
            line_end=line,
            evidence_text=text[:1000],
            extractor=self.name,
            confidence=confidence,
        )
