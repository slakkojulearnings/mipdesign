from __future__ import annotations

import re
from collections.abc import Iterable

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
from mip.parsers.common import cobol_code_lines, compact_statements, normalize_name

_PROGRAM_ID = re.compile(r"\bPROGRAM-ID\s*\.\s*([A-Z0-9@$#-]+)", re.I)
_COPY = re.compile(r"\bCOPY\s+([A-Z0-9@$#-]+)(.*?)(?:\.|$)", re.I)
_REPLACING_PAIR = re.compile(
    r"==([^=]+)==\s+BY\s+==([^=]+)==|(?:\b([A-Z0-9@$#:-]+)\b)\s+BY\s+(?:\b([A-Z0-9@$#:-]+)\b)", re.I
)
_STATIC_CALL = re.compile(r"\bCALL\s+['\"]([^'\"]+)['\"]", re.I)
_DYNAMIC_CALL = re.compile(r"\bCALL\s+([A-Z][A-Z0-9@$#-]*)", re.I)
_PARAGRAPH = re.compile(r"^([A-Z0-9][A-Z0-9-]+)\s*\.\s*$", re.I)
_SELECT_FILE = re.compile(r"\bSELECT\s+([A-Z0-9-]+)\s+ASSIGN\s+TO\s+([^\s.]+)", re.I)
_FD = re.compile(r"\bFD\s+([A-Z0-9-]+)", re.I)
_FILE_OP = re.compile(r"\b(READ|WRITE|REWRITE|DELETE)\s+([A-Z0-9-]+)", re.I)
_OPEN = re.compile(r"\bOPEN\s+(INPUT|OUTPUT|I-O|EXTEND)\s+([A-Z0-9-]+)", re.I)
_SQL_BLOCK = re.compile(r"EXEC\s+SQL(.*?)END-EXEC", re.I | re.S)
_SQL_READ = re.compile(r"\b(?:FROM|JOIN)\s+([A-Z0-9_.$#@-]+)", re.I)
_SQL_INSERT = re.compile(r"\bINSERT\s+INTO\s+([A-Z0-9_.$#@-]+)", re.I)
_SQL_UPDATE = re.compile(r"\bUPDATE\s+([A-Z0-9_.$#@-]+)", re.I)
_SQL_DELETE = re.compile(r"\bDELETE\s+FROM\s+([A-Z0-9_.$#@-]+)", re.I)
_CICS_LINK = re.compile(
    r"EXEC\s+CICS\s+(?:LINK|XCTL)\b.*?PROGRAM\s*\(\s*['\"]?([A-Z0-9@$#-]+)",
    re.I | re.S,
)
_CICS_TRANS = re.compile(
    r"EXEC\s+CICS\s+START\b.*?TRANSID\s*\(\s*['\"]?([A-Z0-9@$#-]+)",
    re.I | re.S,
)
_CICS_MAP = re.compile(
    r"EXEC\s+CICS\s+(?:SEND|RECEIVE)\s+MAP\b.*?MAP\s*\(\s*['\"]?([A-Z0-9@$#-]+)",
    re.I | re.S,
)
_MQ_CALL = re.compile(
    r"\bCALL\s+['\"](MQ(?:PUT|GET|OPEN|CLOSE|CONN|DISC))['\"](?:\s+USING\s+(.+?))?$", re.I
)
_MQ_QUEUE_LITERAL = re.compile(r"['\"]([A-Z0-9._@$#-]*QUEUE[A-Z0-9._@$#-]*)['\"]", re.I)
_IF_RULE = re.compile(r"\bIF\s+(.+?)(?:\bTHEN\b|$)", re.I)
_EVALUATE_RULE = re.compile(r"\bEVALUATE\s+(.+)$", re.I)
_PARAGRAPH_EXCLUSIONS = {
    "IDENTIFICATION",
    "ENVIRONMENT",
    "DATA",
    "PROCEDURE",
    "FILE-CONTROL",
    "END-EXEC",
    "END-IF",
    "END-EVALUATE",
    "GOBACK",
    "STOP",
    "EXIT",
}


