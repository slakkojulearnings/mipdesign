"""MIP canonical metadata model (Pydantic v2).

These are the in-memory types that mirror `schema.sql`. Every entity and every
relationship carries the *evidence envelope* so that uncertainty is always visible
and every fact is traceable to its source.

This module is intentionally dependency-light (only pydantic) so it can be reused by
the reference implementation and by any downstream tool.
"""

from __future__ import annotations

from datetime import datetime, timezone
from enum import Enum

from pydantic import BaseModel, Field


# ---------------------------------------------------------------------------
# Evidence envelope — Principle 1 (Evidence-First, Confidence-Aware)
# ---------------------------------------------------------------------------
class ValidationStatus(str, Enum):
    CONFIRMED = "confirmed"        # backed by direct, unambiguous evidence
    INFERRED = "inferred"          # derived; plausible but not directly proven
    NEEDS_REVIEW = "needs_review"  # low confidence / dynamic / ambiguous — human must check


class DiscoveryMethod(str, Enum):
    SCAN = "scan"
    STATIC_PARSE = "static-parse"
    AST = "ast"
    DATA_FLOW = "data-flow"
    SEMANTIC = "semantic"
    RUNTIME = "runtime"
    INFERENCE = "inference"


def _now() -> datetime:
    return datetime.now(timezone.utc)


class Evidence(BaseModel):
    """The envelope attached to every fact in the platform."""

    source_evidence: str | None = None          # "file:line" or "scan:path"
    discovery_method: DiscoveryMethod = DiscoveryMethod.STATIC_PARSE
    confidence: float = Field(default=1.0, ge=0.0, le=1.0)
    validation_status: ValidationStatus = ValidationStatus.CONFIRMED
    discovered_at: datetime = Field(default_factory=_now)

    @classmethod
    def confirmed(cls, source: str, method: DiscoveryMethod = DiscoveryMethod.STATIC_PARSE) -> "Evidence":
        return cls(source_evidence=source, discovery_method=method,
                   confidence=1.0, validation_status=ValidationStatus.CONFIRMED)

    @classmethod
    def needs_review(cls, source: str, confidence: float = 0.3,
                     method: DiscoveryMethod = DiscoveryMethod.INFERENCE) -> "Evidence":
        """For dynamic calls, unresolved targets, semantic guesses, etc."""
        return cls(source_evidence=source, discovery_method=method,
                   confidence=confidence, validation_status=ValidationStatus.NEEDS_REVIEW)


# ---------------------------------------------------------------------------
# Entities (Level 1–2)
# ---------------------------------------------------------------------------
class ArtifactType(str, Enum):
    COBOL = "cobol"
    JCL = "jcl"
    COPYBOOK = "copybook"
    DB2 = "db2"
    VSAM = "vsam"
    CICS = "cics"
    PROC = "proc"
    UNKNOWN = "unknown"


class Artifact(BaseModel):
    artifact_id: str
    path: str
    artifact_type: ArtifactType
    file_name: str
    size_bytes: int | None = None
    line_count: int | None = None
    evidence: Evidence


class Program(BaseModel):
    program_id: str            # PROGRAM-ID, canonical
    program_name: str
    language: str = "cobol"
    artifact_id: str | None = None
    line_count: int | None = None
    evidence: Evidence


class Job(BaseModel):
    job_id: str
    job_name: str
    artifact_id: str | None = None
    evidence: Evidence


class JobStep(BaseModel):
    step_id: str
    job_id: str
    step_name: str
    program_name: str | None = None   # EXEC PGM= target (may be unresolved)
    step_order: int | None = None
    evidence: Evidence


class Copybook(BaseModel):
    copybook_id: str
    copybook_name: str
    artifact_id: str | None = None
    evidence: Evidence


class Db2Table(BaseModel):
    table_id: str
    table_name: str
    evidence: Evidence


# ---------------------------------------------------------------------------
# Relationship (Level 3: graph edge) — Principle 4 (relationships are first-class)
# ---------------------------------------------------------------------------
class RelType(str, Enum):
    CALLS = "CALLS"
    EXECUTES = "EXECUTES"
    USES = "USES"          # program USES copybook
    READS = "READS"
    WRITES = "WRITES"
    CONTAINS = "CONTAINS"
    DEPENDS_ON = "DEPENDS_ON"


class Relationship(BaseModel):
    relationship_id: str
    source_type: str
    source_id: str
    rel_type: RelType
    target_type: str
    target_id: str          # may be an unresolved name (dynamic call target)
    evidence: Evidence
