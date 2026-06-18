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

_DEFINE_QUEUE = re.compile(
    r"\bDEFINE\s+Q(?:LOCAL|REMOTE|ALIAS)\s*\(\s*['\"]?([A-Z0-9._@$#-]+)", re.I
)
_MQOPEN = re.compile(r"\bMQOPEN\b.*?([A-Z0-9._@$#-]*QUEUE[A-Z0-9._@$#-]*)", re.I)
_MQPUT = re.compile(r"\bMQPUT\b.*?([A-Z0-9._@$#-]*QUEUE[A-Z0-9._@$#-]*)?", re.I)
_MQGET = re.compile(r"\bMQGET\b.*?([A-Z0-9._@$#-]*QUEUE[A-Z0-9._@$#-]*)?", re.I)


class MqParser(ArtifactParser):
    name = "mq-parser"

    def parse(self, source: DiscoveredFile) -> ParseResult:
        if source.text is None:
            return ParseResult(
                issues=[
                    ParseIssue(
                        severity="ERROR",
                        message="MQ source has no decodable text",
                        source_path=source.relative_path,
                    )
                ]
            )
        result = ParseResult()
        producer = source.absolute_path.stem.upper()
        result.assets.append(
            AssetCandidate(
                asset_type=AssetType.PROGRAM,
                technical_name=producer,
                source_path=source.relative_path,
                confidence=0.55,
                attributes={"language": "MQ-CONFIG"},
            )
        )
        for line_number, raw in enumerate(source.text.splitlines(), 1):
            line = raw.strip()
            if not line or line.startswith("*"):
                continue
            evidence = self._evidence(source, line_number, line, 0.86)
            if match := _DEFINE_QUEUE.search(line):
                queue = normalize_name(match.group(1))
                result.assets.append(
                    AssetCandidate(
                        asset_type=AssetType.MQ_QUEUE,
                        technical_name=queue,
                        source_path=source.relative_path,
                        confidence=0.95,
                        evidence=[evidence],
                        attributes={"definition": "MQSC"},
                    )
                )
            for regex, rel in (
                (_MQPUT, RelationshipType.PUTS_MESSAGE),
                (_MQGET, RelationshipType.GETS_MESSAGE),
                (_MQOPEN, RelationshipType.USES_QUEUE),
            ):
                if match := regex.search(line):
                    queue = normalize_name(match.group(1) or "UNRESOLVED-MQ-QUEUE")
                    result.assets.append(
                        AssetCandidate(
                            asset_type=AssetType.MQ_QUEUE,
                            technical_name=queue,
                            source_path=source.relative_path,
                            confidence=0.55 if queue.startswith("UNRESOLVED") else 0.78,
                            evidence=[evidence],
                        )
                    )
                    result.relationships.append(
                        RelationshipCandidate(
                            relationship_type=rel,
                            source_type=AssetType.PROGRAM,
                            source_name=producer,
                            target_type=AssetType.MQ_QUEUE,
                            target_name=queue,
                            confidence=0.55 if queue.startswith("UNRESOLVED") else 0.78,
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
