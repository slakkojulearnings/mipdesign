from __future__ import annotations

import csv
import json
import re
from io import StringIO

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

_PIPE = re.compile(
    r"^\s*([A-Z0-9@$#-]+)\s*\|\s*(RUNS_BEFORE|TRIGGERS|FOLLOWS)\s*\|\s*([A-Z0-9@$#-]+)", re.I
)
_KV = re.compile(
    r"\bJOB\s*=\s*([A-Z0-9@$#-]+).*?\b(?:FOLLOWS|AFTER|PREDECESSOR)\s*=\s*([A-Z0-9@$#-]+)", re.I
)


class SchedulerParser(ArtifactParser):
    name = "scheduler-parser"

    def parse(self, source: DiscoveredFile) -> ParseResult:
        if source.text is None:
            return ParseResult(
                issues=[
                    ParseIssue(
                        severity="ERROR",
                        message="Scheduler source has no decodable text",
                        source_path=source.relative_path,
                    )
                ]
            )
        result = ParseResult()
        self._parse_json(source, result)
        self._parse_text(source, result)
        if not result.assets and not result.relationships:
            result.issues.append(
                ParseIssue(
                    severity="WARNING",
                    message="No scheduler relationships found",
                    source_path=source.relative_path,
                )
            )
        return result

    def _parse_json(self, source: DiscoveredFile, result: ParseResult) -> None:
        try:
            data = json.loads(source.text or "")
        except json.JSONDecodeError:
            return
        jobs = data.get("jobs", []) if isinstance(data, dict) else []
        for idx, item in enumerate(jobs, 1):
            if not isinstance(item, dict) or "name" not in item:
                continue
            job = normalize_name(str(item["name"]))
            evidence = self._evidence(source, idx, json.dumps(item, sort_keys=True), 0.78)
            result.assets.append(
                AssetCandidate(
                    asset_type=AssetType.JOB,
                    technical_name=job,
                    source_path=source.relative_path,
                    confidence=0.78,
                    evidence=[evidence],
                    attributes={"scheduler": data.get("scheduler", "generic-json")},
                )
            )
            for predecessor in item.get("predecessors", []):
                pred = normalize_name(str(predecessor))
                result.relationships.append(
                    RelationshipCandidate(
                        relationship_type=RelationshipType.TRIGGERS,
                        source_type=AssetType.JOB,
                        source_name=pred,
                        target_type=AssetType.JOB,
                        target_name=job,
                        confidence=0.78,
                        evidence=[evidence],
                        attributes={"source": "scheduler-json"},
                    )
                )

    def _parse_text(self, source: DiscoveredFile, result: ParseResult) -> None:
        for line_number, raw in enumerate((source.text or "").splitlines(), 1):
            line = raw.strip()
            if not line or line.startswith("#"):
                continue
            evidence = self._evidence(source, line_number, line, 0.75)
            if match := _PIPE.search(line):
                left, rel, right = (
                    normalize_name(match.group(1)),
                    match.group(2).upper(),
                    normalize_name(match.group(3)),
                )
                source_name, target_name = (right, left) if rel == "FOLLOWS" else (left, right)
                result.assets.extend(
                    [
                        AssetCandidate(
                            asset_type=AssetType.JOB,
                            technical_name=source_name,
                            source_path=source.relative_path,
                            confidence=0.75,
                            evidence=[evidence],
                        ),
                        AssetCandidate(
                            asset_type=AssetType.JOB,
                            technical_name=target_name,
                            source_path=source.relative_path,
                            confidence=0.75,
                            evidence=[evidence],
                        ),
                    ]
                )
                result.relationships.append(
                    RelationshipCandidate(
                        relationship_type=RelationshipType.TRIGGERS,
                        source_type=AssetType.JOB,
                        source_name=source_name,
                        target_type=AssetType.JOB,
                        target_name=target_name,
                        confidence=0.75,
                        evidence=[evidence],
                        attributes={"source": "scheduler-pipe"},
                    )
                )
            elif match := _KV.search(line):
                job, pred = normalize_name(match.group(1)), normalize_name(match.group(2))
                result.relationships.append(
                    RelationshipCandidate(
                        relationship_type=RelationshipType.TRIGGERS,
                        source_type=AssetType.JOB,
                        source_name=pred,
                        target_type=AssetType.JOB,
                        target_name=job,
                        confidence=0.7,
                        evidence=[evidence],
                        attributes={"source": "scheduler-kv"},
                    )
                )
            elif "," in line:
                try:
                    for row in csv.DictReader(StringIO(source.text or "")):
                        if "job" in row and "predecessor" in row:
                            job, pred = (
                                normalize_name(row["job"]),
                                normalize_name(row["predecessor"]),
                            )
                            result.relationships.append(
                                RelationshipCandidate(
                                    relationship_type=RelationshipType.TRIGGERS,
                                    source_type=AssetType.JOB,
                                    source_name=pred,
                                    target_type=AssetType.JOB,
                                    target_name=job,
                                    confidence=0.72,
                                    evidence=[evidence],
                                    attributes={"source": "scheduler-csv"},
                                )
                            )
                    return
                except csv.Error:
                    pass

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
