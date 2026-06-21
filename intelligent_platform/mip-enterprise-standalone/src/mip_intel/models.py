from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from hashlib import sha1
from typing import Any


def now_iso() -> str:
    return datetime.now(UTC).isoformat()


def stable_id(*parts: object) -> str:
    value = "|".join(str(part) for part in parts)
    return sha1(value.encode("utf-8")).hexdigest()[:16]


@dataclass(frozen=True)
class Evidence:
    source_path: str
    line_start: int | None = None
    line_end: int | None = None
    evidence_text: str = ""
    extractor: str = "manual"
    discovery_method: str = "observed"
    confidence: float = 1.0
    validation_status: str = "confirmed"


@dataclass(frozen=True)
class SourceMember:
    run_id: str
    relative_path: str
    folder_path: str
    member_name: str
    sha256: str
    size_bytes: int
    encoding: str | None
    is_binary: bool
    text_status: str
    artifact_type: str
    classification_basis: str
    confidence: float
    validation_status: str
    discovered_at: str = field(default_factory=now_iso)

    @property
    def member_id(self) -> str:
        return stable_id(self.run_id, "member", self.relative_path)


@dataclass(frozen=True)
class Asset:
    run_id: str
    asset_type: str
    technical_name: str
    display_name: str | None = None
    member_id: str | None = None
    folder_path: str | None = None
    confidence: float = 1.0
    validation_status: str = "confirmed"
    discovery_method: str = "observed"
    attributes: dict[str, Any] = field(default_factory=dict)
    created_at: str = field(default_factory=now_iso)

    @property
    def asset_id(self) -> str:
        return stable_id(self.run_id, "asset", self.asset_type, self.technical_name.upper())


@dataclass(frozen=True)
class Relationship:
    run_id: str
    relationship_type: str
    source_asset_id: str
    target_asset_id: str
    confidence: float = 1.0
    validation_status: str = "confirmed"
    discovery_method: str = "observed"
    attributes: dict[str, Any] = field(default_factory=dict)
    created_at: str = field(default_factory=now_iso)

    @property
    def relationship_id(self) -> str:
        return stable_id(
            self.run_id,
            "relationship",
            self.relationship_type,
            self.source_asset_id,
            self.target_asset_id,
            self.attributes,
        )


@dataclass(frozen=True)
class GraphSliceRequest:
    run_id: str
    root_asset_id: str
    mode: str = "neighborhood"
    direction: str = "both"
    depth: int = 1
    limit: int = 500
    relationship_types: tuple[str, ...] = ()
    confidence_min: float = 0.0

    def normalized(self) -> "GraphSliceRequest":
        depth = min(max(self.depth, 0), 8)
        limit = min(max(self.limit, 1), 1500)
        confidence = min(max(self.confidence_min, 0.0), 1.0)
        rels = tuple(sorted({item.upper() for item in self.relationship_types if item}))
        direction = self.direction.lower()
        if direction not in {"upstream", "downstream", "both"}:
            direction = "both"
        return GraphSliceRequest(
            run_id=self.run_id,
            root_asset_id=self.root_asset_id,
            mode=self.mode.lower(),
            direction=direction,
            depth=depth,
            limit=limit,
            relationship_types=rels,
            confidence_min=confidence,
        )

    @property
    def cache_key(self) -> str:
        req = self.normalized()
        return stable_id(
            req.run_id,
            req.root_asset_id,
            req.mode,
            req.direction,
            req.depth,
            req.limit,
            ",".join(req.relationship_types),
            req.confidence_min,
        )
