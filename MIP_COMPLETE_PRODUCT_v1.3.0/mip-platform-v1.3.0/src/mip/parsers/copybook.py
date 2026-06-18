from __future__ import annotations

import math
import re
from typing import TypedDict

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
from mip.parsers.common import cobol_code_lines, normalize_name

_ENTRY = re.compile(r"^(\d{1,2})\s+([A-Z0-9@$#-]+)\s*(.*?)(?:\.)?$", re.I)
_PIC = re.compile(r"\bPIC(?:TURE)?\s+([^\s.]+)", re.I)
_USAGE = re.compile(r"\b(?:USAGE\s+IS\s+)?(COMP-3|COMP-1|COMP-2|COMP|BINARY|DISPLAY)\b", re.I)
_OCCURS = re.compile(r"\bOCCURS\s+(\d+)(?:\s+TO\s+(\d+))?\s+TIMES", re.I)
_REDEFINES = re.compile(r"\bREDEFINES\s+([A-Z0-9@$#-]+)", re.I)
_COPY = re.compile(r"\bCOPY\s+([A-Z0-9@$#-]+)", re.I)


class CopybookEntry(TypedDict):
    line: int
    level: int
    name: str
    rest: str
    pic: str | None
    usage: str
    occurs: int
    length: int
    redefines: str | None


