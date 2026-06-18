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

_PROC = re.compile(r"\b([A-Z0-9@$#-]+)\s*:\s*PROC\b|\b([A-Z0-9@$#-]+)\s+PROC\b", re.I)
_CALL = re.compile(r"\bCALL\s+([A-Z0-9@$#-]+)", re.I)
_INCLUDE = re.compile(r"%\s*INCLUDE\s+([A-Z0-9@$#-]+)", re.I)
_SQL_BLOCK = re.compile(r"EXEC\s+SQL(.*?)END-EXEC", re.I | re.S)
_SQL_READ = re.compile(r"\b(?:FROM|JOIN)\s+([A-Z0-9_.$#@-]+)", re.I)
_SQL_WRITE = re.compile(r"\b(?:INSERT\s+INTO|UPDATE|DELETE\s+FROM)\s+([A-Z0-9_.$#@-]+)", re.I)


class Pl1Parser(ArtifactParser):
    name = "pl1-parser"

    def parse(self, source: DiscoveredFile) -> ParseResult:
        if source.text is None:
            return ParseResult(
                issues=[
                    ParseIssue(
                        severity="ERROR",
                        message="PL/I source has no decodable text",
                        source_path=source.relative_path,
                    )
                ]
            )
        result = ParseResult()
        program = source.absolute_path.stem.upper()
        lines = source.text.splitlines()
        for line_number, raw in enumerate(lines, 1):
            line = raw.strip()
            evidence = self._evidence(source, line_number, line, 0.84)
            if match := _PROC.search(line):
                program = normalize_name(match.group(1) or match.group(2))
                result.assets.append(
                    AssetCandidate(
                        asset_type=AssetType.PL1_PROCEDURE,
                        technical_name=program,
                        source_path=source.relative_path,
                        confidence=0.9,
                        evidence=[evidence],
                        attributes={"language": "PL/I"},
                    )
                )
                result.assets.append(
                    AssetCandidate(
                        asset_type=AssetType.PROGRAM,
                        technical_name=program,
                        source_path=source.relative_path,
                        confidence=0.9,
                        evidence=[evidence],
                        attributes={"language": "PL/I"},
                    )
                )
            if match := _CALL.search(line):
                result.relationships.append(
                    RelationshipCandidate(
                        relationship_type=RelationshipType.CALLS,
                        source_type=AssetType.PROGRAM,
                        source_name=program,
                        target_type=AssetType.PROGRAM,
                        target_name=normalize_name(match.group(1)),
                        confidence=0.9,
                        evidence=[evidence],
                    )
                )
            if match := _INCLUDE.search(line):
                result.relationships.append(
                    RelationshipCandidate(
                        relationship_type=RelationshipType.USES_COPYBOOK,
                        source_type=AssetType.PROGRAM,
                        source_name=program,
                        target_type=AssetType.COPYBOOK,
                        target_name=normalize_name(match.group(1)),
                        confidence=0.8,
                        evidence=[evidence],
                        attributes={"include_type": "PL/I %INCLUDE"},
                    )
                )
        text = source.text
        for match in _SQL_BLOCK.finditer(text):
            block = match.group(1)
            sql_line = text[: match.start()].count("\n") + 1
            evidence = self._evidence(source, sql_line, "EXEC SQL" + block[:300], 0.85)
            for table in _SQL_READ.findall(block):
                result.assets.append(
                    AssetCandidate(
                        asset_type=AssetType.TABLE,
                        technical_name=normalize_name(table),
                        source_path=source.relative_path,
                        confidence=0.85,
                        evidence=[evidence],
                    )
                )
                result.relationships.append(
                    RelationshipCandidate(
                        relationship_type=RelationshipType.READS_TABLE,
                        source_type=AssetType.PROGRAM,
                        source_name=program,
                        target_type=AssetType.TABLE,
                        target_name=normalize_name(table),
                        confidence=0.85,
                        evidence=[evidence],
                    )
                )
            for table in _SQL_WRITE.findall(block):
                result.assets.append(
                    AssetCandidate(
                        asset_type=AssetType.TABLE,
                        technical_name=normalize_name(table),
                        source_path=source.relative_path,
                        confidence=0.85,
                        evidence=[evidence],
                    )
                )
                result.relationships.append(
                    RelationshipCandidate(
                        relationship_type=RelationshipType.WRITES_TABLE,
                        source_type=AssetType.PROGRAM,
                        source_name=program,
                        target_type=AssetType.TABLE,
                        target_name=normalize_name(table),
                        confidence=0.85,
                        evidence=[evidence],
                    )
                )
        return result

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
