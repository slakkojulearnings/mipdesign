from __future__ import annotations

import re
from pathlib import Path

from mip.models import ArtifactType, ClassificationResult

_EXTENSION_MAP: dict[str, ArtifactType] = {
    ".cbl": ArtifactType.COBOL,
    ".cob": ArtifactType.COBOL,
    ".cobol": ArtifactType.COBOL,
    ".jcl": ArtifactType.JCL,
    ".proc": ArtifactType.JCL,
    ".prc": ArtifactType.JCL,
    ".cpy": ArtifactType.COPYBOOK,
    ".copy": ArtifactType.COPYBOOK,
    ".sql": ArtifactType.SQL,
    ".ddl": ArtifactType.SQL,
    ".bms": ArtifactType.BMS,
    ".dbd": ArtifactType.IMS,
    ".psb": ArtifactType.IMS,
    ".mqsc": ArtifactType.MQ,
    ".sch": ArtifactType.SCHEDULER,
    ".sched": ArtifactType.SCHEDULER,
    ".asm": ArtifactType.ASSEMBLER,
    ".s": ArtifactType.ASSEMBLER,
    ".pli": ArtifactType.PL1,
    ".pl1": ArtifactType.PL1,
    ".md": ArtifactType.DOCUMENTATION,
    ".txt": ArtifactType.DOCUMENTATION,
    ".rst": ArtifactType.DOCUMENTATION,
}

_FOLDER_HINTS: dict[str, ArtifactType] = {
    "cbl": ArtifactType.COBOL,
    "cobol": ArtifactType.COBOL,
    "jcl": ArtifactType.JCL,
    "proc": ArtifactType.JCL,
    "proclib": ArtifactType.JCL,
    "copy": ArtifactType.COPYBOOK,
    "copybook": ArtifactType.COPYBOOK,
    "cpy": ArtifactType.COPYBOOK,
    "sql": ArtifactType.SQL,
    "ddl": ArtifactType.SQL,
    "bms": ArtifactType.BMS,
    "ims": ArtifactType.IMS,
    "dbd": ArtifactType.IMS,
    "psb": ArtifactType.IMS,
    "mq": ArtifactType.MQ,
    "mqsc": ArtifactType.MQ,
    "sched": ArtifactType.SCHEDULER,
    "scheduler": ArtifactType.SCHEDULER,
    "asm": ArtifactType.ASSEMBLER,
    "assembler": ArtifactType.ASSEMBLER,
    "pli": ArtifactType.PL1,
    "control": ArtifactType.CONTROL_CARD,
    "cntl": ArtifactType.CONTROL_CARD,
}

_PATTERNS: list[tuple[ArtifactType, re.Pattern[str], float, str]] = [
    (
        ArtifactType.COBOL,
        re.compile(r"\bIDENTIFICATION\s+DIVISION\b|\bPROGRAM-ID\s*\.", re.I),
        0.98,
        "COBOL division or PROGRAM-ID",
    ),
    (
        ArtifactType.JCL,
        re.compile(r"(?m)^//[A-Z0-9@$#]+\s+(?:JOB|EXEC|PROC|DD)\b", re.I),
        0.98,
        "JCL statement",
    ),
    (
        ArtifactType.COPYBOOK,
        re.compile(
            r"(?m)^\s*(?:0?1|0?5|10|15|20|66|77|88)\s+[A-Z0-9-]+(?:\s+PIC\b|\.|\s+REDEFINES\b)",
            re.I,
        ),
        0.85,
        "COBOL data-description entries",
    ),
    (
        ArtifactType.SQL,
        re.compile(r"\bCREATE\s+(?:TABLE|VIEW|INDEX)\b|\bALTER\s+TABLE\b", re.I),
        0.92,
        "SQL DDL",
    ),
    (
        ArtifactType.BMS,
        re.compile(r"\bDFHMSD\b|\bDFHMDI\b|\bDFHMDF\b", re.I),
        0.96,
        "BMS macro",
    ),
    (
        ArtifactType.IMS,
        re.compile(r"\bDBD\b|\bSEGM\s+NAME\s*=|\bPSBGEN\b|\bPCB\s+TYPE\s*=\s*DB", re.I),
        0.90,
        "IMS DBD/PSB macro",
    ),
    (
        ArtifactType.MQ,
        re.compile(
            r"\bDEFINE\s+Q(?:LOCAL|REMOTE|ALIAS)\b|\bMQ(?:OPEN|PUT|GET|CLOSE|CONN|DISC)\b", re.I
        ),
        0.88,
        "IBM MQ command or API reference",
    ),
    (
        ArtifactType.SCHEDULER,
        re.compile(
            r"\b(?:CONTROL-M|CA-7|TWS|AUTOSYS)\b|\bRUNS_BEFORE\b|\bFOLLOWS\b|\bSCHEDULE\b", re.I
        ),
        0.78,
        "scheduler dependency definition",
    ),
    (
        ArtifactType.PL1,
        re.compile(r"\bDCL\b.*\bCHAR\b|\bPROC(?:EDURE)?\b.*\bOPTIONS\s*\(MAIN\)", re.I | re.S),
        0.82,
        "PL/I declaration or main procedure",
    ),
    (
        ArtifactType.ASSEMBLER,
        re.compile(r"(?m)^\s*[A-Z0-9@$#]*\s+(?:CSECT|DSECT|START)\b", re.I),
        0.78,
        "Assembler section directive",
    ),
]


def classify(path: Path, text: str | None, is_binary: bool) -> ClassificationResult:
    if is_binary:
        return ClassificationResult(
            artifact_type=ArtifactType.BINARY,
            confidence=1.0,
            reasons=["binary content"],
        )

    scores: dict[ArtifactType, float] = {}
    reasons: dict[ArtifactType, list[str]] = {}

    extension_type = _EXTENSION_MAP.get(path.suffix.lower())
    if extension_type:
        scores[extension_type] = max(scores.get(extension_type, 0.0), 0.72)
        reasons.setdefault(extension_type, []).append(f"extension {path.suffix.lower()}")

    lower_parts = {part.lower() for part in path.parts}
    for folder, artifact_type in _FOLDER_HINTS.items():
        if folder in lower_parts:
            scores[artifact_type] = max(scores.get(artifact_type, 0.0), 0.60)
            reasons.setdefault(artifact_type, []).append(f"folder hint {folder}")

    sample = (text or "")[:100_000]
    for artifact_type, pattern, score, reason in _PATTERNS:
        if pattern.search(sample):
            scores[artifact_type] = max(scores.get(artifact_type, 0.0), score)
            reasons.setdefault(artifact_type, []).append(reason)

    if not scores:
        return ClassificationResult(
            artifact_type=ArtifactType.UNKNOWN,
            confidence=0.20,
            reasons=["no known content signature"],
        )

    artifact_type, confidence = max(scores.items(), key=lambda item: item[1])
    # COBOL program evidence outranks a copybook-like data division.
    if artifact_type == ArtifactType.COPYBOOK and re.search(r"\bPROGRAM-ID\s*\.", sample, re.I):
        artifact_type, confidence = ArtifactType.COBOL, 0.99
        reasons.setdefault(artifact_type, []).append("PROGRAM-ID overrides copybook pattern")

    return ClassificationResult(
        artifact_type=artifact_type,
        confidence=confidence,
        reasons=reasons.get(artifact_type, []),
    )