class CopybookParser(ArtifactParser):
    name = "copybook-parser"

    def parse(self, source: DiscoveredFile) -> ParseResult:
        if source.text is None:
            return ParseResult(
                issues=[
                    ParseIssue(
                        severity="ERROR",
                        message="Copybook has no decodable text",
                        source_path=source.relative_path,
                    )
                ]
            )

        result = ParseResult()
        lines = cobol_code_lines(source.text)
        entries: list[CopybookEntry] = []
        for line_number, code in lines:
            match = _ENTRY.match(code)
            if not match:
                continue
            level = int(match.group(1))
            name = normalize_name(match.group(2))
            rest = match.group(3)
            pic_match = _PIC.search(rest)
            usage_match = _USAGE.search(rest)
            occurs_match = _OCCURS.search(rest)
            redefines_match = _REDEFINES.search(rest)
            pic = pic_match.group(1).upper() if pic_match else None
            usage = usage_match.group(1).upper() if usage_match else "DISPLAY"
            occurs = int(occurs_match.group(1)) if occurs_match else 1
            length = self._field_length(pic, usage) * occurs if pic else 0
            entries.append(
                {
                    "line": line_number,
                    "level": level,
                    "name": name,
                    "rest": rest,
                    "pic": pic,
                    "usage": usage,
                    "occurs": occurs,
                    "length": length,
                    "redefines": (
                        normalize_name(redefines_match.group(1)) if redefines_match else None
                    ),
                }
            )

        copybook_name = source.absolute_path.stem.upper()
        record_names = [entry["name"] for entry in entries if entry["level"] == 1]
        root_evidence = EvidenceCandidate(
            source_path=source.relative_path,
            line_start=entries[0]["line"] if entries else 1,
            line_end=entries[0]["line"] if entries else 1,
            evidence_text=self._source_line(source, int(entries[0]["line"])) if entries else "",
            extractor=self.name,
            confidence=0.95,
        )
        result.assets.append(
            AssetCandidate(
                asset_type=AssetType.COPYBOOK,
                technical_name=copybook_name,
                source_path=source.relative_path,
                attributes={
                    "field_count": sum(1 for entry in entries if entry["pic"]),
                    "estimated_record_length": self._estimated_record_length(entries),
                    "record_names": record_names,
                    "encoding": source.encoding,
                },
                confidence=0.95,
                evidence=[root_evidence],
            )
        )

        offsets: dict[str, int] = {}
        next_offset = 0
        for entry in entries:
            name = str(entry["name"])
            redefines = entry["redefines"]
            offset = offsets.get(str(redefines), next_offset) if redefines else next_offset
            if not redefines:
                offsets[name] = offset
                next_offset += int(entry["length"])
            field_name = f"{copybook_name}.{name}"
            line_number = int(entry["line"])
            evidence = EvidenceCandidate(
                source_path=source.relative_path,
                line_start=line_number,
                line_end=line_number,
                evidence_text=self._source_line(source, line_number),
                extractor=self.name,
                confidence=0.9,
            )
            result.assets.append(
                AssetCandidate(
                    asset_type=AssetType.DATA_FIELD,
                    technical_name=field_name,
                    source_path=source.relative_path,
                    attributes={
                        "field_name": name,
                        "level": entry["level"],
                        "pic": entry["pic"],
                        "usage": entry["usage"],
                        "occurs": entry["occurs"],
                        "length": entry["length"],
                        "offset": offset,
                        "redefines": redefines,
                        "condition_name": entry["level"] == 88,
                    },
                    confidence=0.9,
                    evidence=[evidence],
                )
            )
            result.relationships.append(
                RelationshipCandidate(
                    relationship_type=RelationshipType.CONTAINS_FIELD,
                    source_type=AssetType.COPYBOOK,
                    source_name=copybook_name,
                    target_type=AssetType.DATA_FIELD,
                    target_name=field_name,
                    confidence=0.9,
                    evidence=[evidence],
                )
            )
            if redefines:
                result.relationships.append(
                    RelationshipCandidate(
                        relationship_type=RelationshipType.REDEFINES,
                        source_type=AssetType.DATA_FIELD,
                        source_name=field_name,
                        target_type=AssetType.DATA_FIELD,
                        target_name=f"{copybook_name}.{redefines}",
                        confidence=0.9,
                        evidence=[evidence],
                    )
                )

        for line_number, code in lines:
            for match in _COPY.finditer(code):
                target = normalize_name(match.group(1))
                evidence = EvidenceCandidate(
                    source_path=source.relative_path,
                    line_start=line_number,
                    line_end=line_number,
                    evidence_text=code,
                    extractor=self.name,
                    confidence=0.95,
                )
                result.relationships.append(
                    RelationshipCandidate(
                        relationship_type=RelationshipType.USES_COPYBOOK,
                        source_type=AssetType.COPYBOOK,
                        source_name=copybook_name,
                        target_type=AssetType.COPYBOOK,
                        target_name=target,
                        confidence=0.95,
                        evidence=[evidence],
                    )
                )
        return result

    @staticmethod
    def _estimated_record_length(entries: list[CopybookEntry]) -> int:
        return sum(
            int(entry["length"])
            for entry in entries
            if entry["pic"] and not entry["redefines"] and entry["level"] != 88
        )

    @staticmethod
    def _field_length(pic: str | None, usage: str) -> int:
        if not pic:
            return 0
        expanded = CopybookParser._expand_pic(pic)
        digits = sum(1 for char in expanded if char in {"9", "Z", "*"})
        chars = sum(1 for char in expanded if char in {"X", "A"})
        sign = 1 if "S" in pic.upper() else 0
        if usage == "COMP-3":
            return math.ceil((digits + sign + 1) / 2)
        if usage in {"COMP", "BINARY"}:
            if digits <= 4:
                return 2
            if digits <= 9:
                return 4
            return 8
        if usage == "COMP-1":
            return 4
        if usage == "COMP-2":
            return 8
        return max(digits + chars, 1)

    @staticmethod
    def _expand_pic(pic: str) -> str:
        value = pic.upper().replace("V", "").replace("S", "")
        pattern = re.compile(r"([X9AZ*])\((\d+)\)")
        while match := pattern.search(value):
            value = (
                value[: match.start()] + match.group(1) * int(match.group(2)) + value[match.end() :]
            )
        return value

    @staticmethod
    def _source_line(source: DiscoveredFile, line: int) -> str:
        lines = (source.text or "").splitlines()
        return lines[line - 1].strip() if 1 <= line <= len(lines) else ""
