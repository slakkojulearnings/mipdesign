"""Lightweight runtime records + the evidence envelope.

Mirrors the canonical Pydantic model in ../../01-metadata-model/models.py but uses
stdlib dataclasses so the reference implementation has zero external dependencies.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass, field
from datetime import datetime, timezone

# validation_status values
CONFIRMED = "confirmed"
INFERRED = "inferred"
NEEDS_REVIEW = "needs_review"


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def make_id(*parts: str) -> str:
    return hashlib.sha1("|".join(parts).encode()).hexdigest()[:12]


@dataclass
class Evidence:
    """Attached to every fact so uncertainty is always visible (Principle 1)."""

    source_evidence: str
    discovery_method: str = "static-parse"
    confidence: float = 1.0
    validation_status: str = CONFIRMED
    discovered_at: str = field(default_factory=now_iso)

    @staticmethod
    def confirmed(source: str, method: str = "static-parse") -> "Evidence":
        return Evidence(source, method, 1.0, CONFIRMED)

    @staticmethod
    def needs_review(source: str, confidence: float = 0.3, method: str = "inference") -> "Evidence":
        return Evidence(source, method, confidence, NEEDS_REVIEW)


@dataclass
class Artifact:
    artifact_id: str
    path: str
    artifact_type: str
    file_name: str
    size_bytes: int
    line_count: int
    evidence: Evidence


@dataclass
class Program:
    program_id: str
    program_name: str
    language: str
    artifact_id: str
    line_count: int
    evidence: Evidence


@dataclass
class Job:
    job_id: str
    job_name: str
    artifact_id: str
    evidence: Evidence


@dataclass
class JobStep:
    step_id: str
    job_id: str
    step_name: str
    program_name: str | None
    step_order: int
    evidence: Evidence


@dataclass
class Edge:
    """A relationship row. target_id may be an unresolved name (dynamic call)."""

    relationship_id: str
    source_type: str
    source_id: str
    rel_type: str
    target_type: str
    target_id: str
    evidence: Evidence

    @staticmethod
    def build(source_type: str, source_id: str, rel_type: str,
              target_type: str, target_id: str, evidence: Evidence) -> "Edge":
        rid = make_id(source_type, source_id, rel_type, target_type, target_id)
        return Edge(rid, source_type, source_id, rel_type, target_type, target_id, evidence)
