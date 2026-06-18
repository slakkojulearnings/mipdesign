from __future__ import annotations

import re

from mip.models import (
    AssetCandidate,
    AssetType,
    DiscoveredFile,
    EvidenceCandidate,
    ParseResult,
)
from mip.parsers.base import ArtifactParser
from mip.parsers.common import normalize_name

_CREATE = re.compile(r"\bCREATE\s+(TABLE|VIEW|INDEX)\s+([A-Z0-9_.$#@-]+)", re.I)


class SqlParser(ArtifactParser):
    name = "sql-parser"

    def parse(self, source: DiscoveredFile) -> ParseResult:
        result = ParseResult()
        if source.text is None:
            return result
        for match in _CREATE.finditer(source.text):
            object_type, name = match.groups()
            line = source.text.count("\n", 0, match.start()) + 1
            result.assets.append(
                AssetCandidate(
                    asset_type=(
                        AssetType.TABLE if object_type.upper() == "TABLE" else AssetType.SQL_OBJECT
                    ),
                    technical_name=normalize_name(name),
                    source_path=source.relative_path,
                    attributes={"object_type": object_type.upper()},
                    confidence=0.98,
                    evidence=[
                        EvidenceCandidate(
                            source_path=source.relative_path,
                            line_start=line,
                            line_end=line,
                            evidence_text=match.group(0),
                            extractor=self.name,
                            confidence=0.98,
                        )
                    ],
                )
            )
        return result
