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

_MAPSET = re.compile(r"(?m)^\s*([A-Z0-9@$#-]+)\s+DFHMSD\b", re.I)
_MAP = re.compile(r"(?m)^\s*([A-Z0-9@$#-]+)\s+DFHMDI\b", re.I)


class BmsParser(ArtifactParser):
    name = "bms-parser"

    def parse(self, source: DiscoveredFile) -> ParseResult:
        result = ParseResult()
        if source.text is None:
            return result
        for pattern, asset_type in ((_MAPSET, AssetType.MAPSET), (_MAP, AssetType.MAP)):
            for match in pattern.finditer(source.text):
                line = source.text.count("\n", 0, match.start()) + 1
                result.assets.append(
                    AssetCandidate(
                        asset_type=asset_type,
                        technical_name=normalize_name(match.group(1)),
                        source_path=source.relative_path,
                        confidence=0.95,
                        evidence=[
                            EvidenceCandidate(
                                source_path=source.relative_path,
                                line_start=line,
                                line_end=line,
                                evidence_text=match.group(0),
                                extractor=self.name,
                                confidence=0.95,
                            )
                        ],
                    )
                )
        return result
