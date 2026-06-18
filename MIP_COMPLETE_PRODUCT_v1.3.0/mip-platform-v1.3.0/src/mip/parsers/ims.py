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

_DBD = re.compile(r"\bDBD\s+NAME\s*=\s*([A-Z0-9@$#-]+)", re.I)
_SEGM = re.compile(r"\bSEGM\s+NAME\s*=\s*([A-Z0-9@$#-]+)(?:.*?PARENT\s*=\s*([A-Z0-9@$#-]+))?", re.I)
_PSB = re.compile(r"\bPSBGEN\s+PSBNAME\s*=\s*([A-Z0-9@$#-]+)", re.I)
_PCB_DBD = re.compile(r"\bPCB\s+TYPE\s*=\s*DB.*?DBDNAME\s*=\s*([A-Z0-9@$#-]+)", re.I)


class ImsParser(ArtifactParser):
    name = "ims-parser"

    def parse(self, source: DiscoveredFile) -> ParseResult:
        if source.text is None:
            return ParseResult(
                issues=[
                    ParseIssue(
                        severity="ERROR",
                        message="IMS source has no decodable text",
                        source_path=source.relative_path,
                    )
                ]
            )
        result = ParseResult()
        current_dbd: str | None = None
        current_psb: str | None = None
        for line_number, raw in enumerate(source.text.splitlines(), 1):
            line = raw.strip()
            if not line or line.startswith("*"):
                continue
            evidence = self._evidence(source, line_number, line, 0.9)
            if match := _DBD.search(line):
                current_dbd = normalize_name(match.group(1))
                result.assets.append(
                    AssetCandidate(
                        asset_type=AssetType.IMS_DATABASE,
                        technical_name=current_dbd,
                        source_path=source.relative_path,
                        confidence=0.95,
                        evidence=[evidence],
                        attributes={"kind": "DBD"},
                    )
                )
            if match := _PSB.search(line):
                current_psb = normalize_name(match.group(1))
                result.assets.append(
                    AssetCandidate(
                        asset_type=AssetType.PROGRAM,
                        technical_name=current_psb,
                        source_path=source.relative_path,
                        confidence=0.75,
                        evidence=[evidence],
                        attributes={"language": "IMS-PSB", "kind": "PSB"},
                    )
                )
            if match := _PCB_DBD.search(line):
                dbd = normalize_name(match.group(1))
                if current_psb:
                    result.relationships.append(
                        RelationshipCandidate(
                            relationship_type=RelationshipType.REFERENCES,
                            source_type=AssetType.PROGRAM,
                            source_name=current_psb,
                            target_type=AssetType.IMS_DATABASE,
                            target_name=dbd,
                            confidence=0.86,
                            evidence=[evidence],
                            attributes={"ims_reference": "PCB DBDNAME"},
                        )
                    )
            if match := _SEGM.search(line):
                segment = normalize_name(match.group(1))
                parent = normalize_name(match.group(2)) if match.group(2) else None
                result.assets.append(
                    AssetCandidate(
                        asset_type=AssetType.IMS_SEGMENT,
                        technical_name=segment,
                        source_path=source.relative_path,
                        confidence=0.9,
                        evidence=[evidence],
                        attributes={"parent": parent},
                    )
                )
                if current_dbd:
                    result.relationships.append(
                        RelationshipCandidate(
                            relationship_type=RelationshipType.CONTAINS_SEGMENT,
                            source_type=AssetType.IMS_DATABASE,
                            source_name=current_dbd,
                            target_type=AssetType.IMS_SEGMENT,
                            target_name=segment,
                            confidence=0.9,
                            evidence=[evidence],
                        )
                    )
                if parent:
                    result.relationships.append(
                        RelationshipCandidate(
                            relationship_type=RelationshipType.PARENT_SEGMENT,
                            source_type=AssetType.IMS_SEGMENT,
                            source_name=segment,
                            target_type=AssetType.IMS_SEGMENT,
                            target_name=parent,
                            confidence=0.85,
                            evidence=[evidence],
                        )
                    )
        if not result.assets:
            result.issues.append(
                ParseIssue(
                    severity="WARNING",
                    message="No IMS DBD/PSB assets found",
                    source_path=source.relative_path,
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
