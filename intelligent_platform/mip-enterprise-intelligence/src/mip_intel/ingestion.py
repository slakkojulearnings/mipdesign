from __future__ import annotations

import argparse
from concurrent.futures import ThreadPoolExecutor, as_completed
import hashlib
import json
import re
import time
from dataclasses import dataclass, replace
from pathlib import Path
from typing import Any

from .graph_service import GraphService
from .models import Asset, Evidence, Relationship, SourceMember, now_iso, stable_id
from .reference_parser import PARSER_VERSION, ast_tree, copybook_resolver, parse_cobol
from .repositories import SQLiteGraphRepository


EXTRACTOR = "mainframe_scanner_v1"
TEXT_LIMIT_BYTES = 4_000_000

FOLDER_TYPES = (
    (("app", "cbl"), "COBOL"),
    (("cobol",), "COBOL"),
    (("app", "cpy"), "COPYBOOK"),
    (("copylib",), "COPYBOOK"),
    (("app", "jcl"), "JCL"),
    (("jcl",), "JCL"),
    (("app", "proc"), "PROC"),
    (("proc",), "PROC"),
    (("app", "bms"), "BMS_MAP"),
    (("bms",), "BMS_MAP"),
    (("app", "csd"), "CSD"),
    (("csd",), "CSD"),
    (("sql",), "SQL_DDL"),
    (("db2",), "SQL_DDL"),
    (("ddl", "dcl"), "DCLGEN"),
    (("dcl",), "DCLGEN"),
    (("ims",), "IMS"),
    (("mq",), "MQ"),
    (("asm",), "ASSEMBLER"),
    (("scheduler",), "SCHEDULER"),
)

ASSET_BY_ARTIFACT = {
    "COBOL": "PROGRAM",
    "COPYBOOK": "COPYBOOK",
    "JCL": "JOB",
    "PROC": "PROC",
    "BMS_MAP": "MAP",
    "CSD": "CSD_RESOURCE",
    "SQL_DDL": "SQL_SCRIPT",
    "DCLGEN": "TABLE",
    "IMS": "IMS_RESOURCE",
    "MQ": "MQ_QUEUE",
    "ASSEMBLER": "PROGRAM",
    "SCHEDULER": "SCHEDULE",
    "BINARY": "BINARY_ARTIFACT",
    "UNKNOWN_TEXT": "UNKNOWN_ARTIFACT",
}


@dataclass(frozen=True)
class TextPayload:
    text: str
    encoding: str | None
    is_binary: bool
    text_status: str


@dataclass(frozen=True)
class ClassifiedMember:
    member: SourceMember
    text: str
    lines: tuple[str, ...]


@dataclass(frozen=True)
class FoundRelationship:
    relationship_type: str
    source_asset_id: str
    target: Asset
    evidence: Evidence
    confidence: float = 1.0
    validation_status: str = "confirmed"
    discovery_method: str = "observed"
    attributes: dict[str, Any] | None = None


@dataclass(frozen=True)
class ScanConfig:
    run_id: str | None = None
    resume: bool = False
    batch_size: int = 500
    max_workers: int = 1
    parse_timeout_seconds: float = 0.0
    fail_fast: bool = False

    @classmethod
    def from_dict(cls, config: dict[str, Any] | None, run_id: str | None = None) -> "ScanConfig":
        config = config or {}
        return cls(
            run_id=str(config.get("run_id") or run_id) if config.get("run_id") or run_id else None,
            resume=bool(config.get("resume", False)),
            batch_size=min(max(int(config.get("batch_size", 500)), 1), 10_000),
            max_workers=min(max(int(config.get("max_workers", 1)), 1), 32),
            parse_timeout_seconds=max(float(config.get("parse_timeout_seconds", 0.0)), 0.0),
            fail_fast=bool(config.get("fail_fast", False)),
        )

    def as_dict(self) -> dict[str, Any]:
        return {
            "run_id": self.run_id,
            "resume": self.resume,
            "batch_size": self.batch_size,
            "max_workers": self.max_workers,
            "parse_timeout_seconds": self.parse_timeout_seconds,
            "fail_fast": self.fail_fast,
        }


