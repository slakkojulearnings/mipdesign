from __future__ import annotations

from enum import StrEnum
from pathlib import Path
from typing import Any

from pydantic import BaseModel, Field


class ArtifactType(StrEnum):
    COBOL = "COBOL"
    JCL = "JCL"
    COPYBOOK = "COPYBOOK"
    SQL = "SQL"
    BMS = "BMS"
    IMS = "IMS"
    MQ = "MQ"
    SCHEDULER = "SCHEDULER"
    ASSEMBLER = "ASSEMBLER"
    PL1 = "PL1"
    CONTROL_CARD = "CONTROL_CARD"
    DOCUMENTATION = "DOCUMENTATION"
    UNKNOWN = "UNKNOWN"
    BINARY = "BINARY"


class AssetType(StrEnum):
    REPOSITORY = "REPOSITORY"
    SOURCE_FILE = "SOURCE_FILE"
    PROGRAM = "PROGRAM"
    JOB = "JOB"
    JOB_STEP = "JOB_STEP"
    PROCEDURE = "PROCEDURE"
    COPYBOOK = "COPYBOOK"
    DATA_FIELD = "DATA_FIELD"
    DATASET = "DATASET"
    TABLE = "TABLE"
    FILE = "FILE"
    TRANSACTION = "TRANSACTION"
    MAPSET = "MAPSET"
    SCHEDULER = "SCHEDULER"
    SCHEDULE = "SCHEDULE"
    IMS_DATABASE = "IMS_DATABASE"
    IMS_SEGMENT = "IMS_SEGMENT"
    MQ_QUEUE = "MQ_QUEUE"
    ASSEMBLER_CSECT = "ASSEMBLER_CSECT"
    PL1_PROCEDURE = "PL1_PROCEDURE"
    TENANT = "TENANT"
    SHARD = "SHARD"
    MAP = "MAP"
    BUSINESS_RULE = "BUSINESS_RULE"
    SQL_OBJECT = "SQL_OBJECT"
    UNRESOLVED = "UNRESOLVED"


class RelationshipType(StrEnum):
    CALLS = "CALLS"
    DYNAMIC_CALL = "DYNAMIC_CALL"
    EXECUTES = "EXECUTES"
    CONTAINS_STEP = "CONTAINS_STEP"
    USES_PROCEDURE = "USES_PROCEDURE"
    USES_COPYBOOK = "USES_COPYBOOK"
    CONTAINS_FIELD = "CONTAINS_FIELD"
    REDEFINES = "REDEFINES"
    READS_TABLE = "READS_TABLE"
    WRITES_TABLE = "WRITES_TABLE"
    READS_DATASET = "READS_DATASET"
    WRITES_DATASET = "WRITES_DATASET"
    USES_DATASET = "USES_DATASET"
    READS_FILE = "READS_FILE"
    WRITES_FILE = "WRITES_FILE"
    STARTS_PROGRAM = "STARTS_PROGRAM"
    STARTS_TRANSACTION = "STARTS_TRANSACTION"
    USES_MAP = "USES_MAP"
    IMPLEMENTS_RULE = "IMPLEMENTS_RULE"
    CREATES = "CREATES"
    REFERENCES = "REFERENCES"
    EXPANDS_TO = "EXPANDS_TO"
    RESOLVES_SYMBOL = "RESOLVES_SYMBOL"
    PUTS_MESSAGE = "PUTS_MESSAGE"
    GETS_MESSAGE = "GETS_MESSAGE"
    USES_QUEUE = "USES_QUEUE"
    CONTAINS_SEGMENT = "CONTAINS_SEGMENT"
    PARENT_SEGMENT = "PARENT_SEGMENT"
    SCHEDULES = "SCHEDULES"
    TRIGGERS = "TRIGGERS"
    BELONGS_TO_TENANT = "BELONGS_TO_TENANT"
    ASSIGNED_TO_SHARD = "ASSIGNED_TO_SHARD"


class ClassificationResult(BaseModel):
    artifact_type: ArtifactType
    confidence: float = Field(ge=0.0, le=1.0)
    reasons: list[str] = Field(default_factory=list)


class DiscoveredFile(BaseModel):
    absolute_path: Path
    relative_path: str
    sha256: str
    size_bytes: int
    artifact_type: ArtifactType
    classification_confidence: float = Field(ge=0.0, le=1.0)
    classification_reasons: list[str] = Field(default_factory=list)
    encoding: str | None = None
    is_binary: bool = False
    text: str | None = None


class EvidenceCandidate(BaseModel):
    source_path: str
    line_start: int | None = None
    line_end: int | None = None
    evidence_text: str = ""
    extractor: str
    confidence: float = Field(default=1.0, ge=0.0, le=1.0)


class AssetCandidate(BaseModel):
    asset_type: AssetType
    technical_name: str
    readable_name: str | None = None
    attributes: dict[str, Any] = Field(default_factory=dict)
    confidence: float = Field(default=1.0, ge=0.0, le=1.0)
    evidence: list[EvidenceCandidate] = Field(default_factory=list)
    source_path: str | None = None


class RelationshipCandidate(BaseModel):
    relationship_type: RelationshipType
    source_type: AssetType
    source_name: str
    target_type: AssetType
    target_name: str
    attributes: dict[str, Any] = Field(default_factory=dict)
    confidence: float = Field(default=1.0, ge=0.0, le=1.0)
    evidence: list[EvidenceCandidate] = Field(default_factory=list)


class ParseIssue(BaseModel):
    severity: str = "WARNING"
    message: str
    source_path: str
    line_number: int | None = None


class ParseResult(BaseModel):
    assets: list[AssetCandidate] = Field(default_factory=list)
    relationships: list[RelationshipCandidate] = Field(default_factory=list)
    issues: list[ParseIssue] = Field(default_factory=list)


class AnalysisSummary(BaseModel):
    run_id: str
    source_root: str
    files_discovered: int
    files_parsed: int
    files_unknown: int
    assets: int
    relationships: int
    parse_issues: int
    database: str
    report_path: str | None = None
