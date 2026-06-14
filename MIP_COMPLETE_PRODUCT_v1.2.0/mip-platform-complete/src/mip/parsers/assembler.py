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

_CSECT = re.compile(r"^\s*([A-Z0-9@$#-]+)\s+CSECT\b", re.I)
_START = re.compile(r"^\s*([A-Z0-9@$#-]+)\s+START\b", re.I)
_CALL = re.compile(r"\b(?:CALL|LINK)\s+([A-Z0-9@$#-]+)", re.I)


class AssemblerParser(ArtifactParser):
    name = "assembler-parser"

    def parse(self, source: DiscoveredFile) -> ParseResult:
        if source.text is None:
            return ParseResult(
                issues=[
                    ParseIssue(
                        severity="ERROR",
                        message="Assembler source has no decodable text",
                        source_path=source.relative_path,
                    )
                ]
            )
        result = ParseResult()
        current = source.absolute_path.stem.upper()
        for line_number, raw in enumerate(source.text.splitlines(), 1):
            line = raw.rstrip()
            if not line.strip() or line.lstrip().startswith("*"):
                continue
            evidence = self._evidence(source, line_number, line, 0.75)
            if match := (_CSECT.search(line) or _START.search(line)):
                current = normalize_name(match.group(1))
                result.assets.append(
                    AssetCandidate(
                        asset_type=AssetType.ASSEMBLER_CSECT,
                        technical_name=current,
                        source_path=source.relative_path,
                        confidence=0.9,
                        evidence=[evidence],
                        attributes={"language": "ASSEMBLER"},
                    )
                )
                result.assets.append(
                    AssetCandidate(
                        asset_type=AssetType.PROGRAM,
                        technical_name=current,
                        source_path=source.relative_path,
                        confidence=0.82,
                        evidence=[evidence],
                        attributes={"language": "ASSEMBLER"},
                    )
                )
            if match := _CALL.search(line):
                target = normalize_name(match.group(1))
                result.relationships.append(
                    RelationshipCandidate(
                        relationship_type=RelationshipType.CALLS,
                        source_type=AssetType.PROGRAM,
                        source_name=current,
                        target_type=AssetType.PROGRAM,
                        target_name=target,
                        confidence=0.65,
                        evidence=[evidence],
                        attributes={"assembler_statement": "CALL_OR_LINK"},
                    )
                )
        if not result.assets:
            result.assets.append(
                AssetCandidate(
                    asset_type=AssetType.PROGRAM,
                    technical_name=current,
                    source_path=source.relative_path,
                    confidence=0.45,
                    attributes={"language": "ASSEMBLER", "status": "name_from_file"},
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