class CobolParser(ArtifactParser):
    name = "cobol-parser"

    def parse(self, source: DiscoveredFile) -> ParseResult:
        if source.text is None:
            return ParseResult(
                issues=[
                    ParseIssue(
                        severity="ERROR",
                        message="COBOL source has no decodable text",
                        source_path=source.relative_path,
                    )
                ]
            )

        result = ParseResult()
        lines = cobol_code_lines(source.text)
        normalized_text = "\n".join(code for _, code in lines)
        program_match = _PROGRAM_ID.search(normalized_text)
        if not program_match:
            result.issues.append(
                ParseIssue(
                    severity="ERROR",
                    message="PROGRAM-ID not found",
                    source_path=source.relative_path,
                )
            )
            return result

        program_name = normalize_name(program_match.group(1))
        program_line = self._find_line(lines, "PROGRAM-ID")
        program_evidence = self._evidence(
            source,
            program_line,
            program_line,
            self._line_text(source, program_line),
            1.0,
        )

        paragraphs = [
            match.group(1).upper()
            for _, code in lines
            if (match := _PARAGRAPH.match(code))
            and match.group(1).upper() not in {"IDENTIFICATION", "ENVIRONMENT", "DATA", "PROCEDURE"}
        ]
        divisions = [
            division
            for division in ("IDENTIFICATION", "ENVIRONMENT", "DATA", "PROCEDURE")
            if re.search(rf"\b{division}\s+DIVISION\b", normalized_text, re.I)
        ]
        executable_lines = len(lines)
        program = AssetCandidate(
            asset_type=AssetType.PROGRAM,
            technical_name=program_name,
            source_path=source.relative_path,
            attributes={
                "language": "COBOL",
                "artifact_type": source.artifact_type.value,
                "lines_of_code": executable_lines,
                "divisions": divisions,
                "paragraphs": paragraphs,
                "encoding": source.encoding,
            },
            confidence=1.0,
            evidence=[program_evidence],
        )
        result.assets.append(program)

        statements = compact_statements(lines)
        self._extract_copybooks(source, program_name, statements, result)
        self._extract_calls(source, program_name, statements, result)
        self._extract_files(source, program_name, statements, result)
        self._extract_sql(source, program_name, normalized_text, lines, result)
        self._extract_cics(source, program_name, normalized_text, lines, result)
        self._extract_mq(source, program_name, statements, result)
        self._extract_rules(source, program_name, lines, result)
        return result

    def _extract_copybooks(
        self,
        source: DiscoveredFile,
        program_name: str,
        statements: Iterable[tuple[int, int, str]],
        result: ParseResult,
    ) -> None:
        seen: set[str] = set()
        for start, end, statement in statements:
            for match in _COPY.finditer(statement):
                target = normalize_name(match.group(1))
                tail = match.group(2) or ""
                replacements: list[dict[str, str]] = []
                if "REPLACING" in tail.upper():
                    for repl in _REPLACING_PAIR.finditer(tail):
                        old_value = (repl.group(1) or repl.group(3) or "").strip()
                        new_value = (repl.group(2) or repl.group(4) or "").strip()
                        if old_value and new_value:
                            replacements.append({"from": old_value, "to": new_value})
                key = f"{target}:{replacements}"
                if key in seen:
                    continue
                seen.add(key)
                evidence = self._evidence(source, start, end, statement, 0.98)
                result.relationships.append(
                    RelationshipCandidate(
                        relationship_type=RelationshipType.USES_COPYBOOK,
                        source_type=AssetType.PROGRAM,
                        source_name=program_name,
                        target_type=AssetType.COPYBOOK,
                        target_name=target,
                        attributes={
                            "copy_replacing": replacements,
                            "requires_expansion": bool(replacements),
                        },
                        confidence=0.98 if not replacements else 0.92,
                        evidence=[evidence],
                    )
                )
                if replacements:
                    result.relationships.append(
                        RelationshipCandidate(
                            relationship_type=RelationshipType.EXPANDS_TO,
                            source_type=AssetType.PROGRAM,
                            source_name=program_name,
                            target_type=AssetType.COPYBOOK,
                            target_name=target,
                            attributes={"copy_replacing": replacements},
                            confidence=0.78,
                            evidence=[evidence],
                        )
                    )

    def _extract_calls(
        self,
        source: DiscoveredFile,
        program_name: str,
        statements: Iterable[tuple[int, int, str]],
        result: ParseResult,
    ) -> None:
        for start, end, statement in statements:
            static_targets = {normalize_name(value) for value in _STATIC_CALL.findall(statement)}
            for target in sorted(static_targets):
                result.relationships.append(
                    RelationshipCandidate(
                        relationship_type=RelationshipType.CALLS,
                        source_type=AssetType.PROGRAM,
                        source_name=program_name,
                        target_type=AssetType.PROGRAM,
                        target_name=target,
                        confidence=1.0,
                        evidence=[self._evidence(source, start, end, statement, 1.0)],
                    )
                )
            if static_targets:
                continue
            dynamic = _DYNAMIC_CALL.search(statement)
            if dynamic:
                variable = normalize_name(dynamic.group(1))
                result.relationships.append(
                    RelationshipCandidate(
                        relationship_type=RelationshipType.DYNAMIC_CALL,
                        source_type=AssetType.PROGRAM,
                        source_name=program_name,
                        target_type=AssetType.UNRESOLVED,
                        target_name=f"DYNAMIC:{variable}",
                        attributes={"program_variable": variable},
                        confidence=0.55,
                        evidence=[self._evidence(source, start, end, statement, 0.55)],
                    )
                )

    def _extract_files(
        self,
        source: DiscoveredFile,
        program_name: str,
        statements: Iterable[tuple[int, int, str]],
        result: ParseResult,
    ) -> None:
        logical_to_physical: dict[str, str] = {}
        record_to_file: dict[str, str] = {}
        current_fd: str | None = None
        statement_list = list(statements)
        for start, end, statement in statement_list:
            if match := _SELECT_FILE.search(statement):
                logical = normalize_name(match.group(1))
                physical = normalize_name(match.group(2))
                logical_to_physical[logical] = physical
                result.assets.append(
                    AssetCandidate(
                        asset_type=AssetType.FILE,
                        technical_name=logical,
                        source_path=source.relative_path,
                        attributes={"assign_to": physical},
                        confidence=0.9,
                        evidence=[self._evidence(source, start, end, statement, 0.9)],
                    )
                )
            elif match := _FD.search(statement):
                logical = normalize_name(match.group(1))
                current_fd = logical
                if logical not in logical_to_physical:
                    result.assets.append(
                        AssetCandidate(
                            asset_type=AssetType.FILE,
                            technical_name=logical,
                            source_path=source.relative_path,
                            confidence=0.9,
                            evidence=[self._evidence(source, start, end, statement, 0.9)],
                        )
                    )
            elif current_fd and (record_match := re.match(r"^01\s+([A-Z0-9-]+)", statement, re.I)):
                record_to_file[normalize_name(record_match.group(1))] = current_fd

        for start, end, statement in statement_list:
            for match in _FILE_OP.finditer(statement):
                operation, logical = match.groups()
                logical = normalize_name(logical)
                logical = record_to_file.get(logical, logical)
                relationship = (
                    RelationshipType.READS_FILE
                    if operation.upper() == "READ"
                    else RelationshipType.WRITES_FILE
                )
                result.relationships.append(
                    RelationshipCandidate(
                        relationship_type=relationship,
                        source_type=AssetType.PROGRAM,
                        source_name=program_name,
                        target_type=AssetType.FILE,
                        target_name=logical,
                        attributes={"operation": operation.upper()},
                        confidence=0.9,
                        evidence=[self._evidence(source, start, end, statement, 0.9)],
                    )
                )
            if match := _OPEN.search(statement):
                mode, logical = match.groups()
                logical = normalize_name(logical)
                relationship = (
                    RelationshipType.READS_FILE
                    if mode.upper() == "INPUT"
                    else RelationshipType.WRITES_FILE
                )
                result.relationships.append(
                    RelationshipCandidate(
                        relationship_type=relationship,
                        source_type=AssetType.PROGRAM,
                        source_name=program_name,
                        target_type=AssetType.FILE,
                        target_name=logical,
                        attributes={"operation": f"OPEN {mode.upper()}"},
                        confidence=0.85,
                        evidence=[self._evidence(source, start, end, statement, 0.85)],
                    )
                )

    def _extract_sql(
        self,
        source: DiscoveredFile,
        program_name: str,
        normalized_text: str,
        lines: list[tuple[int, str]],
        result: ParseResult,
    ) -> None:
        for block in _SQL_BLOCK.finditer(normalized_text):
            sql = " ".join(block.group(1).split())
            line = normalized_text.count("\n", 0, block.start()) + 1
            source_line = lines[min(line - 1, len(lines) - 1)][0] if lines else line
            evidence = self._evidence(source, source_line, source_line, sql, 0.95)
            for table in sorted({normalize_name(t) for t in _SQL_READ.findall(sql)}):
                result.relationships.append(
                    RelationshipCandidate(
                        relationship_type=RelationshipType.READS_TABLE,
                        source_type=AssetType.PROGRAM,
                        source_name=program_name,
                        target_type=AssetType.TABLE,
                        target_name=table,
                        attributes={"sql": sql},
                        confidence=0.95,
                        evidence=[evidence],
                    )
                )
            for pattern, operation in (
                (_SQL_INSERT, "INSERT"),
                (_SQL_UPDATE, "UPDATE"),
                (_SQL_DELETE, "DELETE"),
            ):
                for table in sorted({normalize_name(t) for t in pattern.findall(sql)}):
                    result.relationships.append(
                        RelationshipCandidate(
                            relationship_type=RelationshipType.WRITES_TABLE,
                            source_type=AssetType.PROGRAM,
                            source_name=program_name,
                            target_type=AssetType.TABLE,
                            target_name=table,
                            attributes={"operation": operation, "sql": sql},
                            confidence=0.95,
                            evidence=[evidence],
                        )
                    )

    def _extract_cics(
        self,
        source: DiscoveredFile,
        program_name: str,
        normalized_text: str,
        lines: list[tuple[int, str]],
        result: ParseResult,
    ) -> None:
        for pattern, rel, target_type in (
            (_CICS_LINK, RelationshipType.CALLS, AssetType.PROGRAM),
            (_CICS_TRANS, RelationshipType.STARTS_TRANSACTION, AssetType.TRANSACTION),
            (_CICS_MAP, RelationshipType.USES_MAP, AssetType.MAP),
        ):
            for match in pattern.finditer(normalized_text):
                target = normalize_name(match.group(1))
                normalized_line = normalized_text.count("\n", 0, match.start()) + 1
                source_line = lines[min(normalized_line - 1, len(lines) - 1)][0]
                result.relationships.append(
                    RelationshipCandidate(
                        relationship_type=rel,
                        source_type=AssetType.PROGRAM,
                        source_name=program_name,
                        target_type=target_type,
                        target_name=target,
                        confidence=0.9,
                        evidence=[
                            self._evidence(
                                source,
                                source_line,
                                source_line,
                                match.group(0),
                                0.9,
                            )
                        ],
                    )
                )

    def _extract_mq(
        self,
        source: DiscoveredFile,
        program_name: str,
        statements: Iterable[tuple[int, int, str]],
        result: ParseResult,
    ) -> None:
        for start, end, statement in statements:
            match = _MQ_CALL.search(statement)
            if not match:
                continue
            api = match.group(1).upper()
            using = match.group(2) or ""
            queue_match = _MQ_QUEUE_LITERAL.search(using)
            queue_name = (
                normalize_name(queue_match.group(1))
                if queue_match
                else f"UNRESOLVED-MQ:{program_name}:{start}"
            )
            relationship = (
                RelationshipType.PUTS_MESSAGE
                if api == "MQPUT"
                else RelationshipType.GETS_MESSAGE
                if api == "MQGET"
                else RelationshipType.USES_QUEUE
            )
            evidence = self._evidence(source, start, end, statement, 0.72)
            result.assets.append(
                AssetCandidate(
                    asset_type=AssetType.MQ_QUEUE,
                    technical_name=queue_name,
                    source_path=source.relative_path,
                    confidence=0.72 if queue_match else 0.45,
                    evidence=[evidence],
                    attributes={
                        "resolved_from": "literal" if queue_match else "unresolved_using_operands"
                    },
                )
            )
            result.relationships.append(
                RelationshipCandidate(
                    relationship_type=relationship,
                    source_type=AssetType.PROGRAM,
                    source_name=program_name,
                    target_type=AssetType.MQ_QUEUE,
                    target_name=queue_name,
                    confidence=0.72 if queue_match else 0.45,
                    evidence=[evidence],
                    attributes={"mq_api": api, "using_operands": using},
                )
            )

    def _extract_rules(
        self,
        source: DiscoveredFile,
        program_name: str,
        lines: list[tuple[int, str]],
        result: ParseResult,
    ) -> None:
        for line_number, code in lines:
            match = _IF_RULE.search(code) or _EVALUATE_RULE.search(code)
            if not match:
                continue
            expression = " ".join(match.group(1).split())[:500]
            if not expression:
                continue
            rule_name = f"{program_name}:RULE:{line_number}"
            evidence = self._evidence(source, line_number, line_number, code, 0.65)
            result.assets.append(
                AssetCandidate(
                    asset_type=AssetType.BUSINESS_RULE,
                    technical_name=rule_name,
                    readable_name=expression,
                    source_path=source.relative_path,
                    attributes={"expression": expression, "rule_kind": "CONDITIONAL"},
                    confidence=0.65,
                    evidence=[evidence],
                )
            )
            result.relationships.append(
                RelationshipCandidate(
                    relationship_type=RelationshipType.IMPLEMENTS_RULE,
                    source_type=AssetType.PROGRAM,
                    source_name=program_name,
                    target_type=AssetType.BUSINESS_RULE,
                    target_name=rule_name,
                    confidence=0.65,
                    evidence=[evidence],
                )
            )

    def _evidence(
        self,
        source: DiscoveredFile,
        start: int | None,
        end: int | None,
        text: str,
        confidence: float,
    ) -> EvidenceCandidate:
        return EvidenceCandidate(
            source_path=source.relative_path,
            line_start=start,
            line_end=end,
            evidence_text=text[:1000],
            extractor=self.name,
            confidence=confidence,
        )

    @staticmethod
    def _find_line(lines: list[tuple[int, str]], token: str) -> int:
        for line_number, code in lines:
            if token.upper() in code.upper():
                return line_number
        return 1

    @staticmethod
    def _line_text(source: DiscoveredFile, line_number: int) -> str:
        if not source.text:
            return ""
        lines = source.text.splitlines()
        if 1 <= line_number <= len(lines):
            return lines[line_number - 1].strip()
        return ""