def scan_mainframe_tree(
    source_root: str | Path,
    db_path: str | Path,
    *,
    run_id: str | None = None,
    config: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """CLI-callable service function for deterministic source inventory and analysis."""
    repository = SQLiteGraphRepository(db_path)
    return scan_mainframe_estate(source_root, repository, run_id=run_id, config=config)


def scan_mainframe_estate(
    source_root: str | Path,
    repository: SQLiteGraphRepository,
    *,
    run_id: str | None = None,
    config: dict[str, Any] | None = None,
) -> dict[str, Any]:
    scan_config = ScanConfig.from_dict(config, run_id=run_id)
    root = Path(source_root)
    selected_run_id = repository.create_run(
        str(root),
        run_id=scan_config.run_id,
        config=scan_config.as_dict(),
        resume=scan_config.resume,
    )
    repository.upsert_scan_progress(
        selected_run_id, "DISCOVERING", details={"source_root": str(root), "config": scan_config.as_dict()}
    )
    paths = _iter_files(root)
    repository.upsert_scan_progress(
        selected_run_id,
        "DISCOVERING",
        total_files=len(paths),
        processed_files=len(paths),
        details={"source_root": str(root)},
    )
    members, scan_issues = _classify_members(paths, root, selected_run_id, repository, scan_config)
    referenced_copies = _referenced_copy_names(members)
    members = _promote_referenced_copybooks(members, referenced_copies)
    copybooks, copybook_metadata = _copybook_index(members, referenced_copies)
    resolver_fingerprint = _copybook_fingerprint(copybooks, copybook_metadata)
    resolver = copybook_resolver(copybooks, copybook_metadata)
    parse_items = [
        item
        for item in members
        if item.member.artifact_type in {"COBOL", "ASSEMBLER"} and item.text
    ]
    repository.upsert_scan_progress(
        selected_run_id,
        "PARSING",
        total_files=len(members),
        processed_files=0,
        parsed_files=0,
        details={"parse_candidates": len(parse_items), "resolver_fingerprint": resolver_fingerprint},
    )
    cobol_analysis, parse_metrics, parse_issues = _parse_members(
        repository,
        parse_items,
        resolver=resolver,
        resolver_fingerprint=resolver_fingerprint,
        config=scan_config,
    )
    scan_issues.extend(parse_issues)

    assets: dict[str, Asset] = {}
    member_assets: dict[str, Asset] = {}
    relationships: list[FoundRelationship] = []
    warnings: list[dict[str, Any]] = []

    for item in members:
        asset = _asset_for_member(item, cobol_analysis.get(item.member.member_id))
        assets[asset.asset_id] = asset
        member_assets[item.member.member_id] = asset
        if item.member.validation_status != "confirmed" or item.member.is_binary:
            warnings.append(
                {
                    "path": item.member.relative_path,
                    "artifact_type": item.member.artifact_type,
                    "validation_status": item.member.validation_status,
                    "confidence": item.member.confidence,
                }
            )
            _record_scan_issue(
                repository,
                selected_run_id,
                item.member.relative_path,
                stage="CLASSIFY",
                severity="WARNING",
                error_type=item.member.validation_status,
                message=f"{item.member.artifact_type} classified with {item.member.validation_status}",
                details={"confidence": item.member.confidence, "basis": item.member.classification_basis},
            )

    repository.upsert_scan_progress(
        selected_run_id,
        "BUILDING_GRAPH",
        total_files=len(members),
        processed_files=len(members),
        parsed_files=parse_metrics["parsed_files"],
        cached_parse_hits=parse_metrics["cached_parse_hits"],
        failed_files=parse_metrics["failed_files"],
        details={"asset_count": len(assets)},
    )
    for item in members:
        source = member_assets[item.member.member_id]
        for rel in _relationships_for_member(item, source, cobol_analysis.get(item.member.member_id)):
            assets.setdefault(rel.target.asset_id, rel.target)
            relationships.append(rel)

    repository.upsert_scan_progress(
        selected_run_id,
        "PERSISTING",
        total_files=len(members),
        processed_files=len(members),
        parsed_files=parse_metrics["parsed_files"],
        cached_parse_hits=parse_metrics["cached_parse_hits"],
        failed_files=parse_metrics["failed_files"],
        details={"asset_count": len(assets), "relationship_count": len(relationships)},
    )
    _persist_graph(repository, selected_run_id, members, assets, relationships)

    repository.upsert_scan_progress(
        selected_run_id,
        "SUMMARIZING",
        total_files=len(members),
        processed_files=len(members),
        parsed_files=parse_metrics["parsed_files"],
        cached_parse_hits=parse_metrics["cached_parse_hits"],
        failed_files=parse_metrics["failed_files"],
    )
    GraphService(repository).recompute_summaries(selected_run_id)
    insight_count = write_deterministic_insights(repository, selected_run_id, warnings)
    repository.complete_run(selected_run_id)
    stats = repository.stats(selected_run_id)
    repository.upsert_scan_progress(
        selected_run_id,
        "COMPLETED",
        total_files=len(members),
        processed_files=len(members),
        parsed_files=parse_metrics["parsed_files"],
        cached_parse_hits=parse_metrics["cached_parse_hits"],
        failed_files=parse_metrics["failed_files"],
        details={"status": "COMPLETED", "issue_count": len(scan_issues)},
    )
    return {
        "run_id": selected_run_id,
        "source_root": str(root),
        "database": str(repository.db_path),
        "file_count": stats["run"]["file_count"] if stats["run"] else len(members),
        "asset_count": stats["run"]["asset_count"] if stats["run"] else len(assets),
        "relationship_count": stats["run"]["relationship_count"] if stats["run"] else len(relationships),
        "insight_count": insight_count,
        "parse_metrics": parse_metrics,
        "issue_count": len(scan_issues),
        "warnings": warnings,
    }


def _classify_members(
    paths: list[Path],
    root: Path,
    run_id: str,
    repository: SQLiteGraphRepository,
    config: ScanConfig,
) -> tuple[list[ClassifiedMember], list[dict[str, Any]]]:
    members: list[ClassifiedMember] = []
    issues: list[dict[str, Any]] = []
    total = len(paths)
    for index, path in enumerate(paths, 1):
        try:
            members.append(_classify_path(path, root, run_id))
        except Exception as exc:
            issue = _record_scan_issue(
                repository,
                run_id,
                _relative_or_name(path, root),
                stage="CLASSIFY",
                severity="ERROR",
                error_type=type(exc).__name__,
                message=str(exc),
            )
            issues.append(issue)
            if config.fail_fast:
                raise
        if index % config.batch_size == 0 or index == total:
            repository.upsert_scan_progress(
                run_id,
                "CLASSIFYING",
                total_files=total,
                processed_files=index,
                failed_files=len(issues),
            )
    return members, issues


def _parse_members(
    repository: SQLiteGraphRepository,
    items: list[ClassifiedMember],
    *,
    resolver,
    resolver_fingerprint: str,
    config: ScanConfig,
) -> tuple[dict[str, dict[str, Any]], dict[str, int], list[dict[str, Any]]]:
    analysis: dict[str, dict[str, Any]] = {}
    issues: list[dict[str, Any]] = []
    metrics = {"parsed_files": 0, "cached_parse_hits": 0, "failed_files": 0}
    total = len(items)
    if config.max_workers > 1 and total > 1:
        with ThreadPoolExecutor(max_workers=config.max_workers) as executor:
            futures = {
                executor.submit(
                    _parse_cobol_cached,
                    repository,
                    item,
                    resolver=resolver,
                    resolver_fingerprint=resolver_fingerprint,
                    soft_timeout_seconds=config.parse_timeout_seconds,
                ): item
                for item in items
            }
            for index, future in enumerate(as_completed(futures), 1):
                item = futures[future]
                try:
                    payload, issue = future.result()
                except Exception as exc:
                    payload = _parse_error_payload(item.text, exc)
                    issue = _record_scan_issue(
                        repository,
                        item.member.run_id,
                        item.member.relative_path,
                        stage="PARSE",
                        severity="ERROR",
                        error_type=type(exc).__name__,
                        message=str(exc),
                        details={"parallel_worker": True},
                    )
                _record_parse_result(
                    analysis,
                    issues,
                    metrics,
                    item,
                    payload,
                    issue,
                    config,
                )
                if index % config.batch_size == 0 or index == total:
                    _update_parse_progress(repository, item.member.run_id, total, index, metrics, config)
        return analysis, metrics, issues

    for index, item in enumerate(items, 1):
        payload, issue = _parse_cobol_cached(
            repository,
            item,
            resolver=resolver,
            resolver_fingerprint=resolver_fingerprint,
            soft_timeout_seconds=config.parse_timeout_seconds,
        )
        _record_parse_result(analysis, issues, metrics, item, payload, issue, config)
        if index % config.batch_size == 0 or index == total:
            _update_parse_progress(repository, item.member.run_id, total, index, metrics, config)
    return analysis, metrics, issues


def _record_parse_result(
    analysis: dict[str, dict[str, Any]],
    issues: list[dict[str, Any]],
    metrics: dict[str, int],
    item: ClassifiedMember,
    payload: dict[str, Any],
    issue: dict[str, Any] | None,
    config: ScanConfig,
) -> None:
    analysis[item.member.member_id] = payload
    metrics["parsed_files"] += 1
    if payload.get("parser", {}).get("cache_hit"):
        metrics["cached_parse_hits"] += 1
    if issue:
        issues.append(issue)
        metrics["failed_files"] += 1
        if config.fail_fast and issue.get("severity") == "ERROR":
            raise RuntimeError(issue["message"])


def _update_parse_progress(
    repository: SQLiteGraphRepository,
    run_id: str,
    total: int,
    processed: int,
    metrics: dict[str, int],
    config: ScanConfig,
) -> None:
    repository.upsert_scan_progress(
        run_id,
        "PARSING",
        total_files=total,
        processed_files=processed,
        parsed_files=metrics["parsed_files"],
        cached_parse_hits=metrics["cached_parse_hits"],
        failed_files=metrics["failed_files"],
        details={"max_workers": config.max_workers},
    )


def _persist_graph(
    repository: SQLiteGraphRepository,
    run_id: str,
    members: list[ClassifiedMember],
    assets: dict[str, Asset],
    relationships: list[FoundRelationship],
) -> None:
    with repository.connect() as conn:
        for item in members:
            _upsert_member(conn, item.member)
        for asset in sorted(assets.values(), key=lambda value: (value.asset_type, value.technical_name)):
            evidence = []
            if asset.member_id:
                evidence = [
                    Evidence(
                        source_path=asset.attributes.get("relative_path", asset.technical_name),
                        evidence_text=asset.attributes.get("classification_basis", ""),
                        extractor=EXTRACTOR,
                        discovery_method=asset.discovery_method,
                        confidence=asset.confidence,
                        validation_status=asset.validation_status,
                    )
                ]
            _upsert_asset(conn, repository, asset, evidence)
        for rel in sorted(
            relationships,
            key=lambda value: (
                value.relationship_type,
                value.source_asset_id,
                value.target.asset_id,
                value.evidence.source_path,
                value.evidence.line_start or 0,
            ),
        ):
            relationship = Relationship(
                run_id=run_id,
                relationship_type=rel.relationship_type,
                source_asset_id=rel.source_asset_id,
                target_asset_id=rel.target.asset_id,
                confidence=rel.confidence,
                validation_status=rel.validation_status,
                discovery_method=rel.discovery_method,
                attributes=rel.attributes or {},
            )
            _insert_relationship(conn, repository, relationship, [rel.evidence])


def _upsert_member(conn, member: SourceMember) -> None:
    conn.execute(
        """
        INSERT OR REPLACE INTO source_member(
            member_id, run_id, relative_path, folder_path, member_name, sha256,
            size_bytes, encoding, is_binary, text_status, artifact_type,
            classification_basis, confidence, validation_status, discovered_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            member.member_id,
            member.run_id,
            member.relative_path,
            member.folder_path,
            member.member_name,
            member.sha256,
            member.size_bytes,
            member.encoding,
            int(member.is_binary),
            member.text_status,
            member.artifact_type,
            member.classification_basis,
            member.confidence,
            member.validation_status,
            member.discovered_at,
        ),
    )


def _upsert_asset(
    conn,
    repository: SQLiteGraphRepository,
    asset: Asset,
    evidence: list[Evidence],
) -> None:
    conn.execute(
        """
        INSERT OR REPLACE INTO asset(
            asset_id, run_id, asset_type, technical_name, display_name, member_id,
            folder_path, confidence, validation_status, discovery_method,
            attributes_json, created_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            asset.asset_id,
            asset.run_id,
            asset.asset_type,
            asset.technical_name.upper(),
            asset.display_name or asset.technical_name.upper(),
            asset.member_id,
            asset.folder_path,
            asset.confidence,
            asset.validation_status,
            asset.discovery_method,
            json.dumps(asset.attributes, sort_keys=True),
            asset.created_at,
        ),
    )
    for item in evidence:
        repository._insert_evidence(conn, asset.run_id, "ASSET", asset.asset_id, item)


def _insert_relationship(
    conn,
    repository: SQLiteGraphRepository,
    relationship: Relationship,
    evidence: list[Evidence],
) -> None:
    conn.execute(
        """
        INSERT OR REPLACE INTO relationship(
            relationship_id, run_id, relationship_type, source_asset_id,
            target_asset_id, confidence, validation_status, discovery_method,
            attributes_json, created_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            relationship.relationship_id,
            relationship.run_id,
            relationship.relationship_type,
            relationship.source_asset_id,
            relationship.target_asset_id,
            relationship.confidence,
            relationship.validation_status,
            relationship.discovery_method,
            json.dumps(relationship.attributes, sort_keys=True),
            relationship.created_at,
        ),
    )
    for item in evidence:
        repository._insert_evidence(
            conn, relationship.run_id, "RELATIONSHIP", relationship.relationship_id, item
        )


def write_deterministic_insights(
    repository: SQLiteGraphRepository,
    run_id: str,
    warnings: list[dict[str, Any]] | None = None,
) -> int:
    warnings = warnings or []
    created = 0
    stats = repository.stats(run_id)
    run = stats["run"] or {}
    with repository.connect() as conn:
        conn.execute("DELETE FROM insight WHERE run_id = ?", (run_id,))
        created += _insert_insight(
            conn,
            run_id,
            "INVENTORY_SUMMARY",
            None,
            "Inventory completed",
            (
                f"Scanned {run.get('file_count', 0)} files into "
                f"{run.get('asset_count', 0)} assets and "
                f"{run.get('relationship_count', 0)} relationships."
            ),
            1.0,
            "confirmed",
            [{"entity_kind": "RUN", "entity_id": run_id}],
        )
        for row in conn.execute(
            """
            SELECT rs.*, a.technical_name
            FROM root_summary rs JOIN asset a ON a.asset_id = rs.root_asset_id
            WHERE rs.run_id = ?
            ORDER BY rs.risk_score DESC, a.technical_name
            """,
            (run_id,),
        ).fetchall():
            status = "needs_review" if row["unresolved_count"] else "confirmed"
            confidence = 0.75 if status == "needs_review" else 0.95
            created += _insert_insight(
                conn,
                run_id,
                "ROOT_SUMMARY",
                row["root_asset_id"],
                f"Root candidate {row['technical_name']}",
                (
                    f"{row['technical_name']} reaches {row['reachable_assets']} assets, "
                    f"{row['reachable_programs']} programs, and "
                    f"{row['data_touchpoints']} data touchpoints."
                ),
                confidence,
                status,
                [{"entity_kind": "ASSET", "entity_id": row["root_asset_id"]}],
            )
        if warnings:
            created += _insert_insight(
                conn,
                run_id,
                "INGESTION_GAPS",
                None,
                "Ingestion gaps require review",
                f"{len(warnings)} files were binary, unknown, or low-confidence classifications.",
                0.65,
                "needs_review",
                warnings[:25],
            )
    return created


def _insert_insight(
    conn,
    run_id: str,
    insight_type: str,
    subject_asset_id: str | None,
    title: str,
    body: str,
    confidence: float,
    validation_status: str,
    citations: list[dict[str, Any]],
) -> int:
    conn.execute(
        """
        INSERT OR REPLACE INTO insight(
            insight_id, run_id, insight_type, subject_asset_id, title, body,
            confidence, validation_status, citations_json, created_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            stable_id(run_id, "insight", insight_type, subject_asset_id or "", title),
            run_id,
            insight_type,
            subject_asset_id,
            title,
            body,
            confidence,
            validation_status,
            json.dumps(citations, sort_keys=True),
            now_iso(),
        ),
    )
    return 1


def _iter_files(root: Path) -> list[Path]:
    if not root.exists():
        raise FileNotFoundError(root)
    return sorted(path for path in root.rglob("*") if path.is_file())


def _classify_path(path: Path, root: Path, run_id: str) -> ClassifiedMember:
    data = path.read_bytes()
    relative = path.relative_to(root).as_posix()
    folder = path.parent.relative_to(root).as_posix()
    payload = _read_text(data)
    artifact_type, basis, confidence, status = _classify(relative, payload)
    member = SourceMember(
        run_id=run_id,
        relative_path=relative,
        folder_path="" if folder == "." else folder,
        member_name=path.name,
        sha256=hashlib.sha256(data).hexdigest(),
        size_bytes=len(data),
        encoding=payload.encoding,
        is_binary=payload.is_binary,
        text_status=payload.text_status,
        artifact_type=artifact_type,
        classification_basis=basis,
        confidence=confidence,
        validation_status=status,
    )
    return ClassifiedMember(member=member, text=payload.text, lines=tuple(payload.text.splitlines()))


def _read_text(data: bytes) -> TextPayload:
    if not data:
        return TextPayload("", "utf-8", False, "TEXT")
    sample = data[:8192]
    if b"\x00" in sample or _non_text_ratio(sample) > 0.30 or len(data) > TEXT_LIMIT_BYTES:
        return TextPayload("", None, True, "BINARY")
    for encoding in ("utf-8", "cp037", "latin-1"):
        try:
            text = data.decode(encoding)
        except UnicodeDecodeError:
            continue
        status = "TEXT" if encoding == "utf-8" else "DECODED"
        return TextPayload(text, encoding, False, status)
    return TextPayload("", None, True, "BINARY")


def _non_text_ratio(data: bytes) -> float:
    allowed = set(range(32, 127)) | {9, 10, 12, 13}
    return sum(1 for byte in data if byte not in allowed) / max(len(data), 1)


def _classify(relative_path: str, payload: TextPayload) -> tuple[str, str, float, str]:
    if payload.is_binary:
        return "BINARY", "binary content detector", 1.0, "confirmed"

    parts = tuple(part.lower() for part in Path(relative_path).parts[:-1])
    for markers, artifact_type in FOLDER_TYPES:
        if _contains_ordered(parts, markers):
            return artifact_type, f"folder:{'/'.join(markers)}", 0.95, "confirmed"

    text = payload.text.upper()
    content_rules = (
        ("COBOL", "content:PROGRAM-ID", 0.90, r"\bPROGRAM-ID\s*\."),
        ("JCL", "content:JCL JOB/EXEC", 0.85, r"(?m)^\s*//\S+\s+(JOB|EXEC)\b"),
        ("PROC", "content:JCL PROC", 0.85, r"(?m)^\s*//\S+\s+PROC\b"),
        ("COPYBOOK", "content:copybook level numbers", 0.70, r"(?m)^\s*(01|05|10|77)\s+\S+"),
        (
            "SQL_DDL",
            "content:SQL DDL",
            0.90,
            r"\b(CREATE|ALTER|DROP)\s+(?:UNIQUE\s+)?(?:TABLE|INDEX|VIEW|DATABASE|BUFFERPOOL|LOCATION|(?:REGULAR|LARGE|TEMPORARY)\s+TABLESPACE|TABLESPACE)\b",
        ),
        ("DCLGEN", "content:DECLARE TABLE", 0.90, r"\bDECLARE\s+TABLE\b"),
        ("BMS_MAP", "content:BMS macros", 0.90, r"\bDFH(MSD|MDI|MDF)\b"),
        ("MQ", "content:MQ definitions", 0.80, r"\b(DEFINE\s+QLOCAL|MQPUT|MQGET|MQOPEN)\b"),
        ("IMS", "content:IMS definitions", 0.80, r"\b(PSBGEN|DBDGEN|PCB\s+TYPE=|SEGM\s+NAME=)\b"),
        ("ASSEMBLER", "content:assembler CSECT", 0.80, r"\bCSECT\b"),
        ("SCHEDULER", "content:scheduler", 0.75, r"\b(SCHEDULE|CALENDAR|RUN\s+DAILY)\b"),
    )
    for artifact_type, basis, confidence, pattern in content_rules:
        if re.search(pattern, text):
            return artifact_type, basis, confidence, "inferred" if confidence < 0.90 else "confirmed"
    return "UNKNOWN_TEXT", "no folder/content rule matched", 0.35, "needs_review"


def _contains_ordered(parts: tuple[str, ...], markers: tuple[str, ...]) -> bool:
    if len(markers) == 1:
        return markers[0] in parts
    return any(parts[index : index + len(markers)] == markers for index in range(len(parts)))


def _referenced_copy_names(members: list[ClassifiedMember]) -> set[str]:
    names: set[str] = set()
    for item in members:
        if item.member.is_binary or not item.text:
            continue
        for match in re.finditer(r"\bCOPY\s+([A-Z0-9#$@_-]+)", item.text, re.I):
            names.add(_clean_name(match.group(1)))
    return names


def _promote_referenced_copybooks(
    members: list[ClassifiedMember], referenced_copies: set[str]
) -> list[ClassifiedMember]:
    if not referenced_copies:
        return members
    promoted = []
    for item in members:
        aliases = _member_aliases(item, item.member.artifact_type)
        if (
            item.member.artifact_type == "UNKNOWN_TEXT"
            and aliases & referenced_copies
            and not item.member.is_binary
        ):
            member = replace(
                item.member,
                artifact_type="COPYBOOK",
                classification_basis="referenced-by-copy-name",
                confidence=0.82,
                validation_status="inferred",
            )
            promoted.append(replace(item, member=member))
        else:
            promoted.append(item)
    return promoted


def _copybook_index(
    members: list[ClassifiedMember], referenced_copies: set[str]
) -> tuple[dict[str, str], dict[str, dict[str, Any]]]:
    copybooks: dict[str, str] = {}
    metadata: dict[str, dict[str, Any]] = {}
    for item in members:
        if item.member.is_binary or not item.text:
            continue
        aliases = _member_aliases(item, item.member.artifact_type)
        plausible = item.member.artifact_type in {"COPYBOOK", "DCLGEN"} or (
            item.member.artifact_type == "UNKNOWN_TEXT" and bool(aliases & referenced_copies)
        )
        if not plausible:
            continue
        for name in aliases:
            if not name:
                continue
            copybooks.setdefault(name, item.text)
            metadata.setdefault(
                name,
                {
                    "source_path": item.member.relative_path,
                    "artifact_type": item.member.artifact_type,
                    "classification_basis": item.member.classification_basis,
                    "confidence": item.member.confidence,
                    "validation_status": item.member.validation_status,
                    "sha256": item.member.sha256,
                },
            )
    return copybooks, metadata


def _member_aliases(item: ClassifiedMember, artifact_type: str) -> set[str]:
    aliases = {
        _clean_name(item.member.member_name),
        _clean_name(Path(item.member.member_name).stem or item.member.member_name),
        _primary_name(item, artifact_type),
    }
    return {alias for alias in aliases if alias}


def _copybook_fingerprint(copybooks: dict[str, str], metadata: dict[str, dict[str, Any]]) -> str:
    rows = []
    for name, text in sorted(copybooks.items()):
        info = metadata.get(name, {})
        rows.append(
            {
                "name": name,
                "sha256": hashlib.sha256(text.encode("utf-8", errors="replace")).hexdigest(),
                "source_path": info.get("source_path"),
            }
        )
    return hashlib.sha256(json.dumps(rows, sort_keys=True).encode("utf-8")).hexdigest()


def _parse_cobol_cached(
    repository: SQLiteGraphRepository,
    item: ClassifiedMember,
    *,
    resolver,
    resolver_fingerprint: str,
    soft_timeout_seconds: float = 0.0,
) -> tuple[dict[str, Any], dict[str, Any] | None]:
    cache_key = stable_id("parse", item.member.sha256, resolver_fingerprint, PARSER_VERSION)
    cached = repository.get_cached_parse(cache_key)
    if cached:
        payload = json.loads(json.dumps(cached))
        parser = dict(payload.get("parser", {}))
        parser["cache_hit"] = True
        payload["parser"] = parser
        return payload, None
    started = time.perf_counter()
    try:
        payload = parse_cobol(item.text, resolver=resolver)
    except Exception as exc:
        payload = _parse_error_payload(item.text, exc)
        issue = _record_scan_issue(
            repository,
            item.member.run_id,
            item.member.relative_path,
            stage="PARSE",
            severity="ERROR",
            error_type=type(exc).__name__,
            message=str(exc),
            details={"parser_version": PARSER_VERSION},
        )
        return payload, issue
    elapsed_ms = int((time.perf_counter() - started) * 1000)
    parser = dict(payload.get("parser", {}))
    parser["cache_hit"] = False
    parser["elapsed_ms"] = elapsed_ms
    issue = None
    if soft_timeout_seconds and elapsed_ms > int(soft_timeout_seconds * 1000):
        parser["soft_timeout_exceeded"] = True
        parser["confidence"] = min(float(parser.get("confidence") or 1.0), 0.65)
        parser["validation_status"] = "needs_review"
        issue = _record_scan_issue(
            repository,
            item.member.run_id,
            item.member.relative_path,
            stage="PARSE",
            severity="WARNING",
            error_type="SoftParseTimeoutExceeded",
            message=f"Parse took {elapsed_ms}ms, above configured soft timeout",
            details={"elapsed_ms": elapsed_ms, "timeout_seconds": soft_timeout_seconds},
        )
    payload["parser"] = parser
    repository.put_cached_parse(
        cache_key=cache_key,
        source_sha256=item.member.sha256,
        resolver_fingerprint=resolver_fingerprint,
        parser_version=PARSER_VERSION,
        payload=payload,
    )
    return payload, issue


def _parse_error_payload(text: str, exc: Exception) -> dict[str, Any]:
    match = re.search(r"\bPROGRAM-ID\s*\.\s*([A-Z0-9#$@_-]+)", text, re.I)
    program = match.group(1).upper() if match else None
    return {
        "program_id": program,
        "divisions": [
            name
            for name in ("IDENTIFICATION", "ENVIRONMENT", "DATA", "PROCEDURE")
            if f"{name} DIVISION" in text.upper()
        ],
        "paragraphs": [],
        "data_items": [],
        "calls": [],
        "copies": [],
        "sql": [],
        "cics": [],
        "field_flows": [],
        "counts": {},
        "complexity": 1,
        "expanded": False,
        "copy_replacing": [],
        "copy_resolution": [],
        "dialect_profile": {},
        "parser": {
            "requested": "local-antlr4",
            "effective": "parse-error",
            "version": PARSER_VERSION,
            "confidence": 0.2,
            "validation_status": "needs_review",
            "error_type": type(exc).__name__,
        },
    }


def _record_scan_issue(
    repository: SQLiteGraphRepository,
    run_id: str,
    relative_path: str,
    *,
    stage: str,
    severity: str,
    error_type: str,
    message: str,
    details: dict[str, Any] | None = None,
) -> dict[str, Any]:
    repository.insert_scan_issue(
        run_id,
        relative_path,
        stage=stage,
        severity=severity,
        error_type=error_type,
        message=message,
        details=details,
    )
    return {
        "relative_path": relative_path,
        "stage": stage.upper(),
        "severity": severity.upper(),
        "error_type": error_type,
        "message": message,
        "details": details or {},
    }


def _relative_or_name(path: Path, root: Path) -> str:
    try:
        return path.relative_to(root).as_posix()
    except ValueError:
        return path.name


def _asset_for_member(item: ClassifiedMember, analysis: dict[str, Any] | None = None) -> Asset:
    artifact_type = item.member.artifact_type
    asset_type = ASSET_BY_ARTIFACT.get(artifact_type, "UNKNOWN_ARTIFACT")
    technical_name = analysis.get("program_id") if analysis and analysis.get("program_id") else _primary_name(item, artifact_type)
    status = item.member.validation_status
    confidence = item.member.confidence
    if analysis:
        parser = analysis.get("parser", {})
        parser_status = str(parser.get("validation_status") or "confirmed")
        parser_confidence = float(parser.get("confidence") or confidence)
        if parser_status != "confirmed":
            status = "needs_review"
        confidence = min(confidence, parser_confidence)
    attributes = {
        "artifact_type": artifact_type,
        "relative_path": item.member.relative_path,
        "classification_basis": item.member.classification_basis,
        "line_count": len(item.lines),
    }
    if analysis:
        attributes.update(
            {
                "parser": analysis.get("parser", {}),
                "copy_resolution": analysis.get("copy_resolution", []),
                "dialect_profile": analysis.get("dialect_profile", {}),
                "ast_summary": {
                    "program_id": analysis.get("program_id"),
                    "divisions": analysis.get("divisions", []),
                    "paragraphs": analysis.get("paragraphs", []),
                    "counts": analysis.get("counts", {}),
                    "complexity": analysis.get("complexity", 1),
                    "data_item_count": len(analysis.get("data_items", [])),
                    "field_flow_count": len(analysis.get("field_flows", [])),
                    "copy_replacing": analysis.get("copy_replacing", []),
                },
                "ast_tree": ast_tree(analysis),
            }
        )
    return Asset(
        run_id=item.member.run_id,
        asset_type=asset_type,
        technical_name=technical_name,
        display_name=technical_name,
        member_id=item.member.member_id,
        folder_path=item.member.folder_path,
        confidence=confidence,
        validation_status=status,
        discovery_method="observed" if status == "confirmed" else "inferred",
        attributes=attributes,
    )


def _primary_name(item: ClassifiedMember, artifact_type: str) -> str:
    text = item.text.upper()
    rules = {
        "COBOL": r"\bPROGRAM-ID\s*\.\s*([A-Z0-9#$@_-]+)",
        "JCL": r"(?m)^\s*//([A-Z0-9#$@]+)\s+JOB\b",
        "PROC": r"(?m)^\s*//([A-Z0-9#$@]+)\s+PROC\b",
        "DCLGEN": r"\bDECLARE\s+TABLE\s+([A-Z0-9_.$#@]+)",
        "SQL_DDL": r"\bCREATE\s+(?:(?:GLOBAL\s+TEMPORARY\s+)?TABLE|DATABASE|BUFFERPOOL|LOCATION|(?:REGULAR|LARGE|TEMPORARY)\s+TABLESPACE|TABLESPACE)\s+([A-Z0-9_.$#@]+)",
        "MQ": r"\bDEFINE\s+QLOCAL\(([^)]+)\)",
        "BMS_MAP": r"\b([A-Z0-9#$@]+)\s+DFHMSD\b",
        "IMS": r"\b(?:DBDGEN\s+.*?\bNAME|PSBGEN\s+.*?\bPSBNAME)=([A-Z0-9#$@_-]+)",
        "ASSEMBLER": r"(?m)^\s*([A-Z0-9#$@]+)\s+CSECT\b",
        "SCHEDULER": r"\bSCHEDULE\s+([A-Z0-9#$@_-]+)",
    }
    pattern = rules.get(artifact_type)
    if pattern:
        match = re.search(pattern, text)
        if match:
            return _clean_name(match.group(match.lastindex or 1))
    return _clean_name(Path(item.member.member_name).stem or item.member.member_name)


def _relationships_for_member(
    item: ClassifiedMember, source: Asset, analysis: dict[str, Any] | None = None
) -> list[FoundRelationship]:
    if item.member.is_binary or not item.lines:
        return []
    artifact_type = item.member.artifact_type
    if artifact_type in {"COBOL", "ASSEMBLER"}:
        return _cobol_relationships(item, source, analysis)
    if artifact_type in {"JCL", "PROC"}:
        return _jcl_relationships(item, source)
    if artifact_type in {"SQL_DDL", "DCLGEN"}:
        return _sql_relationships(item, source)
    if artifact_type == "IMS":
        return _ims_relationships(item, source)
    if artifact_type == "CSD":
        return _csd_relationships(item, source)
    if artifact_type == "SCHEDULER":
        return _scheduler_relationships(item, source)
    return []


def _cobol_relationships(
    item: ClassifiedMember, source: Asset, analysis: dict[str, Any] | None = None
) -> list[FoundRelationship]:
    found: list[FoundRelationship] = []
    seen: set[tuple[str, str, str]] = set()
    if analysis:
        parser = analysis.get("parser", {})
        parser_cap = float(parser.get("confidence") or 1.0)
        copy_resolution = {
            _clean_name(str(row.get("name", ""))): row
            for row in analysis.get("copy_resolution", [])
        }
        for copy in analysis.get("copies", []):
            name = _clean_name(str(copy.get("name", "")))
            if not name:
                continue
            line_no = int(copy.get("line") or _line_for_text(item.lines, f"COPY {name}") or 1)
            line = _line_at(item.lines, line_no)
            attrs = _copy_attributes(line)
            attrs["parser_effective"] = parser.get("effective")
            resolved = copy_resolution.get(name, {}).get("resolved", True)
            status = "confirmed" if resolved else "needs_review"
            confidence = 0.90 if attrs.get("copy_replacing") else 0.98
            if not resolved:
                confidence = 0.35
            _append_found(
                found,
                seen,
                _found(
                    item,
                    source,
                    "USES_COPYBOOK",
                    "COPYBOOK",
                    name,
                    line_no,
                    line,
                    confidence=min(confidence, parser_cap),
                    validation_status=status,
                    discovery_method="reference-parser",
                    attributes=attrs,
                ),
            )
        for call in analysis.get("calls", []):
            target = _clean_name(str(call.get("target", "")))
            if not target:
                continue
            line_no = int(call.get("line") or 1)
            if line_no <= 0 or line_no > len(item.lines):
                line_no = _copy_expansion_line(item.lines) or 1
            line = _line_at(item.lines, line_no)
            validation = str(call.get("validation") or "confirmed")
            confidence = float(call.get("confidence") or (1.0 if validation == "confirmed" else 0.55))
            confidence = min(confidence, parser_cap)
            if validation == "needs_review":
                _append_found(
                    found,
                    seen,
                    _found(
                        item,
                        source,
                        "DYNAMIC_CALL",
                        "UNRESOLVED",
                        f"DYNAMIC:{target}",
                        line_no,
                        line,
                        confidence=min(confidence, 0.40),
                        validation_status="needs_review",
                        discovery_method="reference-parser",
                        attributes={"unresolved_dynamic_target": True, "via": call.get("via")},
                    ),
                )
            else:
                status = "confirmed" if validation == "confirmed" else "inferred"
                _append_found(
                    found,
                    seen,
                    _found(
                        item,
                        source,
                        "CALLS",
                        "PROGRAM",
                        target,
                        line_no,
                        line,
                        confidence=confidence,
                        validation_status=status,
                        discovery_method="reference-parser",
                        attributes={
                            "call_kind": call.get("kind"),
                            "via": call.get("via"),
                            "parser_effective": parser.get("effective"),
                        },
                    ),
                )
        for sql in analysis.get("sql", []):
            op = str(sql.get("op", "")).upper()
            rel_type = "READS_TABLE" if op == "READS" else "WRITES_TABLE" if op == "WRITES" else ""
            table = _clean_name(str(sql.get("table", "")))
            if not rel_type or not table:
                continue
            line_no = int(sql.get("line") or 1)
            _append_found(
                found,
                seen,
                _found(
                    item,
                    source,
                    rel_type,
                    "TABLE",
                    table,
                    line_no,
                    _line_at(item.lines, line_no),
                    confidence=min(0.95, parser_cap),
                    validation_status="confirmed" if parser_cap >= 0.7 else "inferred",
                    discovery_method="reference-parser",
                    attributes={"parser_effective": parser.get("effective")},
                ),
            )
        for cics in analysis.get("cics", []):
            target = _clean_name(str(cics.get("target", "")))
            if not target:
                continue
            rel, target_type = _cics_relationship(cics)
            line_no = int(cics.get("line") or 1)
            _append_found(
                found,
                seen,
                _found(
                    item,
                    source,
                    rel,
                    target_type,
                    target,
                    line_no,
                    _line_at(item.lines, line_no),
                    confidence=min(float(cics.get("confidence") or 0.80), parser_cap),
                    validation_status=str(cics.get("validation") or "inferred"),
                    discovery_method="reference-parser",
                    attributes={"cics_kind": cics.get("kind"), "parser_effective": parser.get("effective")},
                ),
            )
    for line_no, line in enumerate(item.lines, 1):
        if _is_cobol_comment(line):
            continue
        upper = line.upper()
        for match in re.finditer(r"\bCALL\s+['\"]([A-Z0-9#$@_-]+)['\"]", upper):
            _append_found(found, seen, _found(item, source, "CALLS", "PROGRAM", match.group(1), line_no, line))
        for match in re.finditer(r"\bCALL\s+([A-Z][A-Z0-9#$@_-]+)", upper):
            _append_found(
                found,
                seen,
                _found(
                    item,
                    source,
                    "DYNAMIC_CALL",
                    "UNRESOLVED",
                    f"DYNAMIC:{match.group(1)}",
                    line_no,
                    line,
                    confidence=0.35,
                    validation_status="needs_review",
                    discovery_method="inferred",
                    attributes={"unresolved_dynamic_target": True},
                ),
            )
        for rel_type, pattern in (
            ("READS_TABLE", r"\bSELECT\b.*?\bFROM\s+([A-Z0-9_.$#@]+)"),
            ("WRITES_TABLE", r"\bINSERT\s+INTO\s+([A-Z0-9_.$#@]+)"),
            ("WRITES_TABLE", r"\bUPDATE\s+([A-Z0-9_.$#@]+)"),
            ("WRITES_TABLE", r"\bDELETE\s+FROM\s+([A-Z0-9_.$#@]+)"),
        ):
            for match in re.finditer(pattern, upper):
                _append_found(
                    found,
                    seen,
                    _found(item, source, rel_type, "TABLE", match.group(1), line_no, line, confidence=0.92),
                )
        for rel_type, pattern in (
            ("READS_FILE", r"\bREAD\s+([A-Z0-9#$@_-]+)"),
            ("WRITES_FILE", r"\bWRITE\s+([A-Z0-9#$@_-]+)"),
            ("WRITES_FILE", r"\bREWRITE\s+([A-Z0-9#$@_-]+)"),
        ):
            for match in re.finditer(pattern, upper):
                _append_found(
                    found,
                    seen,
                    _found(item, source, rel_type, "FILE", match.group(1), line_no, line, confidence=0.80),
                )
        for match in re.finditer(r"\bMAP\s*\(\s*['\"]?([A-Z0-9#$@_-]+)", upper):
            _append_found(
                found,
                seen,
                _found(item, source, "USES_MAP", "MAP", match.group(1), line_no, line, confidence=0.85),
            )
        for match in re.finditer(r"\bPROGRAM\s*\(\s*['\"]?([A-Z0-9#$@_-]+)", upper):
            _append_found(
                found,
                seen,
                _found(item, source, "CALLS", "PROGRAM", match.group(1), line_no, line, confidence=0.85),
            )
        for match in re.finditer(r"\b(MQPUT|MQGET|MQOPEN)\b.*?\b([A-Z0-9#$@._-]*Q[A-Z0-9#$@._-]*)", upper):
            _append_found(
                found,
                seen,
                _found(item, source, "USES_QUEUE", "MQ_QUEUE", match.group(2), line_no, line, confidence=0.70),
            )
    for rel in _vsam_file_control_relationships(item, source):
        _append_found(found, seen, rel)
    return found


def _vsam_file_control_relationships(item: ClassifiedMember, source: Asset) -> list[FoundRelationship]:
    found: list[FoundRelationship] = []
    text = "\n".join(item.lines)
    for match in re.finditer(
        r"\bSELECT\s+([A-Z0-9#$@_-]+)\s+ASSIGN\s+TO\s+([A-Z0-9.$#@_-]+)(.*?)(?:\.)",
        text,
        flags=re.I | re.S,
    ):
        logical_file = _clean_name(match.group(1))
        dataset = _clean_name(match.group(2))
        tail = match.group(3)
        line_no = _line_for_offset(text, match.start())
        attrs = {
            "logical_file": logical_file,
            "assignment": dataset,
            "source_clause": "SELECT ASSIGN",
        }
        organization = re.search(r"\bORGANIZATION\s+(?:IS\s+)?([A-Z0-9_-]+)", tail, re.I)
        access_mode = re.search(r"\bACCESS\s+MODE\s+(?:IS\s+)?([A-Z0-9_-]+)", tail, re.I)
        record_key = re.search(r"\bRECORD\s+KEY\s+(?:IS\s+)?([A-Z0-9#$@_-]+)", tail, re.I)
        if organization:
            attrs["organization"] = _clean_name(organization.group(1))
        if access_mode:
            attrs["access_mode"] = _clean_name(access_mode.group(1))
        if record_key:
            attrs["record_key"] = _clean_name(record_key.group(1))
        found.append(
            _found(
                item,
                source,
                "USES_DATASET",
                "DATASET",
                dataset,
                line_no,
                _line_at(item.lines, line_no),
                confidence=0.90,
                validation_status="confirmed",
                discovery_method="observed",
                attributes=attrs,
            )
        )
    for line_no, line in enumerate(item.lines, 1):
        if _is_cobol_comment(line):
            continue
        for match in re.finditer(r"\bFD\s+([A-Z0-9#$@_-]+)", line, re.I):
            found.append(
                _found(
                    item,
                    source,
                    "DEFINES_FILE",
                    "FILE",
                    match.group(1),
                    line_no,
                    line,
                    confidence=0.90,
                    validation_status="confirmed",
                    discovery_method="observed",
                    attributes={"source_clause": "FD"},
                )
            )
    return found


def _sql_relationships(item: ClassifiedMember, source: Asset) -> list[FoundRelationship]:
    found: list[FoundRelationship] = []
    seen: set[tuple[str, str, str, str]] = set()
    text = item.text
    for statement in _iter_sql_table_blocks(text):
        line_no = _line_for_offset(text, statement["offset"])
        table = statement["name"]
        body = statement["body"]
        attrs = {
            "dialect": "DB2",
            "statement": "CREATE TABLE",
            "columns": _sql_columns(body),
            "primary_key": _sql_primary_key(body),
        }
        _append_found(
            found,
            seen,
            _found(
                item,
                source,
                "DEFINES_TABLE",
                "TABLE",
                table,
                line_no,
                _line_at(item.lines, line_no),
                confidence=0.95,
                validation_status="confirmed",
                discovery_method="observed",
                attributes=attrs,
            ),
        )
    for statement in _iter_sql_index_blocks(text):
        line_no = _line_for_offset(text, statement["offset"])
        attrs = {
            "dialect": "DB2",
            "statement": "CREATE INDEX",
            "index_name": statement["index_name"],
            "unique": statement["unique"],
            "columns": [_clean_name(part.split()[0]) for part in _split_top_level_csv(statement["body"]) if part.strip()],
        }
        _append_found(
            found,
            seen,
            _found(
                item,
                source,
                "INDEXES_TABLE",
                "TABLE",
                statement["table_name"],
                line_no,
                _line_at(item.lines, line_no),
                confidence=0.92,
                validation_status="confirmed",
                discovery_method="observed",
                attributes=attrs,
            ),
        )
    for match in re.finditer(r"\bDECLARE\s+TABLE\s+([A-Z0-9_.$#@]+)", text, re.I):
        line_no = _line_for_offset(text, match.start())
        _append_found(
            found,
            seen,
            _found(
                item,
                source,
                "DECLARES_TABLE",
                "TABLE",
                match.group(1),
                line_no,
                _line_at(item.lines, line_no),
                confidence=0.92,
                validation_status="confirmed",
                discovery_method="observed",
                attributes={"dialect": "DB2", "statement": "DECLARE TABLE"},
            ),
        )
    for rel in _db2_infrastructure_relationships(item, source, text):
        _append_found(found, seen, rel)
    return found


def _db2_infrastructure_relationships(item: ClassifiedMember, source: Asset, text: str) -> list[FoundRelationship]:
    found: list[FoundRelationship] = []
    rules = (
        (
            "DEFINES_DB2_DATABASE",
            "DB2_DATABASE",
            r"\bCREATE\s+DATABASE\s+([A-Z0-9_.$#@]+)",
            "CREATE DATABASE",
            0.94,
        ),
        (
            "DEFINES_DB2_BUFFERPOOL",
            "DB2_BUFFERPOOL",
            r"\bCREATE\s+BUFFERPOOL\s+([A-Z0-9_.$#@]+)",
            "CREATE BUFFERPOOL",
            0.92,
        ),
        (
            "DEFINES_DB2_TABLESPACE",
            "DB2_TABLESPACE",
            r"\bCREATE\s+(?:REGULAR\s+|LARGE\s+|TEMPORARY\s+)?TABLESPACE\s+([A-Z0-9_.$#@]+)",
            "CREATE TABLESPACE",
            0.92,
        ),
        (
            "DEFINES_DB2_LOCATION",
            "DB2_LOCATION",
            r"\bCREATE\s+LOCATION\s+([A-Z0-9_.$#@]+)",
            "CREATE LOCATION",
            0.90,
        ),
    )
    for rel_type, target_type, pattern, statement, confidence in rules:
        for match in re.finditer(pattern, text, re.I):
            line_no = _line_for_offset(text, match.start())
            found.append(
                _found(
                    item,
                    source,
                    rel_type,
                    target_type,
                    match.group(1),
                    line_no,
                    _line_at(item.lines, line_no),
                    confidence=confidence,
                    validation_status="confirmed",
                    discovery_method="observed",
                    attributes={"dialect": "DB2", "statement": statement},
                )
            )
    return found


def _iter_sql_table_blocks(text: str) -> list[dict[str, Any]]:
    blocks: list[dict[str, Any]] = []
    pattern = re.compile(r"\bCREATE\s+(?:GLOBAL\s+TEMPORARY\s+)?TABLE\s+([A-Z0-9_.$#@]+)", re.I)
    for match in pattern.finditer(text):
        body = _parenthesized_body_after(text, match.end())
        if body is None:
            continue
        blocks.append({"name": _clean_name(match.group(1)), "body": body, "offset": match.start()})
    return blocks


def _iter_sql_index_blocks(text: str) -> list[dict[str, Any]]:
    blocks: list[dict[str, Any]] = []
    pattern = re.compile(r"\bCREATE\s+(UNIQUE\s+)?INDEX\s+([A-Z0-9_.$#@]+)\s+ON\s+([A-Z0-9_.$#@]+)", re.I)
    for match in pattern.finditer(text):
        body = _parenthesized_body_after(text, match.end())
        if body is None:
            continue
        blocks.append(
            {
                "unique": bool(match.group(1)),
                "index_name": _clean_name(match.group(2)),
                "table_name": _clean_name(match.group(3)),
                "body": body,
                "offset": match.start(),
            }
        )
    return blocks


def _parenthesized_body_after(text: str, offset: int) -> str | None:
    start = text.find("(", offset)
    if start < 0:
        return None
    depth = 0
    for index in range(start, len(text)):
        char = text[index]
        if char == "(":
            depth += 1
        elif char == ")":
            depth -= 1
            if depth == 0:
                return text[start + 1 : index]
    return None


def _sql_columns(body: str) -> list[dict[str, str]]:
    columns: list[dict[str, str]] = []
    for raw_part in _split_top_level_csv(body):
        part = " ".join(raw_part.strip().split())
        if not part:
            continue
        upper = part.upper()
        if upper.startswith(("PRIMARY ", "FOREIGN ", "UNIQUE ", "CHECK ", "CONSTRAINT ", "LIKE ")):
            continue
        pieces = part.split(maxsplit=1)
        if len(pieces) < 2:
            continue
        columns.append({"name": _clean_name(pieces[0]), "definition": pieces[1]})
    return columns


def _sql_primary_key(body: str) -> list[str]:
    match = re.search(r"\bPRIMARY\s+KEY\s*\((.*?)\)", body, re.I | re.S)
    if not match:
        return []
    return [_clean_name(part) for part in _split_top_level_csv(match.group(1)) if part.strip()]


def _split_top_level_csv(text: str) -> list[str]:
    parts: list[str] = []
    start = 0
    depth = 0
    quote: str | None = None
    for index, char in enumerate(text):
        if quote:
            if char == quote:
                quote = None
            continue
        if char in {"'", '"'}:
            quote = char
        elif char == "(":
            depth += 1
        elif char == ")":
            depth = max(depth - 1, 0)
        elif char == "," and depth == 0:
            parts.append(text[start:index])
            start = index + 1
    parts.append(text[start:])
    return parts


def _ims_relationships(item: ClassifiedMember, source: Asset) -> list[FoundRelationship]:
    found: list[FoundRelationship] = []
    seen: set[tuple[str, str, str, str]] = set()
    current_segment = ""
    for line_no, line in enumerate(item.lines, 1):
        upper = line.upper()
        dbd = re.search(r"\bDBDGEN\s+.*?\bNAME=([A-Z0-9#$@_-]+)", upper)
        if dbd:
            _append_found(
                found,
                seen,
                _found(
                    item,
                    source,
                    "DEFINES_IMS_DATABASE",
                    "IMS_DATABASE",
                    dbd.group(1),
                    line_no,
                    line,
                    confidence=0.95,
                    validation_status="confirmed",
                    discovery_method="observed",
                    attributes={"ims_statement": "DBDGEN"},
                ),
            )
        psb = re.search(r"\bPSBGEN\s+.*?\bPSBNAME=([A-Z0-9#$@_-]+)", upper)
        if psb:
            _append_found(
                found,
                seen,
                _found(
                    item,
                    source,
                    "DEFINES_IMS_PSB",
                    "IMS_PSB",
                    psb.group(1),
                    line_no,
                    line,
                    confidence=0.95,
                    validation_status="confirmed",
                    discovery_method="observed",
                    attributes={"ims_statement": "PSBGEN"},
                ),
            )
        segment = re.search(r"\bSEGM\s+.*?\bNAME=([A-Z0-9#$@_-]+)", upper)
        if segment:
            current_segment = _clean_name(segment.group(1))
            _append_found(
                found,
                seen,
                _found(
                    item,
                    source,
                    "CONTAINS_IMS_SEGMENT",
                    "IMS_SEGMENT",
                    current_segment,
                    line_no,
                    line,
                    confidence=0.92,
                    validation_status="confirmed",
                    discovery_method="observed",
                    attributes={
                        "ims_statement": "SEGM",
                        "parent": _ims_option(upper, "PARENT"),
                        "bytes": _ims_option(upper, "BYTES"),
                    },
                ),
            )
        field = re.search(r"\bFIELD\s+.*?\bNAME=([A-Z0-9#$@_-]+)", upper)
        if field:
            attrs = {
                "ims_statement": "FIELD",
                "segment": current_segment,
                "bytes": _ims_option(upper, "BYTES"),
                "start": _ims_option(upper, "START"),
                "field_type": _ims_option(upper, "TYPE"),
            }
            _append_found(
                found,
                seen,
                _found(
                    item,
                    source,
                    "DEFINES_IMS_FIELD",
                    "IMS_FIELD",
                    field.group(1),
                    line_no,
                    line,
                    confidence=0.90,
                    validation_status="confirmed",
                    discovery_method="observed",
                    attributes=attrs,
                ),
            )
        dataset = re.search(r"\bDATASET\s+.*?\b(?:DSN|DD1)=([A-Z0-9.$#@_-]+)", upper)
        if dataset:
            _append_found(
                found,
                seen,
                _found(
                    item,
                    source,
                    "USES_DATASET",
                    "DATASET",
                    dataset.group(1),
                    line_no,
                    line,
                    confidence=0.82,
                    validation_status="inferred",
                    discovery_method="observed",
                    attributes={"ims_statement": "DATASET"},
                ),
            )
        pcb = re.search(r"\bPCB\s+.*?\bDBDNAME=([A-Z0-9#$@_-]+)", upper)
        if pcb:
            _append_found(
                found,
                seen,
                _found(
                    item,
                    source,
                    "USES_IMS_DATABASE",
                    "IMS_DATABASE",
                    pcb.group(1),
                    line_no,
                    line,
                    confidence=0.92,
                    validation_status="confirmed",
                    discovery_method="observed",
                    attributes={"ims_statement": "PCB", "procopt": _ims_option(upper, "PROCOPT")},
                ),
            )
        senseg = re.search(r"\bSENSEG\s+.*?\bNAME=([A-Z0-9#$@_-]+)", upper)
        if senseg:
            _append_found(
                found,
                seen,
                _found(
                    item,
                    source,
                    "USES_IMS_SEGMENT",
                    "IMS_SEGMENT",
                    senseg.group(1),
                    line_no,
                    line,
                    confidence=0.88,
                    validation_status="confirmed",
                    discovery_method="observed",
                    attributes={"ims_statement": "SENSEG", "parent": _ims_option(upper, "PARENT")},
                ),
            )
    return found


def _ims_option(line: str, option: str) -> str | None:
    match = re.search(rf"\b{re.escape(option)}=([A-Z0-9.$#@_-]+)", line, re.I)
    return _clean_name(match.group(1)) if match else None


def _line_for_offset(text: str, offset: int) -> int:
    return text.count("\n", 0, max(offset, 0)) + 1


def _append_found(
    found: list[FoundRelationship], seen: set[tuple[str, str, str, str]], rel: FoundRelationship
) -> None:
    attrs_key = json.dumps(rel.attributes or {}, sort_keys=True, default=str)
    key = (rel.relationship_type, rel.source_asset_id, rel.target.asset_id, attrs_key)
    if key in seen:
        return
    seen.add(key)
    found.append(rel)


def _line_at(lines: tuple[str, ...], line_no: int) -> str:
    if line_no <= 0 or line_no > len(lines):
        return ""
    return lines[line_no - 1]


def _is_cobol_comment(line: str) -> bool:
    stripped = line.lstrip()
    return stripped.startswith("*") or stripped.startswith("/") or stripped.startswith("*>")


def _line_for_text(lines: tuple[str, ...], text: str) -> int | None:
    needle = text.upper()
    for line_no, line in enumerate(lines, 1):
        if needle in line.upper():
            return line_no
    return None


def _copy_expansion_line(lines: tuple[str, ...]) -> int | None:
    for line_no, line in enumerate(lines, 1):
        if "COPY " in line.upper():
            return line_no
    return None


def _copy_attributes(line: str) -> dict[str, Any]:
    if " REPLACING " not in line.upper():
        return {}
    return {
        "copy_replacing": True,
        "replacement_pairs": _replacement_pairs(line),
    }


def _replacement_pairs(line: str) -> list[dict[str, str]]:
    pairs = []
    for src, dst in re.findall(
        r"(==.*?==|:[^:]+:|'[^']*'|\"[^\"]*\"|[^\s.]+)\s+BY\s+"
        r"(==.*?==|:[^:]+:|'[^']*'|\"[^\"]*\"|[^\s.]+)",
        line,
        flags=re.I,
    ):
        pairs.append({"from": _strip_pseudo(src), "to": _strip_pseudo(dst)})
    return pairs


def _strip_pseudo(value: str) -> str:
    text = value.strip()
    if text.startswith("==") and text.endswith("=="):
        return text[2:-2]
    if len(text) >= 2 and text[0] == ":" and text[-1] == ":":
        return text[1:-1]
    return text.strip("'\"")


def _cics_relationship(cics: dict[str, Any]) -> tuple[str, str]:
    rel = str(cics.get("rel") or "USES").upper()
    target_type = str(cics.get("ttype") or "CICS_RESOURCE").upper()
    if target_type == "QUEUE":
        return ("READS_QUEUE" if rel == "READS" else "WRITES_QUEUE" if rel == "WRITES" else "USES_QUEUE"), "MQ_QUEUE"
    if target_type == "DATASET":
        return ("READS_DATASET" if rel == "READS" else "WRITES_DATASET" if rel == "WRITES" else "USES_DATASET"), "DATASET"
    mapping = {
        "READS": "READS_FILE",
        "WRITES": "WRITES_FILE",
        "STARTS": "STARTS_TRANSACTION",
        "USES": "USES_MAP",
    }
    type_mapping = {
        "MAP": "MAP",
        "PROGRAM": "PROGRAM",
        "TRANSACTION": "TRANSACTION",
        "FILE": "FILE",
    }
    return mapping.get(rel, rel), type_mapping.get(target_type, target_type)


def _jcl_relationships(item: ClassifiedMember, source: Asset) -> list[FoundRelationship]:
    found: list[FoundRelationship] = []
    for line_no, line in enumerate(item.lines, 1):
        upper = line.upper()
        for match in re.finditer(r"\bEXEC\s+(?:(PGM|PROC)=)?([A-Z0-9#$@_-]+)", upper):
            kind = match.group(1)
            target = match.group(2)
            if target in {"PGM", "PROC"}:
                continue
            target_type = "PROGRAM" if kind == "PGM" else "PROC"
            rel_type = "EXECUTES"
            found.append(_found(item, source, rel_type, target_type, target, line_no, line, confidence=0.95))
        for match in re.finditer(r"\bDSN=([A-Z0-9.$#@_-]+)", upper):
            rel_type = "WRITES_DATASET" if any(token in upper for token in ("DISP=(NEW", "DISP=NEW", "DISP=MOD")) else "READS_DATASET"
            found.append(_found(item, source, rel_type, "DATASET", match.group(1), line_no, line, confidence=0.75))
    return found


def _csd_relationships(item: ClassifiedMember, source: Asset) -> list[FoundRelationship]:
    found: list[FoundRelationship] = []
    for line_no, line in enumerate(item.lines, 1):
        upper = line.upper()
        for match in re.finditer(r"\bDEFINE\s+PROGRAM\(([^)]+)\)", upper):
            found.append(_found(item, source, "STARTS_PROGRAM", "PROGRAM", match.group(1), line_no, line, confidence=0.80))
        for match in re.finditer(r"\bDEFINE\s+TRANSACTION\(([^)]+)\).*?\bPROGRAM\(([^)]+)\)", upper):
            tx = _asset(item.member.run_id, "TRANSACTION", match.group(1), confidence=0.80, validation_status="inferred")
            found.append(_found_existing(item, source, "STARTS_TRANSACTION", tx, line_no, line, confidence=0.80, validation_status="inferred"))
            found.append(_found(item, tx, "STARTS_PROGRAM", "PROGRAM", match.group(2), line_no, line, confidence=0.80, validation_status="inferred"))
    return found


def _scheduler_relationships(item: ClassifiedMember, source: Asset) -> list[FoundRelationship]:
    found: list[FoundRelationship] = []
    for line_no, line in enumerate(item.lines, 1):
        upper = line.upper()
        for match in re.finditer(r"\b(?:JOB|RUN)\s+([A-Z0-9#$@_-]+)", upper):
            found.append(_found(item, source, "TRIGGERS", "JOB", match.group(1), line_no, line, confidence=0.80))
    return found


def _found(
    item: ClassifiedMember,
    source: Asset,
    relationship_type: str,
    target_type: str,
    target_name: str,
    line_no: int,
    line: str,
    *,
    confidence: float = 1.0,
    validation_status: str = "confirmed",
    discovery_method: str = "observed",
    attributes: dict[str, Any] | None = None,
) -> FoundRelationship:
    target = _asset(
        item.member.run_id,
        target_type,
        target_name,
        confidence=confidence,
        validation_status=validation_status,
        discovery_method=discovery_method,
    )
    return _found_existing(
        item,
        source,
        relationship_type,
        target,
        line_no,
        line,
        confidence=confidence,
        validation_status=validation_status,
        discovery_method=discovery_method,
        attributes=attributes,
    )


def _found_existing(
    item: ClassifiedMember,
    source: Asset,
    relationship_type: str,
    target: Asset,
    line_no: int,
    line: str,
    *,
    confidence: float = 1.0,
    validation_status: str = "confirmed",
    discovery_method: str = "observed",
    attributes: dict[str, Any] | None = None,
) -> FoundRelationship:
    return FoundRelationship(
        relationship_type=relationship_type,
        source_asset_id=source.asset_id,
        target=target,
        evidence=Evidence(
            source_path=item.member.relative_path,
            line_start=line_no,
            line_end=line_no,
            evidence_text=line.strip()[:500],
            extractor=EXTRACTOR,
            discovery_method=discovery_method,
            confidence=confidence,
            validation_status=validation_status,
        ),
        confidence=confidence,
        validation_status=validation_status,
        discovery_method=discovery_method,
        attributes=attributes,
    )


def _asset(
    run_id: str,
    asset_type: str,
    technical_name: str,
    *,
    confidence: float,
    validation_status: str,
    discovery_method: str = "observed",
) -> Asset:
    name = _clean_name(technical_name)
    return Asset(
        run_id=run_id,
        asset_type=asset_type,
        technical_name=name,
        display_name=name,
        confidence=confidence,
        validation_status=validation_status,
        discovery_method=discovery_method,
        attributes={"reference_only": True},
    )


def _clean_name(value: str) -> str:
    return value.strip().strip("'\"()[],.").upper()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="python -m mip_intel.ingestion")
    parser.add_argument("source_root")
    parser.add_argument("--db", default="data/mip-intel.db")
    parser.add_argument("--run-id")
    parser.add_argument("--config", default="{}")
    args = parser.parse_args(argv)
    print(
        json.dumps(
            scan_mainframe_tree(
                args.source_root,
                args.db,
                run_id=args.run_id,
                config=json.loads(args.config),
            ),
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
