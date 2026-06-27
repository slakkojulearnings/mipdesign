from __future__ import annotations

import argparse
from concurrent.futures import ProcessPoolExecutor, ThreadPoolExecutor, as_completed
import hashlib
import json
import multiprocessing as mp
import os
import re
import time
import tracemalloc
from dataclasses import dataclass, replace
from pathlib import Path
from typing import Any

from .cobol_antlr import cobol_ast
from .graph_service import GraphService
from .models import Asset, Evidence, Relationship, SourceMember, now_iso, stable_id
from .reference_parser import PARSER_VERSION, ast_tree, copybook_resolver, parse_cobol
from .repositories import SQLiteGraphRepository


EXTRACTOR = "mainframe_scanner_v1"
TEXT_LIMIT_BYTES = 4_000_000
FIELD_FLOW_LIMIT = 500  # max field-lineage flows persisted per program (truncation flagged)
COPYBOOK_SITE_FIELD_LIMIT = 128
DATA_DICTIONARY_GRAPH_LIMIT = 256
DEFAULT_EXCLUDED_DIRS = (".git",)

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
    (("pli",), "PLI"),
    (("pl1",), "PLI"),
    (("asm",), "ASSEMBLER"),
    (("assembler",), "ASSEMBLER"),
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
    "DCLGEN": "DCLGEN",
    "IMS": "IMS_RESOURCE",
    "MQ": "MQ_QUEUE",
    "PLI": "PROGRAM",
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
    source_asset: Asset | None = None


@dataclass(frozen=True)
class ScanConfig:
    run_id: str | None = None
    resume: bool = False
    incremental: bool = False
    collect_telemetry: bool = True
    batch_size: int = 500
    max_workers: int = 1
    parse_timeout_seconds: float = 0.0
    fail_fast: bool = False
    exclude_dirs: tuple[str, ...] = DEFAULT_EXCLUDED_DIRS
    copybook_dirs: tuple[str, ...] = ()

    @classmethod
    def from_dict(cls, config: dict[str, Any] | None, run_id: str | None = None) -> "ScanConfig":
        config = config or {}
        return cls(
            run_id=str(config.get("run_id") or run_id) if config.get("run_id") or run_id else None,
            resume=bool(config.get("resume", False)),
            incremental=bool(config.get("incremental", False)),
            collect_telemetry=bool(config.get("collect_telemetry", True)),
            batch_size=min(max(int(config.get("batch_size", 500)), 1), 10_000),
            max_workers=min(max(int(config.get("max_workers", 1)), 1), 32),
            parse_timeout_seconds=max(float(config.get("parse_timeout_seconds", 0.0)), 0.0),
            fail_fast=bool(config.get("fail_fast", False)),
            exclude_dirs=_normalize_excluded_dirs(config.get("exclude_dirs", DEFAULT_EXCLUDED_DIRS)),
            copybook_dirs=_normalize_path_list(config.get("copybook_dirs", ())),
        )

    def as_dict(self) -> dict[str, Any]:
        return {
            "run_id": self.run_id,
            "resume": self.resume,
            "incremental": self.incremental,
            "collect_telemetry": self.collect_telemetry,
            "batch_size": self.batch_size,
            "max_workers": self.max_workers,
            "parse_timeout_seconds": self.parse_timeout_seconds,
            "fail_fast": self.fail_fast,
            "exclude_dirs": list(self.exclude_dirs),
            "copybook_dirs": list(self.copybook_dirs),
        }


def _normalize_excluded_dirs(value: Any) -> tuple[str, ...]:
    if value is None:
        return DEFAULT_EXCLUDED_DIRS
    if isinstance(value, str):
        raw_items = re.split(r"[,\s]+", value)
    else:
        raw_items = [str(item) for item in value]
    names = {item.strip().strip("/\\") for item in raw_items if item and item.strip()}
    names.add(".git")
    return tuple(sorted(names))


def _normalize_path_list(value: Any) -> tuple[str, ...]:
    if value is None:
        return ()
    if isinstance(value, str):
        raw_items = re.split(r"[,;]+", value)
    else:
        raw_items = [str(item) for item in value]
    return tuple(item.strip().strip("/\\").replace("\\", "/") for item in raw_items if item and item.strip())


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
    scan_started = time.perf_counter()
    if scan_config.collect_telemetry and not tracemalloc.is_tracing():
        tracemalloc.start()
    root = Path(source_root)
    selected_run_id = repository.create_run(
        str(root),
        run_id=scan_config.run_id,
        config=scan_config.as_dict(),
        resume=scan_config.resume,
    )
    corrections = _corrections_by_kind(repository.list_corrections(selected_run_id))
    repository.upsert_scan_progress(
        selected_run_id, "DISCOVERING", details={"source_root": str(root), "config": scan_config.as_dict()}
    )
    phase_started = time.perf_counter()
    paths, discovery_feedback = _iter_files(root, scan_config.exclude_dirs)
    _record_phase_telemetry(
        repository,
        selected_run_id,
        "DISCOVERING",
        phase_started,
        scan_config,
        {"source_root": str(root), **discovery_feedback},
    )
    repository.upsert_scan_progress(
        selected_run_id,
        "DISCOVERING",
        total_files=len(paths),
        processed_files=len(paths),
        details={"source_root": str(root), **discovery_feedback},
    )
    phase_started = time.perf_counter()
    members, scan_issues = _classify_members(
        paths,
        root,
        selected_run_id,
        repository,
        scan_config,
        corrections.get("MEMBER", []),
    )
    _record_phase_telemetry(
        repository,
        selected_run_id,
        "CLASSIFYING",
        phase_started,
        scan_config,
        {"member_count": len(members), "issue_count": len(scan_issues)},
    )
    referenced_copies = _referenced_copy_names(members)
    members = _promote_referenced_copybooks(members, referenced_copies)
    copybooks, copybook_metadata = _copybook_index(
        members,
        referenced_copies,
        copybook_dirs=scan_config.copybook_dirs,
    )
    resolver_fingerprint = _copybook_fingerprint(copybooks, copybook_metadata)
    resolver = copybook_resolver(copybooks, copybook_metadata)
    parse_items = [
        item
        for item in members
        if item.member.artifact_type == "COBOL" and item.text
    ]
    repository.upsert_scan_progress(
        selected_run_id,
        "PARSING",
        total_files=len(members),
        processed_files=0,
        parsed_files=0,
        details={"parse_candidates": len(parse_items), "resolver_fingerprint": resolver_fingerprint},
    )
    phase_started = time.perf_counter()
    cobol_analysis, parse_metrics, parse_issues = _parse_members(
        repository,
        parse_items,
        resolver=resolver,
        resolver_fingerprint=resolver_fingerprint,
        config=scan_config,
    )
    _update_parse_file_telemetry(repository, parse_items, cobol_analysis)
    _record_phase_telemetry(
        repository,
        selected_run_id,
        "PARSING",
        phase_started,
        scan_config,
        {"parse_candidates": len(parse_items), **parse_metrics},
    )
    scan_issues.extend(parse_issues)

    assets: dict[str, Asset] = {}
    member_assets: dict[str, Asset] = {}
    relationships: list[FoundRelationship] = []
    warnings: list[dict[str, Any]] = []

    for item in members:
        asset = _asset_for_member(item, cobol_analysis.get(item.member.member_id))
        asset = _apply_asset_corrections(asset, corrections.get("ASSET", []))
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
    phase_started = time.perf_counter()
    for item in members:
        source = member_assets[item.member.member_id]
        graph_started = time.perf_counter()
        for rel in _relationships_for_member(item, source, cobol_analysis.get(item.member.member_id)):
            if rel.source_asset is not None:
                assets.setdefault(rel.source_asset.asset_id, rel.source_asset)
            assets.setdefault(rel.target.asset_id, rel.target)
            relationships.append(rel)
        _update_graph_file_telemetry(repository, item, graph_started)
    for rel in _cross_member_relationships(members, member_assets, cobol_analysis, copybook_metadata):
        if rel.source_asset is not None:
            assets.setdefault(rel.source_asset.asset_id, rel.source_asset)
        assets.setdefault(rel.target.asset_id, rel.target)
        relationships.append(rel)
    relationships = _apply_relationship_corrections(relationships, assets, corrections.get("RELATIONSHIP", []))
    for rel in relationships:
        if rel.source_asset is not None:
            assets.setdefault(rel.source_asset.asset_id, rel.source_asset)
        assets.setdefault(rel.target.asset_id, rel.target)
    _record_phase_telemetry(
        repository,
        selected_run_id,
        "BUILDING_GRAPH",
        phase_started,
        scan_config,
        {"asset_count": len(assets), "relationship_count": len(relationships)},
    )

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
    phase_started = time.perf_counter()
    _persist_graph(repository, selected_run_id, members, assets, relationships)
    _record_phase_telemetry(
        repository,
        selected_run_id,
        "PERSISTING",
        phase_started,
        scan_config,
        {"asset_count": len(assets), "relationship_count": len(relationships)},
    )
    phase_started = time.perf_counter()
    validation_feedback = _scan_validation_snapshot(repository, selected_run_id)
    _record_phase_telemetry(repository, selected_run_id, "VALIDATING", phase_started, scan_config, validation_feedback)
    repository.upsert_scan_progress(
        selected_run_id,
        "VALIDATING",
        total_files=len(members),
        processed_files=len(members),
        parsed_files=parse_metrics["parsed_files"],
        cached_parse_hits=parse_metrics["cached_parse_hits"],
        failed_files=parse_metrics["failed_files"],
        details=validation_feedback,
    )

    repository.upsert_scan_progress(
        selected_run_id,
        "SUMMARIZING",
        total_files=len(members),
        processed_files=len(members),
        parsed_files=parse_metrics["parsed_files"],
        cached_parse_hits=parse_metrics["cached_parse_hits"],
        failed_files=parse_metrics["failed_files"],
    )
    phase_started = time.perf_counter()
    GraphService(repository).recompute_summaries(selected_run_id)
    insight_count = write_deterministic_insights(repository, selected_run_id, warnings)
    _record_phase_telemetry(
        repository,
        selected_run_id,
        "SUMMARIZING",
        phase_started,
        scan_config,
        {"insight_count": insight_count},
    )
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
        details={
            "status": "COMPLETED",
            "issue_count": len(scan_issues),
            "validation": validation_feedback,
            "elapsed_ms": round((time.perf_counter() - scan_started) * 1000, 3),
        },
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
        "validation_feedback": validation_feedback,
        "issue_count": len(scan_issues),
        "warnings": warnings,
    }


def _classify_members(
    paths: list[Path],
    root: Path,
    run_id: str,
    repository: SQLiteGraphRepository,
    config: ScanConfig,
    corrections: list[dict[str, Any]] | None = None,
) -> tuple[list[ClassifiedMember], list[dict[str, Any]]]:
    members: list[ClassifiedMember] = []
    issues: list[dict[str, Any]] = []
    total = len(paths)
    source_root = str(root)
    correction_rows = corrections or []
    for index, path in enumerate(paths, 1):
        started = time.perf_counter()
        try:
            item, reused = _classify_path(path, root, run_id, repository, config, source_root)
            item = _apply_member_corrections(item, correction_rows)
            members.append(item)
            classify_ms = (time.perf_counter() - started) * 1000
            repository.upsert_file_telemetry(
                run_id,
                item.member.relative_path,
                sha256=item.member.sha256,
                size_bytes=item.member.size_bytes,
                artifact_type=item.member.artifact_type,
                classification_basis=item.member.classification_basis,
                validation_status=item.member.validation_status,
                classify_ms=classify_ms,
                total_ms=classify_ms,
                reused_classification=reused,
                details={"encoding": item.member.encoding, "text_status": item.member.text_status},
            )
            if config.incremental:
                repository.put_file_inventory_cache(source_root, item.member)
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


def _record_phase_telemetry(
    repository: SQLiteGraphRepository,
    run_id: str,
    phase: str,
    started: float,
    config: ScanConfig,
    details: dict[str, Any] | None = None,
) -> None:
    if not config.collect_telemetry:
        return
    repository.insert_phase_telemetry(
        run_id,
        phase,
        elapsed_ms=(time.perf_counter() - started) * 1000,
        memory_peak_bytes=_memory_peak_bytes(),
        details=details or {},
    )


def _memory_peak_bytes() -> int:
    if not tracemalloc.is_tracing():
        return 0
    return int(tracemalloc.get_traced_memory()[1])


def _corrections_by_kind(corrections: list[dict[str, Any]]) -> dict[str, list[dict[str, Any]]]:
    grouped: dict[str, list[dict[str, Any]]] = {}
    for row in corrections:
        grouped.setdefault(str(row.get("entity_kind") or "").upper(), []).append(row)
    return grouped


def _apply_member_corrections(
    item: ClassifiedMember,
    corrections: list[dict[str, Any]],
) -> ClassifiedMember:
    selected = _matching_correction(corrections, item.member.relative_path, item.member.member_name)
    if not selected:
        return item
    action = str(selected.get("action") or "").upper()
    if action not in {"OVERRIDE_TYPE", "OVERRIDE", "CLASSIFY_AS"}:
        return item
    corrected_type = selected.get("corrected_type")
    if not corrected_type:
        return item
    confidence = float(selected.get("corrected_confidence") or 0.97)
    status = str(selected.get("corrected_status") or "confirmed")
    member = replace(
        item.member,
        artifact_type=str(corrected_type).upper(),
        classification_basis=f"correction:{selected['correction_id']}",
        confidence=confidence,
        validation_status=status,
    )
    return replace(item, member=member)


def _apply_asset_corrections(asset: Asset, corrections: list[dict[str, Any]]) -> Asset:
    selected = _matching_correction(corrections, asset.asset_id, asset.technical_name)
    if not selected:
        return asset
    action = str(selected.get("action") or "").upper()
    attrs = {**asset.attributes, "correction_id": selected["correction_id"], "correction_action": action}
    corrected_type = str(selected.get("corrected_type") or asset.asset_type).upper()
    corrected_name = str(selected.get("corrected_name") or asset.technical_name).upper()
    status = str(selected.get("corrected_status") or asset.validation_status)
    confidence = float(selected.get("corrected_confidence") or asset.confidence)
    if action in {"OVERRIDE", "OVERRIDE_TYPE", "RENAME"}:
        return replace(
            asset,
            asset_type=corrected_type,
            technical_name=corrected_name,
            display_name=corrected_name,
            confidence=confidence,
            validation_status=status,
            discovery_method="corrected",
            attributes=attrs,
        )
    return asset


def _apply_relationship_corrections(
    relationships: list[FoundRelationship],
    assets: dict[str, Asset],
    corrections: list[dict[str, Any]],
) -> list[FoundRelationship]:
    if not corrections:
        return relationships
    corrected: list[FoundRelationship] = []
    for rel in relationships:
        source = assets.get(rel.source_asset_id) or rel.source_asset
        source_name = source.technical_name if source else rel.source_asset_id
        selectors = {
            rel.relationship_type,
            f"{source_name}|{rel.relationship_type}|{rel.target.technical_name}",
            f"{source_name}->{rel.relationship_type}->{rel.target.technical_name}",
            f"{rel.source_asset_id}|{rel.relationship_type}|{rel.target.asset_id}",
        }
        selected = next(
            (
                row for row in corrections
                if str(row.get("selector") or "").upper() in {value.upper() for value in selectors}
            ),
            None,
        )
        if not selected:
            corrected.append(rel)
            continue
        action = str(selected.get("action") or "").upper()
        if action == "SUPPRESS":
            continue
        attrs = {
            **(rel.attributes or {}),
            "correction_id": selected["correction_id"],
            "correction_action": action,
        }
        relationship_type = str(selected.get("corrected_type") or rel.relationship_type).upper()
        target = rel.target
        if selected.get("corrected_name"):
            corrected_name = str(selected["corrected_name"]).upper()
            target = replace(target, technical_name=corrected_name, display_name=corrected_name)
        corrected.append(
            replace(
                rel,
                relationship_type=relationship_type,
                target=target,
                confidence=float(selected.get("corrected_confidence") or rel.confidence),
                validation_status=str(selected.get("corrected_status") or rel.validation_status),
                discovery_method="corrected",
                attributes=attrs,
            )
        )
    return corrected


def _matching_correction(
    corrections: list[dict[str, Any]],
    *selectors: str | None,
) -> dict[str, Any] | None:
    wanted = {str(item).upper() for item in selectors if item}
    for row in corrections:
        if str(row.get("selector") or "").upper() in wanted:
            return row
    return None


def _update_parse_file_telemetry(
    repository: SQLiteGraphRepository,
    parse_items: list[ClassifiedMember],
    analysis: dict[str, dict[str, Any]],
) -> None:
    for item in parse_items:
        payload = analysis.get(item.member.member_id) or {}
        parser = payload.get("parser", {}) or {}
        parse_ms = float(parser.get("elapsed_ms") or 0.0)
        repository.upsert_file_telemetry(
            item.member.run_id,
            item.member.relative_path,
            sha256=item.member.sha256,
            size_bytes=item.member.size_bytes,
            artifact_type=item.member.artifact_type,
            classification_basis=item.member.classification_basis,
            validation_status=item.member.validation_status,
            parse_ms=parse_ms,
            total_ms=parse_ms,
            parse_cache_hit=bool(parser.get("cache_hit")),
            details={"parser": parser},
        )


def _update_graph_file_telemetry(
    repository: SQLiteGraphRepository,
    item: ClassifiedMember,
    started: float,
) -> None:
    graph_ms = (time.perf_counter() - started) * 1000
    repository.upsert_file_telemetry(
        item.member.run_id,
        item.member.relative_path,
        sha256=item.member.sha256,
        size_bytes=item.member.size_bytes,
        artifact_type=item.member.artifact_type,
        classification_basis=item.member.classification_basis,
        validation_status=item.member.validation_status,
        graph_ms=graph_ms,
        total_ms=graph_ms,
    )


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
        pending: list[tuple[ClassifiedMember, str]] = []
        processed = 0
        for item in items:
            cache_key = _parse_cache_key(item, resolver_fingerprint)
            cached = repository.get_cached_parse(cache_key)
            if cached:
                payload = json.loads(json.dumps(cached))
                parser = dict(payload.get("parser", {}))
                parser["cache_hit"] = True
                payload["parser"] = parser
                _record_parse_result(analysis, issues, metrics, item, payload, None, config)
                processed += 1
            else:
                pending.append((item, cache_key))
        if processed:
            _update_parse_progress(repository, items[0].member.run_id, total, processed, metrics, config)

        executor_class = ThreadPoolExecutor if config.parse_timeout_seconds else ProcessPoolExecutor
        with executor_class(max_workers=config.max_workers) as executor:
            futures = {
                executor.submit(
                    _parse_cobol_hard_timeout_worker if config.parse_timeout_seconds else _parse_cobol_worker,
                    item.text,
                    resolver,
                    config.parse_timeout_seconds,
                ): (item, cache_key)
                for item, cache_key in pending
            }
            for index, future in enumerate(as_completed(futures), 1):
                item, cache_key = futures[future]
                try:
                    payload, issue_stub = future.result()
                except Exception as exc:
                    payload = _parse_error_payload(item.text, exc)
                    issue_stub = {
                        "severity": "ERROR",
                        "error_type": type(exc).__name__,
                        "message": str(exc),
                        "details": {"parallel_worker": True},
                    }
                issue = None
                if issue_stub:
                    issue = _record_scan_issue(
                        repository,
                        item.member.run_id,
                        item.member.relative_path,
                        stage="PARSE",
                        severity=issue_stub["severity"],
                        error_type=issue_stub["error_type"],
                        message=issue_stub["message"],
                        details=issue_stub.get("details"),
                    )
                if not issue_stub:
                    repository.put_cached_parse(
                        cache_key=cache_key,
                        source_sha256=item.member.sha256,
                        resolver_fingerprint=resolver_fingerprint,
                        parser_version=PARSER_VERSION,
                        payload=payload,
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
                processed += 1
                if processed % config.batch_size == 0 or processed == total:
                    _update_parse_progress(repository, item.member.run_id, total, processed, metrics, config)
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
    asset_evidence: dict[str, list[Evidence]] = {}
    for rel in relationships:
        if rel.source_asset is not None and len(asset_evidence.get(rel.source_asset.asset_id, [])) < 3:
            asset_evidence.setdefault(rel.source_asset.asset_id, []).append(
                Evidence(
                    source_path=rel.evidence.source_path,
                    line_start=rel.evidence.line_start,
                    line_end=rel.evidence.line_end,
                    evidence_text=f"{rel.relationship_type} source: {rel.evidence.evidence_text}"[:500],
                    extractor=EXTRACTOR,
                    discovery_method=rel.discovery_method,
                    confidence=rel.confidence,
                    validation_status=rel.validation_status,
                )
            )
        if len(asset_evidence.get(rel.target.asset_id, [])) >= 3:
            continue
        asset_evidence.setdefault(rel.target.asset_id, []).append(
            Evidence(
                source_path=rel.evidence.source_path,
                line_start=rel.evidence.line_start,
                line_end=rel.evidence.line_end,
                evidence_text=f"{rel.relationship_type} target: {rel.evidence.evidence_text}"[:500],
                extractor=EXTRACTOR,
                discovery_method=rel.discovery_method,
                confidence=rel.confidence,
                validation_status=rel.validation_status,
            )
        )
    with repository.connect() as conn:
        _upsert_members(conn, [item.member for item in members])
        ordered_assets = sorted(assets.values(), key=lambda value: (value.asset_type, value.technical_name))
        asset_evidence_rows: list[tuple[Asset, list[Evidence]]] = []
        for asset in ordered_assets:
            evidence = list(asset_evidence.get(asset.asset_id, []))
            if asset.member_id:
                evidence.insert(
                    0,
                    Evidence(
                        source_path=asset.attributes.get("relative_path", asset.technical_name),
                        evidence_text=asset.attributes.get("classification_basis", ""),
                        extractor=EXTRACTOR,
                        discovery_method=asset.discovery_method,
                        confidence=asset.confidence,
                        validation_status=asset.validation_status,
                    ),
                )
            asset_evidence_rows.append((asset, evidence))
        _upsert_assets(conn, ordered_assets)
        _insert_evidence_batch(
            conn,
            [
                (asset.run_id, "ASSET", asset.asset_id, item)
                for asset, evidence in asset_evidence_rows
                for item in evidence
            ],
        )
        relationship_rows: list[tuple[Relationship, list[Evidence]]] = []
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
            relationship_rows.append((relationship, [rel.evidence]))
        _insert_relationships(conn, [relationship for relationship, _ in relationship_rows])
        _insert_evidence_batch(
            conn,
            [
                (relationship.run_id, "RELATIONSHIP", relationship.relationship_id, item)
                for relationship, evidence in relationship_rows
                for item in evidence
            ],
        )


def _upsert_member(conn, member: SourceMember) -> None:
    conn.execute(
        """
        INSERT INTO source_member(
            member_id, run_id, relative_path, folder_path, member_name, sha256,
            size_bytes, encoding, is_binary, text_status, artifact_type,
            classification_basis, confidence, validation_status, discovered_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(member_id) DO UPDATE SET
            relative_path = excluded.relative_path,
            folder_path = excluded.folder_path,
            member_name = excluded.member_name,
            sha256 = excluded.sha256,
            size_bytes = excluded.size_bytes,
            encoding = excluded.encoding,
            is_binary = excluded.is_binary,
            text_status = excluded.text_status,
            artifact_type = excluded.artifact_type,
            classification_basis = excluded.classification_basis,
            confidence = excluded.confidence,
            validation_status = excluded.validation_status,
            discovered_at = excluded.discovered_at
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


def _upsert_members(conn, members: list[SourceMember]) -> None:
    if not members:
        return
    conn.executemany(
        """
        INSERT INTO source_member(
            member_id, run_id, relative_path, folder_path, member_name, sha256,
            size_bytes, encoding, is_binary, text_status, artifact_type,
            classification_basis, confidence, validation_status, discovered_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(member_id) DO UPDATE SET
            relative_path = excluded.relative_path,
            folder_path = excluded.folder_path,
            member_name = excluded.member_name,
            sha256 = excluded.sha256,
            size_bytes = excluded.size_bytes,
            encoding = excluded.encoding,
            is_binary = excluded.is_binary,
            text_status = excluded.text_status,
            artifact_type = excluded.artifact_type,
            classification_basis = excluded.classification_basis,
            confidence = excluded.confidence,
            validation_status = excluded.validation_status,
            discovered_at = excluded.discovered_at
        """,
        [
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
            )
            for member in members
        ],
    )


def _upsert_asset(
    conn,
    repository: SQLiteGraphRepository,
    asset: Asset,
    evidence: list[Evidence],
) -> None:
    conn.execute(
        """
        INSERT INTO asset(
            asset_id, run_id, asset_type, technical_name, display_name, member_id,
            folder_path, confidence, validation_status, discovery_method,
            attributes_json, origin, enriched_by_member, created_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(asset_id) DO UPDATE SET
            asset_type = excluded.asset_type,
            technical_name = excluded.technical_name,
            display_name = excluded.display_name,
            member_id = excluded.member_id,
            folder_path = excluded.folder_path,
            confidence = excluded.confidence,
            validation_status = excluded.validation_status,
            discovery_method = excluded.discovery_method,
            attributes_json = excluded.attributes_json,
            origin = excluded.origin,
            enriched_by_member = excluded.enriched_by_member,
            created_at = excluded.created_at
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
            asset.origin,
            asset.enriched_by_member,
            asset.created_at,
        ),
    )
    for item in evidence:
        repository._insert_evidence(conn, asset.run_id, "ASSET", asset.asset_id, item)


def _upsert_assets(conn, assets: list[Asset]) -> None:
    if not assets:
        return
    conn.executemany(
        """
        INSERT INTO asset(
            asset_id, run_id, asset_type, technical_name, display_name, member_id,
            folder_path, confidence, validation_status, discovery_method,
            attributes_json, origin, enriched_by_member, created_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(asset_id) DO UPDATE SET
            asset_type = excluded.asset_type,
            technical_name = excluded.technical_name,
            display_name = excluded.display_name,
            member_id = excluded.member_id,
            folder_path = excluded.folder_path,
            confidence = excluded.confidence,
            validation_status = excluded.validation_status,
            discovery_method = excluded.discovery_method,
            attributes_json = excluded.attributes_json,
            origin = excluded.origin,
            enriched_by_member = excluded.enriched_by_member,
            created_at = excluded.created_at
        """,
        [
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
                asset.origin,
                asset.enriched_by_member,
                asset.created_at,
            )
            for asset in assets
        ],
    )


def _insert_relationship(
    conn,
    repository: SQLiteGraphRepository,
    relationship: Relationship,
    evidence: list[Evidence],
) -> None:
    conn.execute(
        """
        INSERT INTO relationship(
            relationship_id, run_id, relationship_type, source_asset_id,
            target_asset_id, confidence, validation_status, discovery_method,
            attributes_json, origin, enriched_by_member, created_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(relationship_id) DO UPDATE SET
            relationship_type = excluded.relationship_type,
            source_asset_id = excluded.source_asset_id,
            target_asset_id = excluded.target_asset_id,
            confidence = excluded.confidence,
            validation_status = excluded.validation_status,
            discovery_method = excluded.discovery_method,
            attributes_json = excluded.attributes_json,
            origin = excluded.origin,
            enriched_by_member = excluded.enriched_by_member,
            created_at = excluded.created_at
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
            relationship.origin,
            relationship.enriched_by_member,
            relationship.created_at,
        ),
    )
    for item in evidence:
        repository._insert_evidence(
            conn, relationship.run_id, "RELATIONSHIP", relationship.relationship_id, item
        )


def _insert_relationships(conn, relationships: list[Relationship]) -> None:
    if not relationships:
        return
    conn.executemany(
        """
        INSERT INTO relationship(
            relationship_id, run_id, relationship_type, source_asset_id,
            target_asset_id, confidence, validation_status, discovery_method,
            attributes_json, origin, enriched_by_member, created_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(relationship_id) DO UPDATE SET
            relationship_type = excluded.relationship_type,
            source_asset_id = excluded.source_asset_id,
            target_asset_id = excluded.target_asset_id,
            confidence = excluded.confidence,
            validation_status = excluded.validation_status,
            discovery_method = excluded.discovery_method,
            attributes_json = excluded.attributes_json,
            origin = excluded.origin,
            enriched_by_member = excluded.enriched_by_member,
            created_at = excluded.created_at
        """,
        [
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
                relationship.origin,
                relationship.enriched_by_member,
                relationship.created_at,
            )
            for relationship in relationships
        ],
    )


def _insert_evidence_batch(conn, rows: list[tuple[str, str, str, Evidence]]) -> None:
    if not rows:
        return
    created_at = now_iso()
    conn.executemany(
        """
        INSERT OR REPLACE INTO evidence(
            evidence_id, run_id, entity_kind, entity_id, source_path, line_start,
            line_end, evidence_text, extractor, discovery_method, confidence,
            validation_status, created_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        [
            (
                stable_id(
                    run_id,
                    "evidence",
                    entity_kind,
                    entity_id,
                    evidence.source_path,
                    evidence.line_start,
                    evidence.evidence_text,
                ),
                run_id,
                entity_kind,
                entity_id,
                evidence.source_path,
                evidence.line_start,
                evidence.line_end,
                evidence.evidence_text,
                evidence.extractor,
                evidence.discovery_method,
                evidence.confidence,
                evidence.validation_status,
                created_at,
            )
            for run_id, entity_kind, entity_id, evidence in rows
        ],
    )


def _scan_validation_snapshot(repository: SQLiteGraphRepository, run_id: str) -> dict[str, Any]:
    with repository.connect() as conn:
        row = conn.execute(
            """
            SELECT
                (SELECT COUNT(*) FROM asset a
                 WHERE a.run_id = ? AND NOT EXISTS (
                    SELECT 1 FROM evidence e
                    WHERE e.run_id = a.run_id AND e.entity_kind = 'ASSET'
                      AND e.entity_id = a.asset_id
                 )) AS nodes_without_evidence,
                (SELECT COUNT(*) FROM relationship r
                 WHERE r.run_id = ? AND NOT EXISTS (
                    SELECT 1 FROM evidence e
                    WHERE e.run_id = r.run_id AND e.entity_kind = 'RELATIONSHIP'
                      AND e.entity_id = r.relationship_id
                 )) AS edges_without_evidence,
                (SELECT COUNT(*) FROM asset
                 WHERE run_id = ? AND (confidence < 0 OR confidence > 1)) AS invalid_node_confidence,
                (SELECT COUNT(*) FROM relationship
                 WHERE run_id = ? AND (confidence < 0 OR confidence > 1)) AS invalid_edge_confidence,
                (SELECT COUNT(*) FROM asset
                 WHERE run_id = ? AND validation_status <> 'confirmed') AS review_node_count,
                (SELECT COUNT(*) FROM relationship
                 WHERE run_id = ? AND validation_status <> 'confirmed') AS review_edge_count
            """,
            (run_id, run_id, run_id, run_id, run_id, run_id),
        ).fetchone()
    feedback = dict(row)
    feedback["status"] = "passed" if not any(
        feedback[key]
        for key in (
            "nodes_without_evidence",
            "edges_without_evidence",
            "invalid_node_confidence",
            "invalid_edge_confidence",
        )
    ) else "needs_review"
    return feedback


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


def _iter_files(root: Path, exclude_dirs: tuple[str, ...] = DEFAULT_EXCLUDED_DIRS) -> tuple[list[Path], dict[str, Any]]:
    if not root.exists():
        raise FileNotFoundError(root)
    excluded = {name.lower() for name in exclude_dirs}
    paths: list[Path] = []
    skipped_dirs: list[str] = []
    for current, dirs, files in os.walk(root):
        current_path = Path(current)
        kept_dirs = []
        for directory in dirs:
            if directory.lower() in excluded:
                try:
                    skipped_dirs.append((current_path / directory).relative_to(root).as_posix())
                except ValueError:
                    skipped_dirs.append(str(current_path / directory))
                continue
            kept_dirs.append(directory)
        dirs[:] = kept_dirs
        for filename in files:
            paths.append(current_path / filename)
    feedback = {
        "excluded_dirs": sorted(excluded),
        "skipped_directory_count": len(skipped_dirs),
        "skipped_directories": skipped_dirs[:50],
    }
    return sorted(paths), feedback


def _classify_path(
    path: Path,
    root: Path,
    run_id: str,
    repository: SQLiteGraphRepository | None = None,
    config: ScanConfig | None = None,
    source_root: str | None = None,
) -> tuple[ClassifiedMember, bool]:
    data = path.read_bytes()
    relative = path.relative_to(root).as_posix()
    folder = path.parent.relative_to(root).as_posix()
    payload = _read_text(data)
    sha256 = hashlib.sha256(data).hexdigest()
    cached = None
    if repository is not None and config is not None and config.incremental:
        cached = repository.get_file_inventory_cache(source_root or str(root), relative, sha256)
    if cached:
        artifact_type = str(cached["artifact_type"])
        basis = f"inventory-cache:{cached['classification_basis']}"
        confidence = float(cached["confidence"])
        status = str(cached["validation_status"])
    else:
        artifact_type, basis, confidence, status = _classify(relative, payload)
    member = SourceMember(
        run_id=run_id,
        relative_path=relative,
        folder_path="" if folder == "." else folder,
        member_name=path.name,
        sha256=sha256,
        size_bytes=len(data),
        encoding=payload.encoding,
        is_binary=payload.is_binary,
        text_status=payload.text_status,
        artifact_type=artifact_type,
        classification_basis=basis,
        confidence=confidence,
        validation_status=status,
    )
    return ClassifiedMember(member=member, text=payload.text, lines=tuple(payload.text.splitlines())), bool(cached)


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
        ("DCLGEN", "content:DECLARE TABLE", 0.90, r"\bDECLARE\s+(?:TABLE\s+[A-Z0-9_.$#@]+|[A-Z0-9_.$#@]+\s+TABLE)\b"),
        ("BMS_MAP", "content:BMS macros", 0.90, r"\bDFH(MSD|MDI|MDF)\b"),
        ("MQ", "content:MQ definitions", 0.80, r"\b(DEFINE\s+QLOCAL|MQPUT|MQGET|MQOPEN)\b"),
        ("IMS", "content:IMS definitions", 0.80, r"\b(PSBGEN|DBDGEN|PCB\s+TYPE=|SEGM\s+NAME=)\b"),
        ("PLI", "content:PL/I PROC", 0.82, r"(?m)^\s*[A-Z0-9#$@_-]+\s*:?\s*PROC\b"),
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
    members: list[ClassifiedMember],
    referenced_copies: set[str],
    *,
    copybook_dirs: tuple[str, ...] = (),
) -> tuple[dict[str, str], dict[str, dict[str, Any]]]:
    candidates: dict[str, list[dict[str, Any]]] = {}
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
            candidates.setdefault(name, []).append(
                {
                    "name": name,
                    "item": item,
                    "score": _copybook_candidate_score(item, copybook_dirs),
                }
            )
    copybooks: dict[str, str] = {}
    metadata: dict[str, dict[str, Any]] = {}
    for name, rows in candidates.items():
        selected = sorted(rows, key=lambda row: (-row["score"], row["item"].member.relative_path))[0]
        item = selected["item"]
        conflict_candidates = [
            {
                "source_path": row["item"].member.relative_path,
                "artifact_type": row["item"].member.artifact_type,
                "sha256": row["item"].member.sha256,
                "score": row["score"],
            }
            for row in sorted(rows, key=lambda row: (-row["score"], row["item"].member.relative_path))
        ]
        copybooks[name] = item.text
        metadata[name] = {
            "source_path": item.member.relative_path,
            "artifact_type": item.member.artifact_type,
            "classification_basis": item.member.classification_basis,
            "confidence": item.member.confidence,
            "validation_status": item.member.validation_status,
            "sha256": item.member.sha256,
            "copybook_search_order": list(copybook_dirs),
            "selected_by": "copybook_dirs" if copybook_dirs else "artifact_confidence_path_order",
            "candidate_count": len(rows),
            "conflict": len({row["item"].member.sha256 for row in rows}) > 1,
            "candidates": conflict_candidates[:25],
        }
    return copybooks, metadata


def _copybook_candidate_score(item: ClassifiedMember, copybook_dirs: tuple[str, ...]) -> float:
    score = float(item.member.confidence)
    if item.member.artifact_type == "COPYBOOK":
        score += 3.0
    elif item.member.artifact_type == "DCLGEN":
        score += 2.0
    for index, folder in enumerate(copybook_dirs):
        if _path_starts_with(item.member.relative_path, folder):
            score += 10.0 - min(index, 9)
            break
    return score


def _path_starts_with(relative_path: str, folder: str) -> bool:
    normalized = relative_path.replace("\\", "/").strip("/").lower()
    selected = folder.replace("\\", "/").strip("/").lower()
    return bool(selected) and (normalized == selected or normalized.startswith(f"{selected}/"))


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
    cache_key = _parse_cache_key(item, resolver_fingerprint)
    cached = repository.get_cached_parse(cache_key)
    if cached:
        payload = json.loads(json.dumps(cached))
        parser = dict(payload.get("parser", {}))
        parser["cache_hit"] = True
        payload["parser"] = parser
        return payload, None
    started = time.perf_counter()
    try:
        if soft_timeout_seconds:
            payload, issue_stub = _parse_cobol_hard_timeout_worker(item.text, resolver, soft_timeout_seconds)
            if issue_stub:
                issue = _record_scan_issue(
                    repository,
                    item.member.run_id,
                    item.member.relative_path,
                    stage="PARSE",
                    severity=issue_stub["severity"],
                    error_type=issue_stub["error_type"],
                    message=issue_stub["message"],
                    details=issue_stub.get("details"),
                )
                return payload, issue
        else:
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


def _parse_cache_key(item: ClassifiedMember, resolver_fingerprint: str) -> str:
    return stable_id("parse", item.member.sha256, resolver_fingerprint, PARSER_VERSION)


def _parse_cobol_worker(
    text: str,
    resolver,
    timeout_seconds: float = 0.0,
) -> tuple[dict[str, Any], dict[str, Any] | None]:
    del timeout_seconds
    started = time.perf_counter()
    try:
        payload = parse_cobol(text, resolver=resolver)
    except Exception as exc:
        return _parse_error_payload(text, exc), {
            "severity": "ERROR",
            "error_type": type(exc).__name__,
            "message": str(exc),
            "details": {"parser_version": PARSER_VERSION, "process_worker": True},
        }
    parser = dict(payload.get("parser", {}))
    parser["cache_hit"] = False
    parser["elapsed_ms"] = int((time.perf_counter() - started) * 1000)
    parser["parallel_backend"] = "process"
    payload["parser"] = parser
    return payload, None


def _parse_cobol_hard_timeout_worker(
    text: str,
    resolver,
    timeout_seconds: float,
) -> tuple[dict[str, Any], dict[str, Any] | None]:
    if timeout_seconds <= 0:
        return _parse_cobol_worker(text, resolver, timeout_seconds)
    queue: mp.Queue = mp.Queue(1)
    process = mp.Process(target=_parse_cobol_process_target, args=(queue, text, resolver))
    started = time.perf_counter()
    process.start()
    process.join(timeout_seconds)
    elapsed_ms = int((time.perf_counter() - started) * 1000)
    if process.is_alive():
        process.terminate()
        process.join(2)
        exc = TimeoutError(f"Parse exceeded hard timeout of {timeout_seconds}s")
        payload = _parse_error_payload(text, exc)
        parser = dict(payload.get("parser", {}))
        parser["hard_timeout_exceeded"] = True
        parser["elapsed_ms"] = elapsed_ms
        payload["parser"] = parser
        return payload, {
            "severity": "ERROR",
            "error_type": "HardParseTimeoutExceeded",
            "message": f"Parse exceeded hard timeout of {timeout_seconds}s",
            "details": {"elapsed_ms": elapsed_ms, "timeout_seconds": timeout_seconds},
        }
    if queue.empty():
        exc = RuntimeError("Parser process exited without a payload")
        return _parse_error_payload(text, exc), {
            "severity": "ERROR",
            "error_type": "ParserProcessNoPayload",
            "message": str(exc),
            "details": {"elapsed_ms": elapsed_ms},
        }
    status, payload_or_error = queue.get()
    if status == "ok":
        payload = payload_or_error
        parser = dict(payload.get("parser", {}))
        parser["cache_hit"] = False
        parser["elapsed_ms"] = elapsed_ms
        parser["parallel_backend"] = "hard-timeout-process"
        payload["parser"] = parser
        return payload, None
    exc_type, message = payload_or_error
    return _parse_error_payload(text, RuntimeError(message)), {
        "severity": "ERROR",
        "error_type": str(exc_type),
        "message": str(message),
        "details": {"elapsed_ms": elapsed_ms, "hard_timeout_process": True},
    }


def _parse_cobol_process_target(queue: mp.Queue, text: str, resolver) -> None:
    try:
        queue.put(("ok", parse_cobol(text, resolver=resolver)))
    except Exception as exc:
        queue.put(("error", (type(exc).__name__, str(exc))))


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
        field_flows = analysis.get("field_flows", []) or []
        attributes.update(
            {
                "parser": analysis.get("parser", {}),
                "copy_resolution": analysis.get("copy_resolution", []),
                "dialect_profile": analysis.get("dialect_profile", {}),
                # Field-level data lineage (MOVE A TO B, COMPUTE, EXEC SQL host-var<->column).
                # Persist the actual flows (capped) so the API/UI can render lineage instead
                # of only a count; flag truncation honestly for very large programs.
                "data_lineage": {
                    "field_flows": field_flows[:FIELD_FLOW_LIMIT],
                    "total": len(field_flows),
                    "truncated": len(field_flows) > FIELD_FLOW_LIMIT,
                },
                "ast_summary": {
                    "program_id": analysis.get("program_id"),
                    "divisions": analysis.get("divisions", []),
                    "paragraphs": analysis.get("paragraphs", []),
                    "counts": analysis.get("counts", {}),
                    "complexity": analysis.get("complexity", 1),
                    "data_item_count": len(analysis.get("data_items", [])),
                    "field_flow_count": len(field_flows),
                    "copy_replacing": analysis.get("copy_replacing", []),
                },
                "data_dictionary": analysis.get("data_items", []),
                "data_layout": analysis.get("data_layout", []),
                "linkage_contract": [
                    row for row in analysis.get("data_items", [])
                    if str(row.get("section") or "").upper() == "LINKAGE"
                ],
                "entry_contract": {
                    "procedure_using": _procedure_using_args(item.text),
                    "linkage_fields": _linkage_top_level_fields(analysis),
                },
                "procedure_outline": analysis.get("procedure_outline", []),
                "business_rules": _business_rules_with_path(analysis, item.member.relative_path),
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


def _business_rules_with_path(analysis: dict[str, Any], relative_path: str) -> list[dict[str, Any]]:
    rules: list[dict[str, Any]] = []
    for row in analysis.get("business_rules", []) or []:
        rule = dict(row)
        evidence = str(rule.get("source_evidence") or "")
        line = evidence.rsplit(":", 1)[-1] if ":" in evidence else ""
        if line.isdigit():
            rule["source_evidence"] = f"{relative_path}:{line}"
        elif not evidence:
            rule["source_evidence"] = relative_path
        rules.append(rule)
    return rules


def _primary_name(item: ClassifiedMember, artifact_type: str) -> str:
    text = item.text.upper()
    rules = {
        "COBOL": r"\bPROGRAM-ID\s*\.\s*([A-Z0-9#$@_-]+)",
        "JCL": r"(?m)^\s*//([A-Z0-9#$@]+)\s+JOB\b",
        "PROC": r"(?m)^\s*//([A-Z0-9#$@]+)\s+PROC\b",
        "SQL_DDL": r"\bCREATE\s+(?:(?:GLOBAL\s+TEMPORARY\s+)?TABLE|DATABASE|BUFFERPOOL|LOCATION|(?:REGULAR|LARGE|TEMPORARY)\s+TABLESPACE|TABLESPACE)\s+([A-Z0-9_.$#@]+)",
        "MQ": r"\bDEFINE\s+QLOCAL\(([^)]+)\)",
        "BMS_MAP": r"\b([A-Z0-9#$@]+)\s+DFHMSD\b",
        "IMS": r"\b(?:DBDGEN\s+.*?\bNAME|PSBGEN\s+.*?\bPSBNAME)=([A-Z0-9#$@_-]+)",
        "PLI": r"(?m)^\s*([A-Z0-9#$@_-]+)\s*:?\s+PROC\b",
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
    if artifact_type == "COBOL":
        relationships = _cobol_relationships(item, source, analysis)
    elif artifact_type == "PLI":
        relationships = _pli_relationships(item, source)
    elif artifact_type == "ASSEMBLER":
        relationships = _assembler_relationships(item, source)
    elif artifact_type in {"JCL", "PROC"}:
        relationships = _jcl_relationships(item, source)
    elif artifact_type in {"SQL_DDL", "DCLGEN"}:
        relationships = _sql_relationships(item, source)
    elif artifact_type == "IMS":
        relationships = _ims_relationships(item, source)
    elif artifact_type == "CSD":
        relationships = _csd_relationships(item, source)
    elif artifact_type == "SCHEDULER":
        relationships = _scheduler_relationships(item, source)
    else:
        relationships = []
    return _with_dataset_identity_relationships(item, relationships)


def _cross_member_relationships(
    members: list[ClassifiedMember],
    member_assets: dict[str, Asset],
    cobol_analysis: dict[str, dict[str, Any]],
    copybook_metadata: dict[str, dict[str, Any]] | None = None,
) -> list[FoundRelationship]:
    found: list[FoundRelationship] = []
    seen: set[tuple[str, str, str, str]] = set()
    copybook_index = _copybook_field_index(members, member_assets, copybook_metadata or {})
    for copybook_name, info in copybook_index.items():
        item = info["item"]
        source = info["asset"]
        for field in info["fields"]:
            line_no = int(field.get("line") or 1)
            copy_field = _copybook_field_asset(item.member.run_id, copybook_name, field, confidence=0.88)
            _append_found(
                found,
                seen,
                _found_existing(
                    item,
                    source,
                    "DECLARES_COPYBOOK_FIELD",
                    copy_field,
                    line_no,
                    _line_at(item.lines, line_no),
                    confidence=0.88,
                    validation_status="inferred",
                    discovery_method="copybook-field-parser",
                    attributes={**copy_field.attributes, "field_source": "copybook"},
                ),
            )
    for item in members:
        analysis = cobol_analysis.get(item.member.member_id)
        if not analysis:
            continue
        program = member_assets[item.member.member_id]
        for copy in analysis.get("copies", []):
            copy_name = _clean_name(str(copy.get("name", "")))
            info = copybook_index.get(copy_name)
            if not info:
                continue
            line_no = int(copy.get("line") or _line_for_text(item.lines, f"COPY {copy_name}") or 1)
            copy_statement = _copy_statement_at(item.lines, line_no)
            line = copy_statement["text"] or _line_at(item.lines, line_no)
            copy_attrs = _copy_attributes(line)
            replacement_pairs = copy_attrs.get("replacement_pairs", [])
            copy_site = _copy_site_asset(
                item.member.run_id,
                program.technical_name,
                copy_name,
                line_no,
                replacement_pairs,
                info["item"].member.relative_path,
            )
            _append_found(
                found,
                seen,
                _found_existing(
                    item,
                    program,
                    "HAS_COPY_SITE",
                    copy_site,
                    line_no,
                    line,
                    confidence=0.84,
                    validation_status="inferred",
                    discovery_method="copybook-expansion",
                    attributes=copy_site.attributes,
                ),
            )
            _append_found(
                found,
                seen,
                _found_existing(
                    item,
                    copy_site,
                    "COPY_SITE_EXPANDS_COPYBOOK",
                    info["asset"],
                    line_no,
                    line,
                    confidence=0.84,
                    validation_status="inferred",
                    discovery_method="copybook-expansion",
                    attributes={"copybook": copy_name, "copy_site": copy_site.technical_name},
                ),
            )
            selected_fields, selection_attrs = _selected_copybook_site_fields(
                analysis,
                item,
                info["fields"],
                replacement_pairs,
            )
            for field in selected_fields:
                original_field = _clean_name(str(field.get("name", "")))
                if not original_field:
                    continue
                materialized_field = _apply_copy_replacements_to_name(original_field, replacement_pairs)
                program_field = _field_asset(
                    item.member.run_id,
                    program.technical_name,
                    materialized_field,
                    confidence=0.82,
                    validation_status="inferred",
                    attributes={
                        **_bounded_copybook_attrs(copy_site, copy_name, original_field, materialized_field, replacement_pairs),
                        **selection_attrs,
                        "level": field.get("level"),
                        "pic": field.get("pic"),
                        "redefines": _apply_copy_replacements_to_name(str(field.get("redefines") or ""), replacement_pairs) if field.get("redefines") else None,
                        "occurs": field.get("occurs"),
                        "occurs_to": field.get("occurs_to"),
                        "depending_on": _apply_copy_replacements_to_name(str(field.get("depending_on") or ""), replacement_pairs) if field.get("depending_on") else None,
                        "usage": field.get("usage"),
                    },
                )
                copy_field = _copybook_field_asset(item.member.run_id, copy_name, field, confidence=0.88)
                bounded_attrs = {
                    **_bounded_copybook_attrs(copy_site, copy_name, original_field, materialized_field, replacement_pairs),
                    **selection_attrs,
                }
                _append_found(
                    found,
                    seen,
                    _found_existing(
                        item,
                        copy_site,
                        "COPY_SITE_DECLARES_FIELD",
                        program_field,
                        line_no,
                        line,
                        confidence=0.82,
                        validation_status="inferred",
                        discovery_method="copybook-expansion",
                        attributes={
                            **bounded_attrs,
                            "level": field.get("level"),
                            "pic": field.get("pic"),
                        },
                    ),
                )
                _append_found(
                    found,
                    seen,
                    FoundRelationship(
                        relationship_type="FIELD_DERIVED_FROM_COPYBOOK",
                        source_asset_id=program_field.asset_id,
                        source_asset=program_field,
                        target=copy_field,
                        evidence=Evidence(
                            source_path=item.member.relative_path,
                            line_start=line_no,
                            line_end=line_no,
                            evidence_text=line.strip()[:500],
                            extractor=EXTRACTOR,
                            discovery_method="copybook-expansion",
                            confidence=0.78,
                            validation_status="inferred",
                        ),
                        confidence=0.78,
                        validation_status="inferred",
                        discovery_method="copybook-expansion",
                        attributes={
                            "program": program.technical_name,
                            "copybook": copy_name,
                            "field": materialized_field,
                            "original_field": original_field,
                            "copybook_source_path": info["item"].member.relative_path,
                            "bounded_copybook_layout": True,
                            "copy_site": copy_site.technical_name,
                            "replacement_pairs": replacement_pairs,
                        },
                    ),
                )
                _append_found(
                    found,
                    seen,
                    _found_existing(
                        item,
                        program_field,
                        "MATERIALIZES_COPYBOOK_FIELD",
                        copy_field,
                        line_no,
                        line,
                        confidence=0.82,
                        validation_status="inferred",
                        discovery_method="copybook-expansion",
                        attributes={
                            **bounded_attrs,
                            "copybook_field": copy_field.technical_name,
                        },
                    ),
                )
                _append_found(
                    found,
                    seen,
                    _found_existing(
                        item,
                        program,
                        "USES_COPYBOOK_FIELD",
                        copy_field,
                        line_no,
                        line,
                        confidence=0.78,
                        validation_status="inferred",
                        discovery_method="copybook-expansion",
                        attributes={
                            "copybook": copy_name,
                            "field": materialized_field,
                            "original_field": original_field,
                            "bounded_copybook_layout": True,
                            "copy_site": copy_site.technical_name,
                        },
                    ),
                )
    for rel in _call_argument_mapping_relationships(members, member_assets, cobol_analysis):
        _append_found(found, seen, rel)
    for rel in _proc_expansion_relationships(members, member_assets):
        _append_found(found, seen, rel)
    return found


def _copy_statement_at(lines: tuple[str, ...], start_line: int) -> dict[str, Any]:
    text_parts: list[str] = []
    end_line = start_line
    for index in range(max(start_line, 1), len(lines) + 1):
        line = _line_at(lines, index)
        text_parts.append(line.strip())
        end_line = index
        if "." in line:
            break
    return {"line": start_line, "end_line": end_line, "text": " ".join(text_parts).strip()}


def _copy_site_asset(
    run_id: str,
    program_name: str,
    copybook_name: str,
    line_no: int,
    replacement_pairs: list[dict[str, str]],
    copybook_source_path: str,
) -> Asset:
    program = _clean_name(program_name)
    copybook = _clean_name(copybook_name)
    digest = stable_id("copy_site", program, copybook, line_no, replacement_pairs)
    return Asset(
        run_id=run_id,
        asset_type="COPY_SITE",
        technical_name=f"{program}::COPY::{line_no}::{copybook}::{digest}",
        display_name=f"{copybook} line {line_no}",
        confidence=0.84,
        validation_status="inferred",
        discovery_method="copybook-expansion",
        attributes={
            "program": program,
            "copybook": copybook,
            "line": line_no,
            "replacement_pairs": replacement_pairs,
            "copybook_source_path": copybook_source_path,
            "bounded_copybook_layout": True,
        },
    )


def _bounded_copybook_attrs(
    copy_site: Asset,
    copybook_name: str,
    original_field: str,
    materialized_field: str,
    replacement_pairs: list[dict[str, str]],
) -> dict[str, Any]:
    return {
        "copy_site": copy_site.technical_name,
        "copybook": _clean_name(copybook_name),
        "original_field": _clean_name(original_field),
        "materialized_field": _clean_name(materialized_field),
        "replacement_pairs": replacement_pairs,
        "bounded_copybook_layout": True,
    }


def _apply_copy_replacements_to_name(value: str, replacement_pairs: list[dict[str, str]]) -> str:
    name = _clean_name(value)
    if not name:
        return ""
    for pair in replacement_pairs:
        src = _clean_name(str(pair.get("from") or ""))
        dst = _clean_name(str(pair.get("to") or ""))
        if src and dst:
            name = re.sub(re.escape(src), dst, name, flags=re.I)
    return _clean_name(name)


def _selected_copybook_site_fields(
    analysis: dict[str, Any],
    item: ClassifiedMember,
    fields: list[dict[str, Any]],
    replacement_pairs: list[dict[str, str]],
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    if not fields:
        return [], {
            "copybook_field_materialization": "none",
            "materialized_field_count": 0,
            "source_field_count": 0,
            "materialization_truncated": False,
        }
    if len(fields) <= COPYBOOK_SITE_FIELD_LIMIT:
        return fields, {
            "copybook_field_materialization": "complete_small_copybook",
            "field_selection_reason": "within_materialization_limit",
            "materialized_field_count": len(fields),
            "source_field_count": len(fields),
            "materialization_truncated": False,
            "materialization_limit": COPYBOOK_SITE_FIELD_LIMIT,
        }
    references = _program_field_reference_names(analysis, item)
    top_level: list[dict[str, Any]] = []
    used: list[dict[str, Any]] = []
    seen_top: set[str] = set()
    seen_used: set[str] = set()
    for field in fields:
        original = _clean_name(str(field.get("name", "")))
        if not original:
            continue
        materialized = _apply_copy_replacements_to_name(original, replacement_pairs)
        level = str(field.get("level") or "").zfill(2)
        if level in {"01", "77"} and original not in seen_top:
            top_level.append(field)
            seen_top.add(original)
        if _copybook_field_is_referenced(original, materialized, references) and original not in seen_used:
            used.append(field)
            seen_used.add(original)
    if not used:
        selected = fields[:COPYBOOK_SITE_FIELD_LIMIT]
        return selected, {
            "copybook_field_materialization": "bounded_sample_no_usage",
            "field_selection_reason": "no_behavioral_field_reference_detected",
            "materialized_field_count": len(selected),
            "source_field_count": len(fields),
            "materialization_truncated": len(fields) > len(selected),
            "materialization_limit": COPYBOOK_SITE_FIELD_LIMIT,
        }
    used = _expand_used_copybook_groups(fields, used)
    selected: list[dict[str, Any]] = []
    selected_names: set[str] = set()
    for field in [*top_level, *used]:
        name = _clean_name(str(field.get("name", "")))
        if not name or name in selected_names:
            continue
        selected.append(field)
        selected_names.add(name)
        if len(selected) >= COPYBOOK_SITE_FIELD_LIMIT:
            break
    return selected, {
        "copybook_field_materialization": "bounded_used_fields",
        "field_selection_reason": "referenced_by_program_behavior",
        "materialized_field_count": len(selected),
        "source_field_count": len(fields),
        "used_field_reference_count": len(used),
        "materialization_truncated": len(used) + len(top_level) > len(selected),
        "materialization_limit": COPYBOOK_SITE_FIELD_LIMIT,
    }


def _expand_used_copybook_groups(fields: list[dict[str, Any]], used: list[dict[str, Any]]) -> list[dict[str, Any]]:
    used_names = {_clean_name(str(field.get("name", ""))) for field in used}
    expanded: list[dict[str, Any]] = []
    active_group_levels: list[int] = []
    for field in fields:
        name = _clean_name(str(field.get("name", "")))
        level = _int_level(field.get("level"))
        while active_group_levels and level <= active_group_levels[-1]:
            active_group_levels.pop()
        if name in used_names:
            expanded.append(field)
            if level < 49:
                active_group_levels.append(level)
            continue
        if active_group_levels:
            expanded.append(field)
    return expanded or used


def _int_level(value: Any) -> int:
    try:
        return int(str(value).strip())
    except (TypeError, ValueError):
        return 99


def _program_field_reference_names(analysis: dict[str, Any], item: ClassifiedMember) -> set[str]:
    names: set[str] = set()
    for flow in analysis.get("field_flows", []) or []:
        for key in ("src", "dst", "source_field", "target_field"):
            names.update(_field_reference_variants(flow.get(key)))
    for call in analysis.get("calls", []) or []:
        names.update(_field_reference_variants(call.get("via")))
        for arg in call.get("using", []) or call.get("arguments", []) or []:
            names.update(_field_reference_variants(arg))
    for section in ("sql", "cics", "business_rules"):
        _collect_reference_names(analysis.get(section), names)
    names.update(_clean_name(token) for token in re.findall(r"\b[A-Z][A-Z0-9#$@_-]*\b", _procedure_division_text(item.text).upper()))
    return {name for name in names if name}


def _collect_reference_names(value: Any, names: set[str]) -> None:
    if isinstance(value, dict):
        for item in value.values():
            _collect_reference_names(item, names)
    elif isinstance(value, list):
        for item in value:
            _collect_reference_names(item, names)
    elif isinstance(value, str):
        names.update(_field_reference_variants(value))


def _field_reference_variants(value: Any) -> set[str]:
    text = _clean_name(str(value or ""))
    if not text:
        return set()
    variants = {text}
    for part in re.split(r"[^A-Z0-9#$@_.-]+", text):
        cleaned = _clean_name(part)
        if cleaned:
            variants.add(cleaned)
            if "." in cleaned:
                variants.add(cleaned.rsplit(".", 1)[-1])
    if "." in text:
        variants.add(text.rsplit(".", 1)[-1])
    return variants


def _copybook_field_is_referenced(original: str, materialized: str, references: set[str]) -> bool:
    candidates = {original, materialized}
    for value in list(candidates):
        if "-" in value:
            candidates.add(value.replace("-", ""))
    return any(candidate in references for candidate in candidates if candidate)


def _procedure_division_text(text: str) -> str:
    match = re.search(r"\bPROCEDURE\s+DIVISION\b", text, flags=re.I)
    return text[match.start():] if match else text


def _copybook_field_index(
    members: list[ClassifiedMember],
    member_assets: dict[str, Asset],
    copybook_metadata: dict[str, dict[str, Any]] | None = None,
) -> dict[str, dict[str, Any]]:
    index: dict[str, dict[str, Any]] = {}
    selected_sources = {
        _clean_name(name): str(info.get("source_path") or "")
        for name, info in (copybook_metadata or {}).items()
    }
    for item in members:
        if item.member.artifact_type not in {"COPYBOOK", "DCLGEN"} or item.member.is_binary or not item.text:
            continue
        fields = _copybook_data_items(item)
        if not fields:
            continue
        aliases = _member_aliases(item, item.member.artifact_type)
        for alias in aliases:
            if not alias:
                continue
            selected_source = selected_sources.get(_clean_name(alias))
            if selected_source and selected_source != item.member.relative_path:
                continue
            index.setdefault(alias, {"item": item, "asset": member_assets[item.member.member_id], "fields": fields})
    return index


def _copybook_data_items(item: ClassifiedMember) -> list[dict[str, Any]]:
    try:
        unit = cobol_ast.parse(item.text)
    except Exception:
        return []
    return [
        row for row in unit.data_items
        if _clean_name(str(row.get("name", ""))) and int(row.get("level") or 0) != 88
    ]


def _copybook_field_asset(run_id: str, copybook_name: str, field: dict[str, Any], *, confidence: float) -> Asset:
    copybook = _clean_name(copybook_name)
    field_name = _clean_name(str(field.get("name", "")))
    return Asset(
        run_id=run_id,
        asset_type="COPYBOOK_FIELD",
        technical_name=f"{copybook}::{field_name}",
        display_name=field_name,
        confidence=confidence,
        validation_status="inferred",
        discovery_method="copybook-field-parser",
        attributes={
            "copybook": copybook,
            "field": field_name,
            "level": field.get("level"),
            "pic": field.get("pic"),
            "redefines": field.get("redefines"),
            "occurs": field.get("occurs"),
            "occurs_to": field.get("occurs_to"),
            "depending_on": field.get("depending_on"),
            "usage": field.get("usage"),
            "value": field.get("value"),
            "condition_name": field.get("condition_name"),
        },
    )


def _proc_expansion_relationships(
    members: list[ClassifiedMember],
    member_assets: dict[str, Asset],
) -> list[FoundRelationship]:
    found: list[FoundRelationship] = []
    proc_defs = _proc_definitions(members, member_assets)
    if not proc_defs:
        return found
    for item in members:
        if item.member.artifact_type != "JCL":
            continue
        job = member_assets[item.member.member_id]
        for invocation in _jcl_proc_invocations(item):
            proc_name = invocation["proc_name"]
            proc_def = proc_defs.get(proc_name)
            if not proc_def:
                continue
            invocation_step = _jcl_step_asset(item.member.run_id, job, invocation["step_name"])
            params = {**proc_def["parameters"], **invocation["parameters"]}
            for proc_step in proc_def["steps"]:
                expanded_step = Asset(
                    run_id=item.member.run_id,
                    asset_type="JOB_STEP",
                    technical_name=f"{job.technical_name}::{invocation['step_name']}.{proc_step['step_name']}",
                    display_name=f"{invocation['step_name']}.{proc_step['step_name']}",
                    confidence=0.74,
                    validation_status="inferred",
                    discovery_method="proc-expansion",
                    attributes={
                        "job": job.technical_name,
                        "invocation_step": invocation["step_name"],
                        "proc": proc_name,
                        "proc_step": proc_step["step_name"],
                        "symbolic_parameters": params,
                    },
                )
                found.append(
                    FoundRelationship(
                        relationship_type="EXPANDS_TO_STEP",
                        source_asset_id=invocation_step.asset_id,
                        source_asset=invocation_step,
                        target=expanded_step,
                        evidence=Evidence(
                            source_path=item.member.relative_path,
                            line_start=invocation["line"],
                            line_end=invocation["line"],
                            evidence_text=_line_at(item.lines, invocation["line"]).strip()[:500],
                            extractor=EXTRACTOR,
                            discovery_method="proc-expansion",
                            confidence=0.74,
                            validation_status="inferred",
                        ),
                        confidence=0.74,
                        validation_status="inferred",
                        discovery_method="proc-expansion",
                        attributes={
                            "proc": proc_name,
                            "proc_step": proc_step["step_name"],
                            "symbolic_parameters": params,
                        },
                    )
                )
                found.append(
                    _found_existing(
                        item,
                        expanded_step,
                        "EXPANDED_FROM_PROC_STEP",
                        _proc_step_asset(item.member.run_id, proc_name, proc_step["step_name"]),
                        invocation["line"],
                        _line_at(item.lines, invocation["line"]),
                        confidence=0.74,
                        validation_status="inferred",
                        discovery_method="proc-expansion",
                        attributes={"proc_source_path": proc_def["item"].member.relative_path, "proc_line": proc_step["line"]},
                    )
                )
                if proc_step.get("exec_target"):
                    target = _substitute_jcl_symbols(proc_step["exec_target"], params)
                    target_type = proc_step.get("target_type", "PROGRAM")
                    found.append(
                        _found_existing(
                            item,
                            expanded_step,
                            "EXECUTES" if target_type == "PROGRAM" else "INVOKES_PROC",
                            _asset(item.member.run_id, target_type, target, confidence=0.74, validation_status="inferred"),
                            invocation["line"],
                            _line_at(item.lines, invocation["line"]),
                            confidence=0.74,
                            validation_status="inferred",
                            discovery_method="proc-expansion",
                            attributes={"expanded_from_proc": proc_name, "proc_step": proc_step["step_name"]},
                        )
                    )
                for dataset in proc_step.get("datasets", []):
                    dsn = _substitute_jcl_symbols(dataset["dsn"], params)
                    rel = _found_existing(
                        item,
                        expanded_step,
                        dataset["relationship_type"],
                        _asset(item.member.run_id, "DATASET", dsn, confidence=0.68, validation_status="inferred"),
                        invocation["line"],
                        _line_at(item.lines, invocation["line"]),
                        confidence=0.68,
                        validation_status="inferred",
                        discovery_method="proc-expansion",
                        attributes={
                            "expanded_from_proc": proc_name,
                            "proc_step": proc_step["step_name"],
                            "dd_name": dataset.get("dd_name"),
                            "disp": dataset.get("disp"),
                            "unresolved_symbolics": _unresolved_symbolics(dsn),
                        },
                    )
                    found.extend(_with_dataset_identity_relationships(item, [rel]))
    return found


def _proc_definitions(
    members: list[ClassifiedMember],
    member_assets: dict[str, Asset],
) -> dict[str, dict[str, Any]]:
    definitions: dict[str, dict[str, Any]] = {}
    for item in members:
        if item.member.artifact_type != "PROC":
            continue
        proc_name = member_assets[item.member.member_id].technical_name
        parameters: dict[str, str] = {}
        steps: list[dict[str, Any]] = []
        current: dict[str, Any] | None = None
        for statement in _jcl_logical_statements(item.lines):
            line_no = statement["line"]
            line = statement["text"]
            upper = line.upper()
            proc_match = re.match(r"^\s*//[A-Z0-9#$@_-]+\s+PROC\b(.*)", upper)
            if proc_match:
                parameters.update(_jcl_parameter_tail(proc_match.group(1)))
                continue
            step_match = re.match(r"^\s*//([A-Z0-9#$@_-]+)\s+EXEC\b", upper)
            if step_match:
                current = {
                    "step_name": _clean_name(step_match.group(1)),
                    "line": line_no,
                    "datasets": [],
                }
                exec_match = re.search(r"\bEXEC\s+(?:(PGM|PROC)=)?([A-Z0-9#$@_&.-]+)", upper)
                if exec_match:
                    current["target_type"] = "PROGRAM" if exec_match.group(1) == "PGM" else "PROC"
                    current["exec_target"] = exec_match.group(2)
                steps.append(current)
                continue
            dsn_match = re.search(r"\bDSN=([A-Z0-9.$#@_&-]+)", upper)
            if dsn_match and current is not None:
                current["datasets"].append(
                    {
                        "dsn": dsn_match.group(1),
                        "relationship_type": "WRITES_DATASET" if any(token in upper for token in ("DISP=(NEW", "DISP=NEW", "DISP=MOD")) else "READS_DATASET",
                        "dd_name": _jcl_dd_name(upper),
                        "disp": _jcl_disp(upper),
                    }
                )
        definitions[proc_name] = {"item": item, "parameters": parameters, "steps": steps}
    return definitions


def _jcl_proc_invocations(item: ClassifiedMember) -> list[dict[str, Any]]:
    invocations: list[dict[str, Any]] = []
    for statement in _jcl_logical_statements(item.lines):
        line_no = statement["line"]
        line = statement["text"]
        upper = line.upper()
        match = re.match(r"^\s*//([A-Z0-9#$@_-]+)\s+EXEC\s+(?:(?:PROC=)?([A-Z0-9#$@_-]+))", upper)
        if not match:
            continue
        if "PGM=" in upper:
            continue
        proc_name = _clean_name(match.group(2))
        if proc_name in {"PGM", "PROC"}:
            continue
        invocations.append(
            {
                "step_name": _clean_name(match.group(1)),
                "proc_name": proc_name,
                "line": line_no,
                "parameters": _jcl_exec_parameters(line),
            }
        )
    return invocations


def _proc_step_asset(run_id: str, proc_name: str, step_name: str) -> Asset:
    proc = _clean_name(proc_name)
    step = _clean_name(step_name)
    return Asset(
        run_id=run_id,
        asset_type="PROC_STEP",
        technical_name=f"{proc}::{step}",
        display_name=step,
        confidence=0.95,
        validation_status="confirmed",
        discovery_method="observed",
        attributes={"proc": proc, "step_name": step},
    )


def _jcl_parameter_tail(tail: str) -> dict[str, str]:
    params: dict[str, str] = {}
    for key, value in re.findall(r"\b([A-Z0-9#$@_-]+)=([^,\s]+)", tail, flags=re.I):
        params[_clean_name(key)] = value.strip().strip("'\"")
    return params


def _substitute_jcl_symbols(value: str, params: dict[str, str]) -> str:
    def repl(match: re.Match[str]) -> str:
        key = _clean_name(match.group(1))
        return params.get(key, f"&{key}")

    substituted = re.sub(r"&([A-Z0-9#$@_-]+)", repl, value, flags=re.I)
    return _clean_name(re.sub(r"\.{2,}", ".", substituted))


def _unresolved_symbolics(value: str) -> list[str]:
    return [_clean_name(match.group(1)) for match in re.finditer(r"&([A-Z0-9#$@_-]+)", value, flags=re.I)]


def _cobol_relationships(
    item: ClassifiedMember, source: Asset, analysis: dict[str, Any] | None = None
) -> list[FoundRelationship]:
    found: list[FoundRelationship] = []
    seen: set[tuple[str, str, str, str]] = set()
    if analysis:
        parser = analysis.get("parser", {})
        parser_cap = float(parser.get("confidence") or 1.0)
        for rel in _data_dictionary_relationships(item, source, analysis, parser_cap):
            _append_found(found, seen, rel)
        for rel in _field_flow_relationships(item, source, analysis, parser_cap):
            _append_found(found, seen, rel)
        for rel in _control_flow_relationships(item, source, analysis, parser_cap):
            _append_found(found, seen, rel)
        for rel in _procedure_structure_relationships(item, source, analysis, parser_cap):
            _append_found(found, seen, rel)
        for rel in _business_rule_relationships(item, source, analysis, parser_cap):
            _append_found(found, seen, rel)
        copy_resolution = {
            _clean_name(str(row.get("name", ""))): row
            for row in analysis.get("copy_resolution", [])
        }
        call_contracts_by_line = _call_contracts_by_line(item.lines)
        using_by_line = {
            line_no: [arg["name"] for arg in contract.get("arguments", [])]
            for line_no, contract in call_contracts_by_line.items()
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
            call_contract = call_contracts_by_line.get(line_no, {})
            call_args = [arg["name"] for arg in call_contract.get("arguments", [])]
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
                            "using": call_args or using_by_line.get(line_no, []),
                            "interface_contract": {
                                "caller_using": call_args or using_by_line.get(line_no, []),
                                "arguments": call_contract.get("arguments", []),
                                "contract_status": "observed" if call_args or using_by_line.get(line_no) else "not_declared",
                            },
                        },
                    ),
                )
        for rel in _interface_contract_relationships(item, source, analysis, parser_cap):
            _append_found(found, seen, rel)
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
            line = _line_at(item.lines, line_no)
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
                    line,
                    confidence=min(float(cics.get("confidence") or 0.80), parser_cap),
                    validation_status=str(cics.get("validation") or "inferred"),
                    discovery_method="reference-parser",
                    attributes={
                        "cics_kind": cics.get("kind"),
                        "parser_effective": parser.get("effective"),
                        "data_contract": _cics_data_contract(line),
                    },
                ),
            )
        for rel in _cics_contract_relationships(item, source, analysis, parser_cap):
            _append_found(found, seen, rel)
        for rel in _db2_cursor_relationships(item, source, item.text, embedded=True, confidence=min(0.90, parser_cap)):
            _append_found(found, seen, rel)
        for rel in _db2_package_relationships(item, source, item.text, confidence=min(0.84, parser_cap)):
            _append_found(found, seen, rel)
        for rel in _db2_include_relationships(item, source, item.text, embedded=True, confidence=min(0.84, parser_cap)):
            _append_found(found, seen, rel)
        for rel in _db2_statement_relationships(item, source, item.text, embedded=True, confidence=min(0.86, parser_cap)):
            _append_found(found, seen, rel)
    parser_rel_types = {rel.relationship_type for rel in found} if analysis else set()
    for line_no, line in enumerate(item.lines, 1):
        if _is_cobol_comment(line):
            continue
        upper = line.upper()
        if "CALLS" not in parser_rel_types and "DYNAMIC_CALL" not in parser_rel_types:
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
                if rel_type in parser_rel_types:
                    continue
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
            if "CALLS" in parser_rel_types:
                continue
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
    for rel in _file_io_semantic_relationships(item, source, analysis):
        _append_found(found, seen, rel)
    for rel in _sort_merge_relationships(item, source):
        _append_found(found, seen, rel)
    return found


def _selected_data_dictionary_items(
    item: ClassifiedMember,
    analysis: dict[str, Any],
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    data_items = list(analysis.get("data_items", []) or [])
    if len(data_items) <= DATA_DICTIONARY_GRAPH_LIMIT:
        return data_items, {
            "data_dictionary_projection": "complete",
            "projected_data_item_count": len(data_items),
            "source_data_item_count": len(data_items),
            "data_dictionary_truncated": False,
        }
    references = _program_field_reference_names(analysis, item)
    selected: list[dict[str, Any]] = []
    selected_names: set[str] = set()
    for data_item in data_items:
        name = _clean_name(str(data_item.get("name", "")))
        if not name or name in selected_names:
            continue
        section = str(data_item.get("section") or "").upper()
        level = str(data_item.get("level") or "").zfill(2)
        if (
            section == "LINKAGE"
            or level in {"01", "77"}
            or _copybook_field_is_referenced(name, name, references)
        ):
            selected.append(data_item)
            selected_names.add(name)
        if len(selected) >= DATA_DICTIONARY_GRAPH_LIMIT:
            break
    if not selected:
        selected = data_items[:DATA_DICTIONARY_GRAPH_LIMIT]
    return selected, {
        "data_dictionary_projection": "bounded_used_fields",
        "projected_data_item_count": len(selected),
        "source_data_item_count": len(data_items),
        "data_dictionary_truncated": len(data_items) > len(selected),
        "data_dictionary_graph_limit": DATA_DICTIONARY_GRAPH_LIMIT,
    }


def _data_dictionary_relationships(
    item: ClassifiedMember,
    source: Asset,
    analysis: dict[str, Any],
    parser_cap: float,
) -> list[FoundRelationship]:
    found: list[FoundRelationship] = []
    selected_data_items, selection_attrs = _selected_data_dictionary_items(item, analysis)
    for data_item in selected_data_items:
        name = _clean_name(str(data_item.get("name", "")))
        if not name:
            continue
        line_no = int(data_item.get("line") or 1)
        field = _field_asset(
            item.member.run_id,
            source.technical_name,
            name,
            confidence=min(0.92, parser_cap),
            validation_status="confirmed" if parser_cap >= 0.7 else "inferred",
            attributes={
                "program": source.technical_name,
                "section": data_item.get("section"),
                "level": data_item.get("level"),
                "pic": data_item.get("pic"),
                "redefines": data_item.get("redefines"),
                "occurs": data_item.get("occurs"),
                "occurs_to": data_item.get("occurs_to"),
                "depending_on": data_item.get("depending_on"),
                "usage": data_item.get("usage"),
                "value": data_item.get("value"),
                "condition_name": data_item.get("condition_name"),
                **selection_attrs,
            },
        )
        found.append(
            _found_existing(
                item,
                source,
                "DECLARES_FIELD",
                field,
                line_no,
                _line_at(item.lines, line_no),
                confidence=min(0.92, parser_cap),
                validation_status="confirmed" if parser_cap >= 0.7 else "inferred",
                discovery_method="reference-parser",
                attributes=field.attributes,
            )
        )
    return found


def _field_flow_relationships(
    item: ClassifiedMember,
    source: Asset,
    analysis: dict[str, Any],
    parser_cap: float,
) -> list[FoundRelationship]:
    found: list[FoundRelationship] = []
    for flow in analysis.get("field_flows", [])[:FIELD_FLOW_LIMIT]:
        src = _clean_name(str(flow.get("src", "")))
        dst = _clean_name(str(flow.get("dst", "")))
        if not src or not dst:
            continue
        line_no = int(flow.get("line") or 1)
        src_field = _field_asset(item.member.run_id, source.technical_name, src, confidence=min(0.88, parser_cap), validation_status="inferred")
        dst_field = _field_asset(item.member.run_id, source.technical_name, dst, confidence=min(0.88, parser_cap), validation_status="inferred")
        found.append(
            FoundRelationship(
                relationship_type="FLOWS_TO",
                source_asset_id=src_field.asset_id,
                source_asset=src_field,
                target=dst_field,
                evidence=Evidence(
                    source_path=item.member.relative_path,
                    line_start=line_no,
                    line_end=line_no,
                    evidence_text=_line_at(item.lines, line_no).strip()[:500],
                    extractor=EXTRACTOR,
                    discovery_method="reference-parser",
                    confidence=min(0.88, parser_cap),
                    validation_status="inferred",
                ),
                confidence=min(0.88, parser_cap),
                validation_status="inferred",
                discovery_method="reference-parser",
                attributes={
                    "program": source.technical_name,
                    "flow_kind": flow.get("kind"),
                    "line": line_no,
                    "source_field": src,
                    "target_field": dst,
                    "truncated": len(analysis.get("field_flows", [])) > FIELD_FLOW_LIMIT,
                },
            )
        )
    return found


def _control_flow_relationships(
    item: ClassifiedMember,
    source: Asset,
    analysis: dict[str, Any],
    parser_cap: float,
) -> list[FoundRelationship]:
    found: list[FoundRelationship] = []
    paragraph_names = {_clean_name(str(name)) for name in analysis.get("paragraphs", []) if name}
    if not paragraph_names:
        return found
    current = ""
    paragraph_assets = {
        name: _paragraph_asset(item.member.run_id, source.technical_name, name, confidence=min(0.90, parser_cap))
        for name in paragraph_names
    }
    for name, para in paragraph_assets.items():
        line_no = _line_for_text(item.lines, f"{name}.") or 1
        found.append(
            _found_existing(
                item,
                source,
                "CONTAINS_PARAGRAPH",
                para,
                line_no,
                _line_at(item.lines, line_no),
                confidence=min(0.90, parser_cap),
                validation_status="confirmed" if parser_cap >= 0.7 else "inferred",
                discovery_method="reference-parser",
                attributes={"program": source.technical_name, "paragraph": name},
            )
        )
    for line_no, line in enumerate(item.lines, 1):
        if _is_cobol_comment(line):
            continue
        match = re.match(r"^\s{0,7}([A-Z0-9][A-Z0-9-]*)\.\s*$", line.upper())
        if match and _clean_name(match.group(1)) in paragraph_names:
            current = _clean_name(match.group(1))
            continue
        source_para = paragraph_assets.get(current)
        if source_para is None:
            continue
        for target in re.findall(r"\bPERFORM\s+([A-Z0-9][A-Z0-9-]*)", line.upper()):
            target_name = _clean_name(target)
            if target_name in paragraph_assets:
                found.append(_paragraph_edge(item, source_para, paragraph_assets[target_name], "PERFORMS", line_no, line, parser_cap))
        for target in re.findall(r"\bGO\s+TO\s+([A-Z0-9][A-Z0-9-]*)", line.upper()):
            target_name = _clean_name(target)
            if target_name in paragraph_assets:
                found.append(_paragraph_edge(item, source_para, paragraph_assets[target_name], "BRANCHES_TO", line_no, line, parser_cap))
    return found


def _paragraph_edge(
    item: ClassifiedMember,
    source_para: Asset,
    target_para: Asset,
    relationship_type: str,
    line_no: int,
    line: str,
    parser_cap: float,
) -> FoundRelationship:
    return FoundRelationship(
        relationship_type=relationship_type,
        source_asset_id=source_para.asset_id,
        source_asset=source_para,
        target=target_para,
        evidence=Evidence(
            source_path=item.member.relative_path,
            line_start=line_no,
            line_end=line_no,
            evidence_text=line.strip()[:500],
            extractor=EXTRACTOR,
            discovery_method="reference-parser",
            confidence=min(0.86, parser_cap),
            validation_status="inferred",
        ),
        confidence=min(0.86, parser_cap),
        validation_status="inferred",
        discovery_method="reference-parser",
        attributes={"control_flow": True},
    )


def _procedure_structure_relationships(
    item: ClassifiedMember,
    source: Asset,
    analysis: dict[str, Any],
    parser_cap: float,
) -> list[FoundRelationship]:
    found: list[FoundRelationship] = []
    paragraph_assets = {
        _clean_name(str(name)): _paragraph_asset(item.member.run_id, source.technical_name, str(name), confidence=min(0.90, parser_cap))
        for name in analysis.get("paragraphs", [])
        if str(name).strip()
    }
    current_section: Asset | None = None
    in_procedure = False
    for line_no, line in enumerate(item.lines, 1):
        upper = line.upper()
        if "PROCEDURE DIVISION" in upper:
            in_procedure = True
            continue
        if not in_procedure or _is_cobol_comment(line):
            continue
        section_match = re.match(r"^\s{0,7}([A-Z0-9][A-Z0-9-]*)\s+SECTION\s*\.", upper)
        if section_match:
            current_section = _section_asset(item.member.run_id, source.technical_name, section_match.group(1), confidence=min(0.86, parser_cap))
            found.append(
                _found_existing(
                    item,
                    source,
                    "CONTAINS_SECTION",
                    current_section,
                    line_no,
                    line,
                    confidence=min(0.86, parser_cap),
                    validation_status="inferred",
                    discovery_method="reference-parser",
                    attributes={"program": source.technical_name, "section": current_section.display_name},
                )
            )
            continue
        para_match = re.match(r"^\s{0,7}([A-Z0-9][A-Z0-9-]*)\.\s*$", upper)
        para_name = _clean_name(para_match.group(1)) if para_match else ""
        if current_section is not None and para_name in paragraph_assets:
            found.append(
                _found_existing(
                    item,
                    current_section,
                    "SECTION_CONTAINS_PARAGRAPH",
                    paragraph_assets[para_name],
                    line_no,
                    line,
                    confidence=min(0.84, parser_cap),
                    validation_status="inferred",
                    discovery_method="reference-parser",
                    attributes={"section": current_section.display_name, "paragraph": para_name},
                )
            )

    previous_statement: Asset | None = None
    sequence = 0
    for paragraph in analysis.get("procedure_outline", []) or []:
        paragraph_name = _clean_name(str(paragraph.get("paragraph") or "MAIN"))
        parent = paragraph_assets.get(paragraph_name)
        for step in paragraph.get("steps", []) or []:
            verb = _clean_name(str(step.get("verb") or "STATEMENT"))
            line_no = int(step.get("line") or 1)
            text = str(step.get("text") or _line_at(item.lines, line_no))
            sequence += 1
            statement = _statement_asset(
                item.member.run_id,
                source.technical_name,
                paragraph_name,
                verb,
                line_no,
                sequence,
                text,
                confidence=min(0.82, parser_cap),
            )
            found.append(
                _found_existing(
                    item,
                    parent or source,
                    "CONTAINS_STATEMENT",
                    statement,
                    line_no,
                    _line_at(item.lines, line_no),
                    confidence=min(0.82, parser_cap),
                    validation_status="inferred",
                    discovery_method="reference-parser",
                    attributes={
                        "program": source.technical_name,
                        "paragraph": paragraph_name,
                        "verb": verb,
                        "sequence": sequence,
                    },
                )
            )
            if previous_statement is not None:
                found.append(
                    _found_existing(
                        item,
                        previous_statement,
                        "EXECUTES_BEFORE",
                        statement,
                        line_no,
                        _line_at(item.lines, line_no),
                        confidence=min(0.72, parser_cap),
                        validation_status="inferred",
                        discovery_method="reference-parser",
                        attributes={"ordering": "procedure_source_order", "sequence": sequence},
                    )
                )
            previous_statement = statement
    return found


def _business_rule_relationships(
    item: ClassifiedMember,
    source: Asset,
    analysis: dict[str, Any],
    parser_cap: float,
) -> list[FoundRelationship]:
    found: list[FoundRelationship] = []
    rules = _business_rules_with_path(analysis, item.member.relative_path)
    for index, rule in enumerate(rules, 1):
        evidence = str(rule.get("source_evidence") or "")
        line_text = evidence.rsplit(":", 1)[-1] if ":" in evidence else ""
        line_no = int(line_text) if line_text.isdigit() else 1
        confidence = min(float(rule.get("confidence") or 0.60), parser_cap)
        rule_asset = _business_rule_asset(item.member.run_id, source.technical_name, rule, index, confidence=confidence)
        found.append(
            _found_existing(
                item,
                source,
                "DEFINES_BUSINESS_RULE",
                rule_asset,
                line_no,
                _line_at(item.lines, line_no),
                confidence=confidence,
                validation_status=str(rule.get("validation_status") or "inferred"),
                discovery_method="business-rule-extractor",
                attributes={
                    "rule_id": rule_asset.display_name,
                    "kind": rule.get("kind"),
                    "condition": rule.get("condition"),
                    "statement": rule.get("statement"),
                    "action": rule.get("action"),
                },
            )
        )
        for field_name in rule.get("fields", []) or []:
            found.append(
                _found_existing(
                    item,
                    rule_asset,
                    "RULE_USES_FIELD",
                    _field_asset(item.member.run_id, source.technical_name, str(field_name), confidence=0.62, validation_status="inferred"),
                    line_no,
                    _line_at(item.lines, line_no),
                    confidence=0.62,
                    validation_status="inferred",
                    discovery_method="business-rule-extractor",
                    attributes={"rule_id": rule_asset.display_name, "field": _clean_name(str(field_name))},
                )
            )
        if str(rule.get("kind") or "").lower() == "calculation":
            transformation = _transformation_asset(item.member.run_id, source.technical_name, rule, index, confidence=confidence)
            found.append(
                _found_existing(
                    item,
                    source,
                    "DEFINES_TRANSFORMATION",
                    transformation,
                    line_no,
                    _line_at(item.lines, line_no),
                    confidence=confidence,
                    validation_status="inferred",
                    discovery_method="business-rule-extractor",
                    attributes={"rule_id": rule_asset.display_name, "expression": rule.get("condition")},
                )
            )
            outputs, inputs = _calculation_fields(str(rule.get("condition") or ""))
            for field_name in inputs:
                found.append(
                    _found_existing(
                        item,
                        transformation,
                        "TRANSFORMATION_INPUT_FIELD",
                        _field_asset(item.member.run_id, source.technical_name, field_name, confidence=0.70, validation_status="inferred"),
                        line_no,
                        _line_at(item.lines, line_no),
                        confidence=0.70,
                        validation_status="inferred",
                        discovery_method="business-rule-extractor",
                        attributes={"transformation": transformation.display_name, "role": "input"},
                    )
                )
            for field_name in outputs:
                found.append(
                    _found_existing(
                        item,
                        transformation,
                        "TRANSFORMATION_OUTPUT_FIELD",
                        _field_asset(item.member.run_id, source.technical_name, field_name, confidence=0.72, validation_status="inferred"),
                        line_no,
                        _line_at(item.lines, line_no),
                        confidence=0.72,
                        validation_status="inferred",
                        discovery_method="business-rule-extractor",
                        attributes={"transformation": transformation.display_name, "role": "output"},
                    )
                )
    return found


def _cics_contract_relationships(
    item: ClassifiedMember,
    source: Asset,
    analysis: dict[str, Any],
    parser_cap: float,
) -> list[FoundRelationship]:
    found: list[FoundRelationship] = []
    paragraph_assets = {
        _clean_name(str(name)): _paragraph_asset(item.member.run_id, source.technical_name, str(name), confidence=min(0.86, parser_cap))
        for name in analysis.get("paragraphs", [])
        if str(name).strip()
    }
    for block in _iter_exec_cics_blocks(item.text):
        body = block["body"]
        upper = body.upper()
        line_no = int(block["line"] or 1)
        verb_match = re.match(r"\s*([A-Z]+)", upper)
        verb = _clean_name(verb_match.group(1)) if verb_match else "CICS"
        if verb == "HANDLE":
            for condition, target in re.findall(r"\b([A-Z0-9_-]+)\s*\(\s*([A-Z0-9#$@_-]+)\s*\)", upper):
                condition_name = _clean_name(condition)
                target_name = _clean_name(target)
                condition_asset = _cics_condition_asset(item.member.run_id, source.technical_name, condition_name, line_no, confidence=min(0.78, parser_cap))
                found.append(
                    _found_existing(
                        item,
                        source,
                        "HANDLES_CICS_CONDITION",
                        condition_asset,
                        line_no,
                        _line_at(item.lines, line_no),
                        confidence=min(0.78, parser_cap),
                        validation_status="inferred",
                        discovery_method="cics-contract-extractor",
                        attributes={"condition": condition_name, "target_paragraph": target_name},
                    )
                )
                if target_name in paragraph_assets:
                    found.append(
                        _found_existing(
                            item,
                            condition_asset,
                            "BRANCHES_TO",
                            paragraph_assets[target_name],
                            line_no,
                            _line_at(item.lines, line_no),
                            confidence=min(0.76, parser_cap),
                            validation_status="inferred",
                            discovery_method="cics-contract-extractor",
                            attributes={"condition": condition_name, "target_paragraph": target_name},
                        )
                    )
            continue
        contract = _cics_data_contract(body)
        if not contract:
            continue
        contract_asset = _cics_contract_asset(item.member.run_id, source.technical_name, verb, line_no, contract, confidence=min(0.80, parser_cap))
        found.append(
            _found_existing(
                item,
                source,
                "DEFINES_CICS_CONTRACT",
                contract_asset,
                line_no,
                _line_at(item.lines, line_no),
                confidence=min(0.80, parser_cap),
                validation_status="inferred",
                discovery_method="cics-contract-extractor",
                attributes={"verb": verb, "data_contract": contract},
            )
        )
        if contract.get("commarea"):
            found.append(
                _found_existing(
                    item,
                    source,
                    "DEFINES_COMMAREA_CONTRACT",
                    contract_asset,
                    line_no,
                    _line_at(item.lines, line_no),
                    confidence=min(0.80, parser_cap),
                    validation_status="inferred",
                    discovery_method="cics-contract-extractor",
                    attributes={"verb": verb, "data_contract": contract, "commarea": contract.get("commarea")},
                )
            )
        layout_children = _layout_children_by_parent(analysis)
        for key in ("commarea", "resp", "resp2", "length", "channel", "container"):
            value = contract.get(key)
            if not value or str(value).isdigit():
                continue
            field_name = _clean_name(str(value))
            found.append(
                _found_existing(
                    item,
                    contract_asset,
                    "CONTRACT_USES_FIELD",
                    _field_asset(item.member.run_id, source.technical_name, field_name, confidence=0.74, validation_status="inferred"),
                    line_no,
                    _line_at(item.lines, line_no),
                    confidence=0.74,
                    validation_status="inferred",
                    discovery_method="cics-contract-extractor",
                    attributes={"contract_role": key, "verb": verb, "field": field_name, "line": line_no},
                )
            )
            if key == "commarea":
                for child in layout_children.get(field_name, []):
                    child_name = _clean_name(str(child.get("name") or ""))
                    if not child_name or child_name == field_name:
                        continue
                    found.append(
                        _found_existing(
                            item,
                            contract_asset,
                            "COMMAREA_CONTAINS_FIELD",
                            _field_asset(
                                item.member.run_id,
                                source.technical_name,
                                child_name,
                                confidence=0.72,
                                validation_status="inferred",
                                attributes={
                                    "commarea": field_name,
                                    "level": child.get("level"),
                                    "pic": child.get("pic"),
                                    "parent_field": child.get("parent"),
                                },
                            ),
                            int(child.get("line") or line_no),
                            _line_at(item.lines, int(child.get("line") or line_no)),
                            confidence=0.72,
                            validation_status="inferred",
                            discovery_method="cics-contract-extractor",
                            attributes={
                                "contract_role": "commarea_child",
                                "verb": verb,
                                "commarea": field_name,
                                "field": child_name,
                                "parent_field": child.get("parent"),
                                "line": int(child.get("line") or line_no),
                            },
                        )
                    )
    return found


def _layout_children_by_parent(analysis: dict[str, Any]) -> dict[str, list[dict[str, Any]]]:
    children: dict[str, list[dict[str, Any]]] = {}
    stack: list[dict[str, Any]] = []
    for row in analysis.get("data_items", []) or []:
        name = _clean_name(str(row.get("name") or ""))
        if not name:
            continue
        level = int(row.get("level") or 0)
        while stack and int(stack[-1].get("level") or 0) >= level:
            stack.pop()
        parent = _clean_name(str(stack[-1].get("name") or "")) if stack else ""
        enriched = dict(row)
        enriched["name"] = name
        enriched["parent"] = parent
        if parent:
            for ancestor in stack:
                ancestor_name = _clean_name(str(ancestor.get("name") or ""))
                if ancestor_name:
                    children.setdefault(ancestor_name, []).append(enriched)
        stack.append(enriched)
    return children


def _iter_exec_cics_blocks(text: str) -> list[dict[str, Any]]:
    return [
        {"body": match.group(1), "line": _line_for_offset(text, match.start()), "offset": match.start()}
        for match in re.finditer(r"(?is)\bEXEC\s+CICS\b(.*?)(?:END-EXEC\b|\;)", text)
    ]


def _file_record_maps(analysis: dict[str, Any]) -> tuple[dict[str, str], dict[str, str]]:
    record_to_file: dict[str, str] = {}
    field_to_record: dict[str, str] = {}
    current_file = ""
    current_record = ""
    for layout in analysis.get("data_layout", []) or []:
        if str(layout.get("section") or "").upper() != "FILE":
            continue
        for row in layout.get("items", []) or []:
            name = _clean_name(str(row.get("name") or ""))
            level = int(row.get("level") or 0)
            if not name:
                continue
            if level == 1:
                current_record = name
                if current_file:
                    record_to_file[current_record] = current_file
            elif current_record:
                field_to_record[name] = current_record
    return record_to_file, field_to_record


def _file_record_layout_relationships(
    item: ClassifiedMember,
    source: Asset,
    record_to_file: dict[str, str],
    field_to_record: dict[str, str],
) -> list[FoundRelationship]:
    found: list[FoundRelationship] = []
    current_file = ""
    current_record = ""
    for line_no, line in enumerate(item.lines, 1):
        if _is_cobol_comment(line):
            continue
        upper = line.upper()
        fd_match = re.match(r"^\s*FD\s+([A-Z0-9#$@_-]+)", upper)
        if fd_match:
            current_file = _clean_name(fd_match.group(1))
            current_record = ""
            continue
        data_match = re.match(r"^\s*(\d{2})\s+([A-Z0-9][A-Z0-9-]*)\b", upper)
        if not data_match or not current_file:
            continue
        level = int(data_match.group(1))
        name = _clean_name(data_match.group(2))
        if level == 1:
            current_record = name
            record_to_file.setdefault(current_record, current_file)
            record = _file_record_asset(item.member.run_id, source.technical_name, current_file, current_record)
            found.append(
                _found_existing(
                    item,
                    _asset(item.member.run_id, "FILE", current_file, confidence=0.82, validation_status="inferred"),
                    "HAS_RECORD_LAYOUT",
                    record,
                    line_no,
                    line,
                    confidence=0.82,
                    validation_status="inferred",
                    discovery_method="file-io-extractor",
                    attributes={"file": current_file, "record": current_record},
                )
            )
        elif current_record:
            field_to_record.setdefault(name, current_record)
            record = _file_record_asset(item.member.run_id, source.technical_name, current_file, current_record)
            found.append(
                _found_existing(
                    item,
                    record,
                    "RECORD_DECLARES_FIELD",
                    _field_asset(item.member.run_id, source.technical_name, name, confidence=0.80, validation_status="inferred"),
                    line_no,
                    line,
                    confidence=0.80,
                    validation_status="inferred",
                    discovery_method="file-io-extractor",
                    attributes={"file": current_file, "record": current_record, "field": name},
                )
            )
    return found


def _file_io_operations(lines: tuple[str, ...], record_to_file: dict[str, str]) -> list[dict[str, Any]]:
    operations: list[dict[str, Any]] = []
    for line_no, line in enumerate(lines, 1):
        if _is_cobol_comment(line):
            continue
        upper = line.upper()
        for mode, file_name in _open_file_modes(upper):
            operations.append(
                {
                    "line": line_no,
                    "verb": "OPEN",
                    "operation_kind": f"OPEN_{mode}",
                    "mode": mode,
                    "file": file_name,
                    "record": None,
                    "key": None,
                    "exception_handlers": _file_exception_handlers(upper),
                }
            )
        read = re.search(r"\bREAD\s+([A-Z0-9#$@_-]+)(.*)", upper)
        if read:
            tail = read.group(2)
            operations.append(
                {
                    "line": line_no,
                    "verb": "READ",
                    "operation_kind": "READ",
                    "mode": None,
                    "file": _clean_name(read.group(1)),
                    "record": _io_option(tail, "INTO"),
                    "key": _file_key(tail),
                    "exception_handlers": _file_exception_handlers(upper),
                }
            )
        for verb in ("WRITE", "REWRITE"):
            match = re.search(rf"\b{verb}\s+([A-Z0-9#$@_-]+)(.*)", upper)
            if not match:
                continue
            record = _clean_name(match.group(1))
            operations.append(
                {
                    "line": line_no,
                    "verb": verb,
                    "operation_kind": verb,
                    "mode": None,
                    "file": record_to_file.get(record, record),
                    "record": record,
                    "key": _file_key(match.group(2)),
                    "exception_handlers": _file_exception_handlers(upper),
                }
            )
        for verb in ("DELETE", "START", "CLOSE"):
            match = re.search(rf"\b{verb}\s+([A-Z0-9#$@_-]+)(.*)", upper)
            if not match:
                continue
            operations.append(
                {
                    "line": line_no,
                    "verb": verb,
                    "operation_kind": verb,
                    "mode": None,
                    "file": _clean_name(match.group(1)),
                    "record": None,
                    "key": _file_key(match.group(2)),
                    "exception_handlers": _file_exception_handlers(upper),
                }
            )
    return operations


def _open_file_modes(line: str) -> list[tuple[str, str]]:
    match = re.search(r"\bOPEN\b(.*)", line)
    if not match:
        return []
    modes = {"INPUT", "OUTPUT", "I-O", "EXTEND"}
    current_mode = "UNKNOWN"
    pairs: list[tuple[str, str]] = []
    for token in re.findall(r"[A-Z0-9#$@_-]+", match.group(1)):
        if token in modes:
            current_mode = token.replace("-", "_")
            continue
        if token in {"WITH", "NO", "REWIND", "REVERSED"}:
            continue
        pairs.append((current_mode, _clean_name(token)))
    return pairs


def _io_option(text: str, option: str) -> str | None:
    match = re.search(rf"\b{option}\s+([A-Z0-9#$@_-]+)", text, re.I)
    return _clean_name(match.group(1)) if match else None


def _file_key(text: str) -> str | None:
    match = re.search(r"\bKEY\s+(?:IS\s+|>=\s*|>\s*|=\s*)?([A-Z0-9#$@_-]+)", text, re.I)
    return _clean_name(match.group(1)) if match else None


def _file_exception_handlers(text: str) -> dict[str, bool]:
    upper = text.upper()
    return {
        "at_end": " AT END" in upper,
        "invalid_key": "INVALID KEY" in upper,
        "not_invalid_key": "NOT INVALID KEY" in upper,
    }


def _sort_merge_files(tail: str, keyword: str) -> list[str]:
    match = re.search(rf"\b{keyword}\b(.*?)(?=\b(?:USING|GIVING|INPUT|OUTPUT|ON|COLLATING)\b|$)", tail, re.I)
    if not match:
        return []
    return [_clean_name(name) for name in re.findall(r"\b[A-Z][A-Z0-9#$@_-]*\b", match.group(1), re.I) if _clean_name(name) not in {"FILE", "FILES"}]


def _sort_merge_keys(tail: str) -> list[str]:
    keys: list[str] = []
    for match in re.finditer(r"\bKEY\s+([A-Z0-9#$@_-]+)", tail, re.I):
        key = _clean_name(match.group(1))
        if key not in keys:
            keys.append(key)
    return keys


def _file_io_semantic_relationships(
    item: ClassifiedMember,
    source: Asset,
    analysis: dict[str, Any] | None = None,
) -> list[FoundRelationship]:
    found: list[FoundRelationship] = []
    record_to_file, field_to_record = _file_record_maps(analysis or {})
    found.extend(_file_record_layout_relationships(item, source, record_to_file, field_to_record))
    for operation in _file_io_operations(item.lines, record_to_file):
        line_no = operation["line"]
        line = _line_at(item.lines, line_no)
        op_asset = _file_io_asset(item.member.run_id, source.technical_name, operation)
        found.append(
            _found_existing(
                item,
                source,
                "DEFINES_FILE_IO",
                op_asset,
                line_no,
                line,
                confidence=0.78,
                validation_status="inferred",
                discovery_method="file-io-extractor",
                attributes=operation,
            )
        )
        rel_type = {
            "READ": "READS_FILE",
            "OPEN_INPUT": "READS_FILE",
            "WRITE": "WRITES_FILE",
            "REWRITE": "WRITES_FILE",
            "DELETE": "WRITES_FILE",
            "OPEN_OUTPUT": "WRITES_FILE",
            "OPEN_EXTEND": "WRITES_FILE",
        }.get(str(operation.get("operation_kind")), "USES_FILE")
        found.append(
            _found_existing(
                item,
                op_asset,
                rel_type,
                _asset(item.member.run_id, "FILE", str(operation["file"]), confidence=0.78, validation_status="inferred"),
                line_no,
                line,
                confidence=0.78,
                validation_status="inferred",
                discovery_method="file-io-extractor",
                attributes=operation,
            )
        )
    return found


def _sort_merge_relationships(item: ClassifiedMember, source: Asset) -> list[FoundRelationship]:
    found: list[FoundRelationship] = []
    for line_no, line in enumerate(item.lines, 1):
        if _is_cobol_comment(line):
            continue
        upper = line.upper()
        match = re.search(r"\b(SORT|MERGE)\s+([A-Z0-9#$@_-]+)\b(.*)", upper)
        if not match:
            continue
        verb = match.group(1)
        work_file = _clean_name(match.group(2))
        tail = match.group(3)
        operation = _sort_merge_asset(item.member.run_id, source.technical_name, verb, line_no, work_file, tail)
        attrs = {
            "verb": verb,
            "work_file": work_file,
            "input_files": _sort_merge_files(tail, "USING"),
            "output_files": _sort_merge_files(tail, "GIVING"),
            "keys": _sort_merge_keys(tail),
        }
        found.append(
            _found_existing(
                item,
                source,
                "DEFINES_SORT_MERGE",
                operation,
                line_no,
                line,
                confidence=0.82,
                validation_status="inferred",
                discovery_method="sort-merge-extractor",
                attributes=attrs,
            )
        )
        found.append(
            _found_existing(
                item,
                operation,
                "USES_FILE",
                _asset(item.member.run_id, "FILE", work_file, confidence=0.74, validation_status="inferred"),
                line_no,
                line,
                confidence=0.74,
                validation_status="inferred",
                discovery_method="sort-merge-extractor",
                attributes={**attrs, "role": "work"},
            )
        )
        for file_name in attrs["input_files"]:
            found.append(
                _found_existing(
                    item,
                    operation,
                    "READS_FILE",
                    _asset(item.member.run_id, "FILE", file_name, confidence=0.76, validation_status="inferred"),
                    line_no,
                    line,
                    confidence=0.76,
                    validation_status="inferred",
                    discovery_method="sort-merge-extractor",
                    attributes={**attrs, "role": "input"},
                )
            )
        for file_name in attrs["output_files"]:
            found.append(
                _found_existing(
                    item,
                    operation,
                    "WRITES_FILE",
                    _asset(item.member.run_id, "FILE", file_name, confidence=0.76, validation_status="inferred"),
                    line_no,
                    line,
                    confidence=0.76,
                    validation_status="inferred",
                    discovery_method="sort-merge-extractor",
                    attributes={**attrs, "role": "output"},
                )
            )
    return found


def _interface_contract_relationships(
    item: ClassifiedMember,
    source: Asset,
    analysis: dict[str, Any],
    parser_cap: float,
) -> list[FoundRelationship]:
    found: list[FoundRelationship] = []
    entry_args = _procedure_using_args(item.text)
    linkage_fields = _linkage_top_level_fields(analysis)
    contract_args = entry_args or linkage_fields
    if contract_args:
        entry = _interface_contract_asset(
            item.member.run_id,
            source.technical_name,
            "ENTRY",
            0,
            source.technical_name,
            {"contract_kind": "program_entry", "procedure_using": entry_args, "linkage_fields": linkage_fields},
            confidence=min(0.86, parser_cap),
        )
        line_no = _line_for_text(item.lines, "PROCEDURE DIVISION") or 1
        found.append(
            _found_existing(
                item,
                source,
                "DECLARES_ENTRY_CONTRACT",
                entry,
                line_no,
                _line_at(item.lines, line_no),
                confidence=min(0.86, parser_cap),
                validation_status="inferred",
                discovery_method="interface-contract-extractor",
                attributes=entry.attributes,
            )
        )
        for position, arg in enumerate(contract_args, 1):
            field = _field_asset(item.member.run_id, source.technical_name, arg["name"], confidence=0.78, validation_status="inferred")
            attrs = {
                "contract_kind": "program_entry",
                "argument_position": position,
                "argument_name": arg["name"],
                "field": arg["name"],
                "mode": arg.get("mode") or "REFERENCE",
            }
            found.append(
                _found_existing(
                    item,
                    entry,
                    "ENTRY_CONTRACT_USES_FIELD",
                    field,
                    int(arg.get("line") or line_no),
                    _line_at(item.lines, int(arg.get("line") or line_no)),
                    confidence=0.78,
                    validation_status="inferred",
                    discovery_method="interface-contract-extractor",
                    attributes=attrs,
                )
            )
            found.append(
                _found_existing(
                    item,
                    entry,
                    "CONTRACT_USES_FIELD",
                    field,
                    int(arg.get("line") or line_no),
                    _line_at(item.lines, int(arg.get("line") or line_no)),
                    confidence=0.78,
                    validation_status="inferred",
                    discovery_method="interface-contract-extractor",
                    attributes={**attrs, "contract_role": "entry_argument"},
                )
            )

    for line_no, call_contract in _call_contracts_by_line(item.lines).items():
        target = call_contract.get("target")
        args = call_contract.get("arguments", [])
        if not target or not args:
            continue
        contract = _interface_contract_asset(
            item.member.run_id,
            source.technical_name,
            "CALL",
            line_no,
            str(target),
            {"contract_kind": "call_site", "target_program": target, "arguments": args},
            confidence=min(0.84, parser_cap),
        )
        line = _line_at(item.lines, line_no)
        found.append(
            _found_existing(
                item,
                source,
                "DEFINES_CALL_CONTRACT",
                contract,
                line_no,
                line,
                confidence=min(0.84, parser_cap),
                validation_status="inferred",
                discovery_method="interface-contract-extractor",
                attributes=contract.attributes,
            )
        )
        found.append(
            _found_existing(
                item,
                contract,
                "CALL_CONTRACT_TARGETS",
                _asset(item.member.run_id, "PROGRAM", str(target), confidence=0.80, validation_status="inferred"),
                line_no,
                line,
                confidence=0.80,
                validation_status="inferred",
                discovery_method="interface-contract-extractor",
                attributes={"target_program": target, "line": line_no},
            )
        )
        for arg in args:
            position = int(arg.get("position") or 0)
            field_name = str(arg.get("name") or "")
            if not field_name:
                continue
            field = _field_asset(item.member.run_id, source.technical_name, field_name, confidence=0.78, validation_status="inferred")
            attrs = {
                "contract_kind": "call_site",
                "target_program": target,
                "argument_position": position,
                "argument_name": field_name,
                "field": field_name,
                "mode": arg.get("mode") or "REFERENCE",
                "line": line_no,
            }
            found.append(
                _found_existing(
                    item,
                    contract,
                    "CALL_PASSES_FIELD",
                    field,
                    line_no,
                    line,
                    confidence=0.78,
                    validation_status="inferred",
                    discovery_method="interface-contract-extractor",
                    attributes=attrs,
                )
            )
            found.append(
                _found_existing(
                    item,
                    contract,
                    "CONTRACT_USES_FIELD",
                    field,
                    line_no,
                    line,
                    confidence=0.78,
                    validation_status="inferred",
                    discovery_method="interface-contract-extractor",
                    attributes={**attrs, "contract_role": "call_argument"},
                )
            )
    return found


def _call_argument_mapping_relationships(
    members: list[ClassifiedMember],
    member_assets: dict[str, Asset],
    cobol_analysis: dict[str, dict[str, Any]],
) -> list[FoundRelationship]:
    found: list[FoundRelationship] = []
    programs_by_name: dict[str, tuple[ClassifiedMember, Asset, dict[str, Any]]] = {}
    for item in members:
        analysis = cobol_analysis.get(item.member.member_id)
        if not analysis:
            continue
        asset = member_assets[item.member.member_id]
        if asset.asset_type == "PROGRAM":
            programs_by_name[_clean_name(asset.technical_name)] = (item, asset, analysis)

    for item in members:
        analysis = cobol_analysis.get(item.member.member_id)
        if not analysis:
            continue
        caller = member_assets[item.member.member_id]
        for line_no, call_contract in _call_contracts_by_line(item.lines).items():
            target = _clean_name(str(call_contract.get("target") or ""))
            callee_tuple = programs_by_name.get(target)
            if not target or callee_tuple is None:
                continue
            _, callee, callee_analysis = callee_tuple
            caller_args = call_contract.get("arguments", [])
            callee_args = _procedure_using_args("\n".join(callee_analysis.get("source_lines", []))) or _linkage_top_level_fields(callee_analysis)
            if not callee_args:
                continue
            line = _line_at(item.lines, line_no)
            for position, caller_arg in enumerate(caller_args, 1):
                if position > len(callee_args):
                    break
                caller_field_name = _clean_name(str(caller_arg.get("name") or ""))
                callee_field_name = _clean_name(str(callee_args[position - 1].get("name") or ""))
                if not caller_field_name or not callee_field_name:
                    continue
                caller_field = _field_asset(item.member.run_id, caller.technical_name, caller_field_name, confidence=0.72, validation_status="inferred")
                callee_field = _field_asset(item.member.run_id, callee.technical_name, callee_field_name, confidence=0.72, validation_status="inferred")
                found.append(
                    FoundRelationship(
                        relationship_type="CALL_ARGUMENT_MAPS_TO_LINKAGE",
                        source_asset_id=caller_field.asset_id,
                        source_asset=caller_field,
                        target=callee_field,
                        evidence=Evidence(
                            source_path=item.member.relative_path,
                            line_start=line_no,
                            line_end=line_no,
                            evidence_text=line.strip()[:500],
                            extractor=EXTRACTOR,
                            discovery_method="interface-contract-extractor",
                            confidence=0.72,
                            validation_status="inferred",
                        ),
                        confidence=0.72,
                        validation_status="inferred",
                        discovery_method="interface-contract-extractor",
                        attributes={
                            "caller_program": caller.technical_name,
                            "callee_program": callee.technical_name,
                            "call_line": line_no,
                            "argument_position": position,
                            "caller_field": caller_field_name,
                            "callee_field": callee_field_name,
                            "mapping_basis": "positional_call_using_to_procedure_linkage",
                        },
                    )
                )
    return found


def _interface_contract_asset(
    run_id: str,
    program_name: str,
    kind: str,
    line_no: int,
    target: str,
    attributes: dict[str, Any],
    *,
    confidence: float,
) -> Asset:
    program = _clean_name(program_name)
    contract_kind = _clean_name(kind)
    target_name = _clean_name(target)
    digest = stable_id("interface_contract", program, contract_kind, line_no, target_name, attributes)
    return Asset(
        run_id=run_id,
        asset_type="INTERFACE_CONTRACT",
        technical_name=f"{program}::{contract_kind}::{line_no}::{target_name}::{digest}",
        display_name=f"{contract_kind} {target_name}",
        confidence=confidence,
        validation_status="inferred",
        discovery_method="interface-contract-extractor",
        attributes={"program": program, "line": line_no, **attributes},
    )


def _call_using_by_line(lines: tuple[str, ...]) -> dict[int, list[str]]:
    return {
        line_no: [arg["name"] for arg in contract.get("arguments", [])]
        for line_no, contract in _call_contracts_by_line(lines).items()
    }


def _call_contracts_by_line(lines: tuple[str, ...]) -> dict[int, dict[str, Any]]:
    contracts: dict[int, dict[str, Any]] = {}
    for statement in _cobol_logical_statements(lines):
        text = statement["text"]
        match = re.search(
            r"\bCALL\s+(?:['\"]([A-Z0-9#$@_-]+)['\"]|([A-Z][A-Z0-9#$@_-]+))(?:\s+USING\s+(.+))?",
            text,
            re.I | re.S,
        )
        if not match:
            continue
        target = _clean_name(match.group(1) or match.group(2) or "")
        args_text = match.group(3) or ""
        contracts[int(statement["line"])] = {
            "target": target,
            "arguments": _parse_using_arguments(args_text, int(statement["line"])),
            "text": text,
        }
    return contracts


def _procedure_using_args(text: str) -> list[dict[str, Any]]:
    match = re.search(r"\bPROCEDURE\s+DIVISION(?:\s+USING\s+(.+?))?\.", text, re.I | re.S)
    if not match or not match.group(1):
        return []
    line_no = _line_for_offset(text, match.start())
    return _parse_using_arguments(match.group(1), line_no)


def _parse_using_arguments(text: str, line_no: int) -> list[dict[str, Any]]:
    cleaned = re.sub(r"\.", " ", text)
    tokens = [_clean_name(token) for token in re.findall(r"[A-Z0-9#$@_-]+", cleaned, re.I)]
    args: list[dict[str, Any]] = []
    mode = "REFERENCE"
    skip_next_mode = False
    for token in tokens:
        if not token:
            continue
        if token == "BY":
            skip_next_mode = True
            continue
        if token in {"REFERENCE", "CONTENT", "VALUE"}:
            mode = token
            skip_next_mode = False
            continue
        if skip_next_mode:
            skip_next_mode = False
        if token in {"ADDRESS", "LENGTH", "OMITTED", "NULL"}:
            continue
        args.append({"position": len(args) + 1, "name": token, "mode": mode, "line": line_no})
    return args


def _linkage_top_level_fields(analysis: dict[str, Any]) -> list[dict[str, Any]]:
    fields = []
    for row in analysis.get("data_items", []) or []:
        if str(row.get("section") or "").upper() != "LINKAGE":
            continue
        if int(row.get("level") or 0) not in {1, 77}:
            continue
        name = _clean_name(str(row.get("name") or ""))
        if name:
            fields.append({"position": len(fields) + 1, "name": name, "mode": "REFERENCE", "line": int(row.get("line") or 1)})
    return fields


def _cobol_logical_statements(lines: tuple[str, ...]) -> list[dict[str, Any]]:
    statements: list[dict[str, Any]] = []
    current: dict[str, Any] | None = None
    in_procedure = False
    for line_no, line in enumerate(lines, 1):
        if _is_cobol_comment(line):
            continue
        upper = line.upper()
        if "PROCEDURE DIVISION" in upper:
            in_procedure = True
        if not in_procedure:
            continue
        stripped = line.strip()
        if not stripped:
            continue
        if current is None:
            current = {"line": line_no, "text": stripped}
        else:
            current["text"] = f"{current['text']} {stripped}"
        if "." in stripped:
            statements.append(current)
            current = None
    if current is not None:
        statements.append(current)
    return statements


def _cics_data_contract(line: str) -> dict[str, Any]:
    upper = line.upper()
    contract: dict[str, Any] = {}
    for key in ("COMMAREA", "CHANNEL", "CONTAINER", "QUEUE", "QNAME", "MAP", "FILE", "DATASET", "TRANSID", "RESP", "RESP2"):
        match = re.search(rf"\b{key}\s*\(\s*['\"]?([A-Z0-9#$@_-]+)", upper)
        if match:
            contract[key.lower()] = _clean_name(match.group(1))
    length = re.search(r"\bLENGTH\s*\(\s*([A-Z0-9#$@_-]+|\d+)", upper)
    if length:
        contract["length"] = _clean_name(length.group(1))
    return contract


def _embedded_sql_relationships(
    item: ClassifiedMember,
    source: Asset,
    *,
    confidence: float = 0.88,
    discovery_method: str = "observed",
) -> list[FoundRelationship]:
    found: list[FoundRelationship] = []
    seen: set[tuple[str, str, str, str]] = set()
    for block in _iter_exec_sql_blocks(item.text):
        for rel in _db2_dml_relationships(item, source, block["body"], block["line"], confidence, discovery_method):
            _append_found(found, seen, rel)
    for rel in _db2_include_relationships(item, source, item.text, embedded=True, confidence=confidence):
        _append_found(found, seen, rel)
    for rel in _db2_statement_relationships(item, source, item.text, embedded=True, confidence=confidence):
        _append_found(found, seen, rel)
    for rel in _db2_cursor_relationships(item, source, item.text, embedded=True, confidence=confidence):
        _append_found(found, seen, rel)
    for rel in _db2_package_relationships(item, source, item.text, confidence=confidence):
        _append_found(found, seen, rel)
    return found


def _iter_exec_sql_blocks(text: str) -> list[dict[str, Any]]:
    blocks: list[dict[str, Any]] = []
    for match in re.finditer(r"(?is)\bEXEC\s+SQL\b(.*?)(?:END-EXEC\b|\;)", text):
        blocks.append({"body": match.group(1), "line": _line_for_offset(text, match.start()), "offset": match.start()})
    return blocks


def _db2_dml_relationships(
    item: ClassifiedMember,
    source: Asset,
    sql_body: str,
    line_no: int,
    confidence: float,
    discovery_method: str,
) -> list[FoundRelationship]:
    found: list[FoundRelationship] = []
    body = _strip_sql_comments(sql_body)
    for table in _db2_select_tables(body):
        found.append(
            _found(
                item,
                source,
                "READS_TABLE",
                "TABLE",
                table,
                line_no,
                _line_at(item.lines, line_no),
                confidence=confidence,
                validation_status="confirmed" if confidence >= 0.9 else "inferred",
                discovery_method=discovery_method,
                attributes={"dialect": "DB2", "statement": "SELECT", "host_vars": _db2_host_vars(body)},
            )
        )
    for rel_type, pattern, statement in (
        ("WRITES_TABLE", r"\bINSERT\s+INTO\s+([A-Z0-9_.$#@]+)", "INSERT"),
        ("WRITES_TABLE", r"\bUPDATE\s+([A-Z0-9_.$#@]+)", "UPDATE"),
        ("WRITES_TABLE", r"\bDELETE\s+FROM\s+([A-Z0-9_.$#@]+)", "DELETE"),
        ("WRITES_TABLE", r"\bMERGE\s+INTO\s+([A-Z0-9_.$#@]+)", "MERGE"),
    ):
        for match in re.finditer(pattern, body, re.I):
            found.append(
                _found(
                    item,
                    source,
                    rel_type,
                    "TABLE",
                    match.group(1),
                    line_no,
                    _line_at(item.lines, line_no),
                    confidence=confidence,
                    validation_status="confirmed" if confidence >= 0.9 else "inferred",
                    discovery_method=discovery_method,
                    attributes={"dialect": "DB2", "statement": statement, "host_vars": _db2_host_vars(body)},
                )
            )
    return found


def _db2_statement_relationships(
    item: ClassifiedMember,
    source: Asset,
    text: str,
    *,
    embedded: bool,
    confidence: float = 0.86,
) -> list[FoundRelationship]:
    found: list[FoundRelationship] = []
    for statement in _db2_sql_statements(text, embedded=embedded):
        body = _strip_sql_comments(statement["body"])
        kind = _db2_statement_kind(body)
        if kind not in {"SELECT", "INSERT", "UPDATE", "DELETE", "MERGE", "DECLARE_CURSOR", "FETCH"}:
            continue
        line_no = int(statement["line"] or 1)
        statement_asset = _db2_statement_asset(item.member.run_id, source.technical_name, kind, line_no, body, confidence)
        tables = _db2_statement_tables(body, kind)
        aliases = _db2_table_aliases(body)
        read_columns = _db2_select_columns(body, tables, aliases) if kind in {"SELECT", "DECLARE_CURSOR"} else []
        predicate_columns = _db2_predicate_columns(body, tables, aliases)
        join_columns = _db2_join_columns(body, tables, aliases)
        write_columns = _db2_write_columns(body, kind, tables, aliases)
        output_hosts = _db2_output_host_vars(body, kind)
        all_hosts = _db2_host_vars(body)
        input_hosts = [host for host in all_hosts if host not in output_hosts]
        attrs = {
            "dialect": "DB2",
            "statement_kind": kind,
            "embedded": embedded,
            "tables": tables,
            "read_columns": read_columns,
            "write_columns": write_columns,
            "predicate_columns": predicate_columns,
            "join_columns": join_columns,
            "input_host_vars": input_hosts,
            "output_host_vars": output_hosts,
            "query_shape": _db2_query_shape(body),
            "table_aliases": aliases,
        }
        found.append(
            _found_existing(
                item,
                source,
                "DEFINES_DB2_STATEMENT",
                statement_asset,
                line_no,
                _line_at(item.lines, line_no),
                confidence=confidence,
                validation_status="inferred",
                discovery_method="db2-statement-model",
                attributes=attrs,
            )
        )
        for table in tables:
            rel_type = "STATEMENT_WRITES_TABLE" if kind in {"INSERT", "UPDATE", "DELETE", "MERGE"} else "STATEMENT_READS_TABLE"
            found.append(
                _found_existing(
                    item,
                    statement_asset,
                    rel_type,
                    _asset(item.member.run_id, "TABLE", table, confidence=confidence, validation_status="inferred"),
                    line_no,
                    _line_at(item.lines, line_no),
                    confidence=confidence,
                    validation_status="inferred",
                    discovery_method="db2-statement-model",
                    attributes={"statement_kind": kind},
                )
            )
        for column in read_columns:
            found.append(
                _found_existing(
                    item,
                    statement_asset,
                    "STATEMENT_READS_COLUMN",
                    _field_asset(item.member.run_id, source.technical_name, column, confidence=0.80, validation_status="inferred"),
                    line_no,
                    _line_at(item.lines, line_no),
                    confidence=0.80,
                    validation_status="inferred",
                    discovery_method="db2-statement-model",
                    attributes={"statement_kind": kind, "column_role": "select_list"},
                )
            )
        for column in write_columns:
            found.append(
                _found_existing(
                    item,
                    statement_asset,
                    "STATEMENT_WRITES_COLUMN",
                    _field_asset(item.member.run_id, source.technical_name, column, confidence=0.78, validation_status="inferred"),
                    line_no,
                    _line_at(item.lines, line_no),
                    confidence=0.78,
                    validation_status="inferred",
                    discovery_method="db2-statement-model",
                    attributes={"statement_kind": kind, "column_role": "write_target"},
                )
            )
        for column in predicate_columns:
            found.append(
                _found_existing(
                    item,
                    statement_asset,
                    "STATEMENT_FILTERS_BY_COLUMN",
                    _field_asset(item.member.run_id, source.technical_name, column, confidence=0.76, validation_status="inferred"),
                    line_no,
                    _line_at(item.lines, line_no),
                    confidence=0.76,
                    validation_status="inferred",
                    discovery_method="db2-statement-model",
                    attributes={"statement_kind": kind, "column_role": "predicate"},
                )
            )
        for column in join_columns:
            found.append(
                _found_existing(
                    item,
                    statement_asset,
                    "STATEMENT_JOINS_ON_COLUMN",
                    _field_asset(item.member.run_id, source.technical_name, column, confidence=0.76, validation_status="inferred"),
                    line_no,
                    _line_at(item.lines, line_no),
                    confidence=0.76,
                    validation_status="inferred",
                    discovery_method="db2-statement-model",
                    attributes={"statement_kind": kind, "column_role": "join"},
                )
            )
        for host in input_hosts:
            found.append(_db2_host_var_edge(item, statement_asset, source.technical_name, host, "STATEMENT_INPUTS_FROM_HOST_VARIABLE", line_no, kind, 0.78))
        for host in output_hosts:
            found.append(_db2_host_var_edge(item, statement_asset, source.technical_name, host, "STATEMENT_OUTPUTS_TO_HOST_VARIABLE", line_no, kind, 0.80))
        for host, column in _db2_host_column_bindings(output_hosts, read_columns):
            found.append(_db2_host_column_edge(item, source.technical_name, host, column, line_no, kind, "select_into", 0.78))
        for host in input_hosts:
            for column in predicate_columns:
                found.append(_db2_host_column_edge(item, source.technical_name, host, column, line_no, kind, "predicate", 0.62))
    return found


def _db2_cursor_relationships(
    item: ClassifiedMember,
    source: Asset,
    text: str,
    *,
    embedded: bool,
    confidence: float = 0.90,
) -> list[FoundRelationship]:
    found: list[FoundRelationship] = []
    statements = _db2_sql_statements(text, embedded=embedded)
    cursor_tables: dict[str, list[str]] = {}
    cursor_columns: dict[str, list[str]] = {}
    for statement in statements:
        body = statement["body"]
        line_no = statement["line"]
        declare = re.search(
            r"\bDECLARE\s+([A-Z0-9_#$@-]+)\s+CURSOR(?:\s+WITH\s+HOLD)?\s+FOR\s+(SELECT\b.*)",
            body,
            re.I | re.S,
        )
        if not declare:
            continue
        cursor_name = _clean_name(declare.group(1))
        query = declare.group(2)
        tables = _db2_select_tables(query)
        aliases = _db2_table_aliases(query)
        columns = _db2_select_columns(query, tables, aliases)
        cursor_tables[cursor_name] = tables
        cursor_columns[cursor_name] = columns
        cursor = _db2_cursor_asset(item.member.run_id, source.technical_name, cursor_name, confidence=confidence)
        attrs = {
            "dialect": "DB2",
            "statement": "DECLARE CURSOR",
            "cursor_name": cursor_name,
            "tables": tables,
            "columns": columns,
            "predicate_columns": _db2_predicate_columns(query, tables, aliases),
            "join_columns": _db2_join_columns(query, tables, aliases),
            "host_vars": _db2_host_vars(query),
            "query_shape": _db2_query_shape(query),
            "table_aliases": aliases,
        }
        found.append(
            _found_existing(
                item,
                source,
                "DEFINES_DB2_CURSOR",
                cursor,
                line_no,
                _line_at(item.lines, line_no),
                confidence=confidence,
                validation_status="confirmed" if confidence >= 0.9 else "inferred",
                discovery_method="observed",
                attributes=attrs,
            )
        )
        for table in tables:
            found.append(
                _found_existing(
                    item,
                    cursor,
                    "CURSOR_READS_TABLE",
                    _asset(item.member.run_id, "TABLE", table, confidence=confidence, validation_status="confirmed"),
                    line_no,
                    _line_at(item.lines, line_no),
                    confidence=confidence,
                    validation_status="confirmed" if confidence >= 0.9 else "inferred",
                    discovery_method="observed",
                    attributes={"cursor_name": cursor_name, "dialect": "DB2"},
                )
            )
        for column in columns:
            found.append(
                _found_existing(
                    item,
                    cursor,
                    "CURSOR_READS_COLUMN",
                    _field_asset(item.member.run_id, source.technical_name, column, confidence=0.82, validation_status="inferred"),
                    line_no,
                    _line_at(item.lines, line_no),
                    confidence=0.82,
                    validation_status="inferred",
                    discovery_method="observed",
                    attributes={"cursor_name": cursor_name, "dialect": "DB2", "column_role": "select_list"},
                )
            )
        for column in attrs["predicate_columns"]:
            found.append(
                _found_existing(
                    item,
                    cursor,
                    "CURSOR_FILTERS_BY_COLUMN",
                    _field_asset(item.member.run_id, source.technical_name, column, confidence=0.78, validation_status="inferred"),
                    line_no,
                    _line_at(item.lines, line_no),
                    confidence=0.78,
                    validation_status="inferred",
                    discovery_method="observed",
                    attributes={"cursor_name": cursor_name, "dialect": "DB2", "column_role": "predicate"},
                )
            )
        for column in attrs["join_columns"]:
            found.append(
                _found_existing(
                    item,
                    cursor,
                    "CURSOR_JOINS_ON_COLUMN",
                    _field_asset(item.member.run_id, source.technical_name, column, confidence=0.76, validation_status="inferred"),
                    line_no,
                    _line_at(item.lines, line_no),
                    confidence=0.76,
                    validation_status="inferred",
                    discovery_method="observed",
                    attributes={"cursor_name": cursor_name, "dialect": "DB2", "column_role": "join"},
                )
            )
    for statement in statements:
        body = statement["body"]
        line_no = statement["line"]
        for verb, rel_type in (
            ("OPEN", "OPENS_DB2_CURSOR"),
            ("CLOSE", "CLOSES_DB2_CURSOR"),
        ):
            for match in re.finditer(rf"\b{verb}\s+([A-Z0-9_#$@-]+)", body, re.I):
                cursor_name = _clean_name(match.group(1))
                found.append(
                    _found_existing(
                        item,
                        source,
                        rel_type,
                        _db2_cursor_asset(item.member.run_id, source.technical_name, cursor_name, confidence=0.82),
                        line_no,
                        _line_at(item.lines, line_no),
                        confidence=0.82,
                        validation_status="inferred",
                        discovery_method="observed",
                        attributes={"cursor_name": cursor_name, "dialect": "DB2"},
                    )
                )
        for match in re.finditer(r"\bFETCH\s+([A-Z0-9_#$@-]+)(?:\s+INTO\s+(.+))?", body, re.I | re.S):
            cursor_name = _clean_name(match.group(1))
            host_vars = _db2_host_vars(match.group(2) or "")
            found.append(
                _found_existing(
                    item,
                    source,
                    "FETCHES_DB2_CURSOR",
                    _db2_cursor_asset(item.member.run_id, source.technical_name, cursor_name, confidence=0.84),
                    line_no,
                    _line_at(item.lines, line_no),
                    confidence=0.84,
                    validation_status="inferred",
                    discovery_method="observed",
                    attributes={
                        "cursor_name": cursor_name,
                        "dialect": "DB2",
                        "host_vars": host_vars,
                        "tables": cursor_tables.get(cursor_name, []),
                        "columns": cursor_columns.get(cursor_name, []),
                    },
                )
            )
    return found


def _db2_package_relationships(
    item: ClassifiedMember,
    source: Asset,
    text: str,
    *,
    confidence: float = 0.88,
) -> list[FoundRelationship]:
    found: list[FoundRelationship] = []
    clean = _strip_sql_comments(text)
    for match in re.finditer(r"\bBIND\s+PACKAGE\s*\(([^)]+)\)(.*?)(?=;|\n//|\Z)", clean, re.I | re.S):
        line_no = _line_for_offset(clean, match.start())
        package_name = _clean_name(match.group(1))
        tail = match.group(2)
        package = _asset(item.member.run_id, "DB2_PACKAGE", package_name, confidence=confidence, validation_status="inferred")
        attrs = {
            "dialect": "DB2",
            "statement": "BIND PACKAGE",
            "package": package_name,
            "member": _db2_option_value(tail, "MEMBER"),
            "collection": _db2_option_value(tail, "COLLECTION"),
            "qualifier": _db2_option_value(tail, "QUALIFIER"),
            "owner": _db2_option_value(tail, "OWNER"),
            "action": _db2_option_value(tail, "ACTION"),
            "isolation": _db2_option_value(tail, "ISOLATION"),
        }
        found.append(
            _found_existing(
                item,
                source,
                "DEFINES_DB2_PACKAGE",
                package,
                line_no,
                _line_at(item.lines, line_no),
                confidence=confidence,
                validation_status="inferred",
                discovery_method="observed",
                attributes=attrs,
            )
        )
        if attrs["member"]:
            found.append(
                _found_existing(
                    item,
                    package,
                    "BINDS_PROGRAM",
                    _asset(item.member.run_id, "PROGRAM", attrs["member"], confidence=0.78, validation_status="inferred"),
                    line_no,
                    _line_at(item.lines, line_no),
                    confidence=0.78,
                    validation_status="inferred",
                    discovery_method="observed",
                    attributes={"package": package_name, "member": attrs["member"]},
                )
            )
    for match in re.finditer(r"\bBIND\s+PLAN\s*\(([^)]+)\)(.*?)(?=;|\n//|\Z)", clean, re.I | re.S):
        line_no = _line_for_offset(clean, match.start())
        plan_name = _clean_name(match.group(1))
        tail = match.group(2)
        packages = [_clean_name(item) for item in _db2_option_list(tail, "PKLIST")]
        plan = _asset(item.member.run_id, "DB2_PLAN", plan_name, confidence=confidence, validation_status="inferred")
        found.append(
            _found_existing(
                item,
                source,
                "DEFINES_DB2_PLAN",
                plan,
                line_no,
                _line_at(item.lines, line_no),
                confidence=confidence,
                validation_status="inferred",
                discovery_method="observed",
                attributes={
                    "dialect": "DB2",
                    "statement": "BIND PLAN",
                    "plan": plan_name,
                    "packages": packages,
                    "owner": _db2_option_value(tail, "OWNER"),
                    "action": _db2_option_value(tail, "ACTION"),
                },
            )
        )
        for package_name in packages:
            found.append(
                _found_existing(
                    item,
                    plan,
                    "USES_DB2_PACKAGE",
                    _asset(item.member.run_id, "DB2_PACKAGE", package_name, confidence=0.78, validation_status="inferred"),
                    line_no,
                    _line_at(item.lines, line_no),
                    confidence=0.78,
                    validation_status="inferred",
                    discovery_method="observed",
                    attributes={"plan": plan_name, "package": package_name},
                )
            )
    return found


def _db2_include_relationships(
    item: ClassifiedMember,
    source: Asset,
    text: str,
    *,
    embedded: bool,
    confidence: float = 0.84,
) -> list[FoundRelationship]:
    found: list[FoundRelationship] = []
    for statement in _db2_sql_statements(text, embedded=embedded):
        body = _strip_sql_comments(statement["body"])
        line_no = int(statement["line"] or 1)
        for match in re.finditer(r"\bINCLUDE\s+([A-Z0-9_#$@.-]+)", body, re.I):
            dclgen = _clean_name(match.group(1))
            found.append(
                _found(
                    item,
                    source,
                    "USES_DCLGEN",
                    "DCLGEN",
                    dclgen,
                    line_no,
                    _line_at(item.lines, line_no),
                    confidence=confidence,
                    validation_status="inferred",
                    discovery_method="db2-dclgen-extractor",
                    attributes={"dialect": "DB2", "statement": "INCLUDE", "dclgen": dclgen},
                )
            )
    return found


def _db2_sql_statements(text: str, *, embedded: bool) -> list[dict[str, Any]]:
    if embedded:
        return _iter_exec_sql_blocks(text)
    clean = _strip_sql_comments(text)
    statements = []
    offset = 0
    for raw in re.split(r";", clean):
        stripped = raw.strip()
        if stripped:
            statements.append({"body": stripped, "line": _line_for_offset(clean, offset), "offset": offset})
        offset += len(raw) + 1
    return statements


def _db2_cursor_asset(run_id: str, owner_name: str, cursor_name: str, *, confidence: float) -> Asset:
    owner = _clean_name(owner_name)
    cursor = _clean_name(cursor_name)
    return Asset(
        run_id=run_id,
        asset_type="DB2_CURSOR",
        technical_name=f"{owner}::{cursor}",
        display_name=cursor,
        confidence=confidence,
        validation_status="confirmed" if confidence >= 0.9 else "inferred",
        discovery_method="observed",
        attributes={"owner": owner, "cursor_name": cursor},
    )


def _db2_statement_asset(
    run_id: str,
    owner_name: str,
    kind: str,
    line_no: int,
    body: str,
    confidence: float,
) -> Asset:
    owner = _clean_name(owner_name)
    digest = hashlib.sha1(" ".join(body.split()).encode("utf-8", errors="replace")).hexdigest()[:10]
    name = f"{owner}::SQL::{line_no}::{kind}::{digest}"
    return Asset(
        run_id=run_id,
        asset_type="DB2_STATEMENT",
        technical_name=name,
        display_name=f"{kind} line {line_no}",
        confidence=confidence,
        validation_status="inferred",
        discovery_method="db2-statement-model",
        attributes={
            "owner": owner,
            "statement_kind": kind,
            "line": line_no,
            "fingerprint": digest,
        },
    )


def _host_variable_asset(run_id: str, owner_name: str, host_var: str, *, confidence: float) -> Asset:
    owner = _clean_name(owner_name)
    name = _clean_name(host_var)
    return Asset(
        run_id=run_id,
        asset_type="HOST_VARIABLE",
        technical_name=f"{owner}::{name}",
        display_name=name,
        confidence=confidence,
        validation_status="inferred",
        discovery_method="db2-statement-model",
        attributes={"owner": owner, "host_variable": name},
    )


def _db2_host_var_edge(
    item: ClassifiedMember,
    statement_asset: Asset,
    owner_name: str,
    host_var: str,
    relationship_type: str,
    line_no: int,
    kind: str,
    confidence: float,
) -> FoundRelationship:
    host = _host_variable_asset(item.member.run_id, owner_name, host_var, confidence=confidence)
    return _found_existing(
        item,
        statement_asset,
        relationship_type,
        host,
        line_no,
        _line_at(item.lines, line_no),
        confidence=confidence,
        validation_status="inferred",
        discovery_method="db2-statement-model",
        attributes={"statement_kind": kind, "host_variable": _clean_name(host_var)},
    )


def _db2_host_column_edge(
    item: ClassifiedMember,
    owner_name: str,
    host_var: str,
    column: str,
    line_no: int,
    kind: str,
    binding_kind: str,
    confidence: float,
) -> FoundRelationship:
    host = _host_variable_asset(item.member.run_id, owner_name, host_var, confidence=confidence)
    column_asset = _field_asset(item.member.run_id, owner_name, column, confidence=confidence, validation_status="inferred")
    return FoundRelationship(
        relationship_type="HOST_VARIABLE_BINDS_COLUMN",
        source_asset_id=host.asset_id,
        source_asset=host,
        target=column_asset,
        evidence=Evidence(
            source_path=item.member.relative_path,
            line_start=line_no,
            line_end=line_no,
            evidence_text=_line_at(item.lines, line_no).strip()[:500],
            extractor=EXTRACTOR,
            discovery_method="db2-statement-model",
            confidence=confidence,
            validation_status="inferred",
        ),
        confidence=confidence,
        validation_status="inferred",
        discovery_method="db2-statement-model",
        attributes={
            "statement_kind": kind,
            "binding_kind": binding_kind,
            "host_variable": _clean_name(host_var),
            "column": _clean_name(column),
        },
    )


def _db2_statement_kind(body: str) -> str:
    upper = body.upper()
    if re.search(r"\bDECLARE\s+[A-Z0-9_#$@-]+\s+CURSOR\b", upper):
        return "DECLARE_CURSOR"
    if re.search(r"\bFETCH\s+[A-Z0-9_#$@-]+", upper):
        return "FETCH"
    for kind in ("SELECT", "INSERT", "UPDATE", "DELETE", "MERGE"):
        if re.search(rf"\b{kind}\b", upper):
            return kind
    return "UNKNOWN"


def _db2_statement_tables(body: str, kind: str) -> list[str]:
    if kind in {"SELECT", "DECLARE_CURSOR"}:
        return _db2_select_tables(body)
    patterns = {
        "INSERT": r"\bINSERT\s+INTO\s+([A-Z0-9_.$#@]+)",
        "UPDATE": r"\bUPDATE\s+([A-Z0-9_.$#@]+)",
        "DELETE": r"\bDELETE\s+FROM\s+([A-Z0-9_.$#@]+)",
        "MERGE": r"\bMERGE\s+INTO\s+([A-Z0-9_.$#@]+)",
    }
    pattern = patterns.get(kind)
    if not pattern:
        return []
    tables: list[str] = []
    for match in re.finditer(pattern, body, re.I):
        table = _clean_name(match.group(1))
        if table and table not in tables:
            tables.append(table)
    return tables


def _db2_write_columns(body: str, kind: str, tables: list[str], aliases: dict[str, str] | None = None) -> list[str]:
    default_table = tables[0] if len(tables) == 1 else ""
    columns: list[str] = []
    if kind == "INSERT":
        match = re.search(r"\bINSERT\s+INTO\s+[A-Z0-9_.$#@]+\s*\((.*?)\)", body, re.I | re.S)
        if match:
            columns.extend(_clean_column_list(match.group(1), default_table, aliases))
    elif kind == "UPDATE":
        match = re.search(r"\bSET\b(.*?)(?:\bWHERE\b|$)", body, re.I | re.S)
        if match:
            for raw in re.findall(r"([A-Z0-9_.$#@]+)\s*=", match.group(1), re.I):
                column = _qualify_column(raw, default_table, aliases)
                if column and column not in columns:
                    columns.append(column)
    elif kind == "MERGE":
        for raw in re.findall(r"\bSET\s+([A-Z0-9_.$#@]+)\s*=", body, re.I):
            column = _qualify_column(raw, default_table, aliases)
            if column and column not in columns:
                columns.append(column)
    return columns


def _db2_output_host_vars(body: str, kind: str) -> list[str]:
    if kind == "FETCH":
        match = re.search(r"\bFETCH\s+[A-Z0-9_#$@-]+(?:\s+INTO\s+(.+))?", body, re.I | re.S)
        return _db2_host_vars(match.group(1) if match else "")
    match = re.search(r"\bINTO\s+(.+?)\bFROM\b", body, re.I | re.S)
    if kind in {"SELECT", "DECLARE_CURSOR"} and match:
        return _db2_host_vars(match.group(1))
    return []


def _db2_host_column_bindings(hosts: list[str], columns: list[str]) -> list[tuple[str, str]]:
    return list(zip(hosts, columns))


def _clean_column_list(text: str, default_table: str, aliases: dict[str, str] | None = None) -> list[str]:
    columns: list[str] = []
    for part in _split_top_level_csv(text):
        column = _qualify_column(part, default_table, aliases)
        if column and column not in columns:
            columns.append(column)
    return columns


def _qualify_column(raw: str, default_table: str, aliases: dict[str, str] | None = None) -> str:
    token = _clean_name(str(raw).strip().split()[-1] if str(raw).strip() else "")
    if not token or token.startswith(":") or token.isdigit():
        return ""
    aliases = aliases or {}
    if "." in token:
        prefix, column = token.split(".", 1)
        table = aliases.get(prefix, prefix)
        token = f"{table}.{column}"
    elif default_table:
        token = f"{default_table}.{token}"
    return token


def _db2_select_tables(query: str) -> list[str]:
    tables: list[str] = []
    for match in re.finditer(r"\b(?:FROM|JOIN)\s+([A-Z0-9_.$#@]+)", query, re.I):
        name = _clean_name(match.group(1))
        if name and name not in tables:
            tables.append(name)
    return tables


def _db2_table_aliases(query: str) -> dict[str, str]:
    aliases: dict[str, str] = {}
    for match in re.finditer(
        r"\b(?:FROM|JOIN)\s+([A-Z0-9_.$#@]+)(?:\s+(?:AS\s+)?([A-Z][A-Z0-9_#$@-]*))?",
        query,
        re.I,
    ):
        table = _clean_name(match.group(1))
        alias = _clean_name(match.group(2) or "")
        if alias and alias not in {"ON", "WHERE", "JOIN", "INNER", "LEFT", "RIGHT", "FULL", "CROSS", "GROUP", "ORDER"}:
            aliases[alias] = table
    return aliases


def _db2_select_columns(query: str, tables: list[str], aliases: dict[str, str] | None = None) -> list[str]:
    match = re.search(r"\bSELECT\b(.*?)\bFROM\b", query, re.I | re.S)
    if not match:
        return []
    columns: list[str] = []
    default_table = tables[0] if len(tables) == 1 else ""
    select_list = re.split(r"\bINTO\b", match.group(1), maxsplit=1, flags=re.I)[0]
    for part in _split_top_level_csv(select_list):
        token = re.sub(r"\bAS\s+[A-Z0-9_#$@-]+$", "", part.strip(), flags=re.I).strip()
        if not token or token == "*" or "(" in token:
            continue
        token = token.split()[-1]
        token = _clean_name(token)
        if not token:
            continue
        token = _qualify_column(token, default_table, aliases)
        if token not in columns:
            columns.append(token)
    return columns


def _db2_predicate_columns(query: str, tables: list[str], aliases: dict[str, str] | None = None) -> list[str]:
    match = re.search(r"\bWHERE\b(.*?)(?:\bGROUP\s+BY\b|\bORDER\s+BY\b|\bFETCH\b|\bWITH\b|$)", query, re.I | re.S)
    if not match:
        return []
    default_table = tables[0] if len(tables) == 1 else ""
    columns: list[str] = []
    for raw in re.findall(r"([A-Z0-9_.$#@]+)\s*(?:=|<>|<|>|<=|>=|LIKE|IN\b|BETWEEN\b)", match.group(1), re.I):
        name = _qualify_column(raw, default_table, aliases)
        if not name or name.startswith(":") or name.isdigit():
            continue
        if name not in columns:
            columns.append(name)
    return columns


def _db2_join_columns(query: str, tables: list[str], aliases: dict[str, str] | None = None) -> list[str]:
    default_table = tables[0] if len(tables) == 1 else ""
    columns: list[str] = []
    for on_body in re.findall(
        r"\bON\b(.*?)(?=\b(?:JOIN|WHERE|GROUP\s+BY|ORDER\s+BY|FETCH|WITH)\b|$)",
        query,
        re.I | re.S,
    ):
        for left, right in re.findall(r"([A-Z0-9_.$#@]+)\s*=\s*([A-Z0-9_.$#@]+)", on_body, re.I):
            for raw in (left, right):
                column = _qualify_column(raw, default_table, aliases)
                if column and not column.startswith(":") and column not in columns:
                    columns.append(column)
    return columns


def _db2_host_vars(text: str) -> list[str]:
    vars_seen: list[str] = []
    for match in re.finditer(r":([A-Z0-9_#$@-]+)", text, re.I):
        name = _clean_name(match.group(1))
        if name and name not in vars_seen:
            vars_seen.append(name)
    return vars_seen


def _db2_query_shape(query: str) -> dict[str, bool]:
    upper = query.upper()
    return {
        "has_join": " JOIN " in upper,
        "has_where": " WHERE " in upper,
        "has_group_by": " GROUP BY " in upper,
        "has_order_by": " ORDER BY " in upper,
        "has_fetch_limit": " FETCH " in upper,
    }


def _db2_option_value(text: str, option: str) -> str | None:
    match = re.search(rf"\b{re.escape(option)}\s*\(([^)]+)\)", text, re.I)
    return _clean_name(match.group(1)) if match else None


def _db2_option_list(text: str, option: str) -> list[str]:
    match = re.search(rf"\b{re.escape(option)}\s*\(([^)]+)\)", text, re.I | re.S)
    if not match:
        return []
    return [part.strip() for part in _split_top_level_csv(match.group(1)) if part.strip()]


def _pli_relationships(item: ClassifiedMember, source: Asset) -> list[FoundRelationship]:
    found: list[FoundRelationship] = []
    seen: set[tuple[str, str, str, str]] = set()
    for line_no, line in enumerate(item.lines, 1):
        if not line.strip():
            continue
        upper = line.upper()
        for match in re.finditer(r"\bCALL\s+([A-Z0-9#$@_-]+)\s*(?:\(|;)", upper):
            target = match.group(1)
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
                    confidence=0.88,
                    validation_status="inferred",
                    discovery_method="pli-static-parser",
                    attributes={"language": "PLI", "statement": "CALL"},
                ),
            )
        for match in re.finditer(r"%\s*INCLUDE\s+([A-Z0-9#$@_.-]+)", upper):
            _append_found(
                found,
                seen,
                _found(
                    item,
                    source,
                    "USES_COPYBOOK",
                    "COPYBOOK",
                    match.group(1),
                    line_no,
                    line,
                    confidence=0.82,
                    validation_status="inferred",
                    discovery_method="pli-static-parser",
                    attributes={"language": "PLI", "statement": "%INCLUDE"},
                ),
            )
        for match in re.finditer(r"\bREAD\s+FILE\s*\(\s*([A-Z0-9#$@_-]+)", upper):
            _append_found(found, seen, _found(item, source, "READS_FILE", "FILE", match.group(1), line_no, line, confidence=0.76, validation_status="inferred", discovery_method="pli-static-parser", attributes={"language": "PLI"}))
        for match in re.finditer(r"\b(?:WRITE|REWRITE)\s+FILE\s*\(\s*([A-Z0-9#$@_-]+)", upper):
            _append_found(found, seen, _found(item, source, "WRITES_FILE", "FILE", match.group(1), line_no, line, confidence=0.76, validation_status="inferred", discovery_method="pli-static-parser", attributes={"language": "PLI"}))
    for rel in _embedded_sql_relationships(item, source, confidence=0.84, discovery_method="pli-static-parser"):
        _append_found(found, seen, rel)
    return found


def _assembler_relationships(item: ClassifiedMember, source: Asset) -> list[FoundRelationship]:
    found: list[FoundRelationship] = []
    seen: set[tuple[str, str, str, str]] = set()
    for line_no, line in enumerate(item.lines, 1):
        stripped = line.strip()
        if not stripped or stripped.startswith(("*", ".*")):
            continue
        upper = stripped.upper()
        label = _assembler_label(line)
        if re.search(r"\bDSECT\b", upper) and label:
            _append_found(
                found,
                seen,
                _found(
                    item,
                    source,
                    "DEFINES_ASSEMBLER_DSECT",
                    "ASSEMBLER_DSECT",
                    label,
                    line_no,
                    line,
                    confidence=0.88,
                    validation_status="confirmed",
                    discovery_method="assembler-static-parser",
                    attributes={"language": "ASSEMBLER", "statement": "DSECT"},
                ),
            )
        for match in re.finditer(r"\b(?:COPY|INCLUDE)\s+([A-Z0-9#$@_.-]+)", upper):
            _append_found(
                found,
                seen,
                _found(
                    item,
                    source,
                    "USES_COPYBOOK",
                    "COPYBOOK",
                    match.group(1),
                    line_no,
                    line,
                    confidence=0.80,
                    validation_status="inferred",
                    discovery_method="assembler-static-parser",
                    attributes={"language": "ASSEMBLER", "statement": match.group(0).split()[0]},
                ),
            )
        for pattern, statement in (
            (r"\bCALL\s+([A-Z0-9#$@_-]+)", "CALL"),
            (r"\b(?:LINK|LOAD|XCTL|ATTACH)\s+(?:EP=|DE=)?([A-Z0-9#$@_-]+)", "LINKAGE_MACRO"),
        ):
            for match in re.finditer(pattern, upper):
                target = match.group(1)
                if target.startswith("("):
                    continue
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
                        confidence=0.78,
                        validation_status="inferred",
                        discovery_method="assembler-static-parser",
                        attributes={"language": "ASSEMBLER", "statement": statement},
                    ),
                )
        if re.search(r"\b(?:BALR|BASSM|BASR)\s+R?1?4?,\s*R?1?5\b|\bCALL\s+\(", upper):
            _append_found(
                found,
                seen,
                _found(
                    item,
                    source,
                    "DYNAMIC_CALL",
                    "UNRESOLVED",
                    f"DYNAMIC:{source.technical_name}:REGISTER",
                    line_no,
                    line,
                    confidence=0.30,
                    validation_status="needs_review",
                    discovery_method="assembler-static-parser",
                    attributes={"language": "ASSEMBLER", "unresolved_dynamic_target": True},
                ),
            )
    for rel in _embedded_sql_relationships(item, source, confidence=0.80, discovery_method="assembler-static-parser"):
        _append_found(found, seen, rel)
    return found


def _assembler_label(line: str) -> str:
    match = re.match(r"^\s*([A-Z0-9#$@_-]+)\s+", line.upper())
    return _clean_name(match.group(1)) if match else ""


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
    text = _strip_sql_comments(item.text)
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
    for match in re.finditer(r"\bDECLARE\s+(?:TABLE\s+([A-Z0-9_.$#@]+)|([A-Z0-9_.$#@]+)\s+TABLE)\b", text, re.I):
        line_no = _line_for_offset(text, match.start())
        table_name = match.group(1) or match.group(2)
        _append_found(
            found,
            seen,
            _found(
                item,
                source,
                "DECLARES_TABLE",
                "TABLE",
                table_name,
                line_no,
                _line_at(item.lines, line_no),
                confidence=0.92,
                validation_status="confirmed",
                discovery_method="observed",
                attributes={"dialect": "DB2", "statement": "DECLARE TABLE"},
            ),
        )
        if item.member.artifact_type == "DCLGEN":
            _append_found(
                found,
                seen,
                _found(
                    item,
                    source,
                    "DCLGEN_DECLARES_TABLE",
                    "TABLE",
                    table_name,
                    line_no,
                    _line_at(item.lines, line_no),
                    confidence=0.92,
                    validation_status="confirmed",
                    discovery_method="observed",
                    attributes={"dialect": "DB2", "statement": "DECLARE TABLE", "dclgen": source.technical_name},
                ),
            )
    for rel in _db2_infrastructure_relationships(item, source, text):
        _append_found(found, seen, rel)
    for rel in _db2_cursor_relationships(item, source, text, embedded=False, confidence=0.90):
        _append_found(found, seen, rel)
    for rel in _db2_package_relationships(item, source, text, confidence=0.88):
        _append_found(found, seen, rel)
    for rel in _db2_include_relationships(item, source, text, embedded=False, confidence=0.84):
        _append_found(found, seen, rel)
    for rel in _db2_statement_relationships(item, source, text, embedded=False, confidence=0.88):
        _append_found(found, seen, rel)
    return found


def _strip_sql_comments(text: str) -> str:
    def block_repl(match: re.Match[str]) -> str:
        return "\n" * match.group(0).count("\n")

    without_blocks = re.sub(r"/\*.*?\*/", block_repl, text, flags=re.S)
    return re.sub(r"--[^\n\r]*", "", without_blocks)


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


def _with_dataset_identity_relationships(
    item: ClassifiedMember,
    relationships: list[FoundRelationship],
) -> list[FoundRelationship]:
    found = list(relationships)
    seen: set[tuple[str, str, str, str]] = set()
    for rel in relationships:
        _append_found([], seen, rel)
    for rel in relationships:
        if rel.target.asset_type != "DATASET":
            continue
        attrs = _dataset_identity_attrs(rel.target.technical_name, rel.attributes or {})
        identity = _dataset_identity_asset(
            item.member.run_id,
            attrs["canonical_dataset"],
            confidence=min(rel.confidence, attrs["identity_confidence"]),
            validation_status=attrs["identity_status"],
            attributes=attrs,
        )
        line_no = rel.evidence.line_start or 1
        line = _line_at(item.lines, line_no)
        _append_found(
            found,
            seen,
            FoundRelationship(
                relationship_type="NORMALIZES_TO_DATASET_IDENTITY",
                source_asset_id=rel.target.asset_id,
                source_asset=rel.target,
                target=identity,
                evidence=Evidence(
                    source_path=item.member.relative_path,
                    line_start=line_no,
                    line_end=rel.evidence.line_end,
                    evidence_text=(rel.evidence.evidence_text or line.strip())[:500],
                    extractor=EXTRACTOR,
                    discovery_method="dataset-identity-normalizer",
                    confidence=min(rel.confidence, attrs["identity_confidence"]),
                    validation_status=attrs["identity_status"],
                ),
                confidence=min(rel.confidence, attrs["identity_confidence"]),
                validation_status=attrs["identity_status"],
                discovery_method="dataset-identity-normalizer",
                attributes=attrs,
            ),
        )
        mapped_rel = _dataset_identity_relationship_type(rel.relationship_type)
        if mapped_rel:
            _append_found(
                found,
                seen,
                FoundRelationship(
                    relationship_type=mapped_rel,
                    source_asset_id=rel.source_asset_id,
                    source_asset=rel.source_asset,
                    target=identity,
                    evidence=Evidence(
                        source_path=item.member.relative_path,
                        line_start=line_no,
                        line_end=rel.evidence.line_end,
                        evidence_text=(rel.evidence.evidence_text or line.strip())[:500],
                        extractor=EXTRACTOR,
                        discovery_method="dataset-identity-normalizer",
                        confidence=min(rel.confidence, attrs["identity_confidence"]),
                        validation_status=attrs["identity_status"],
                    ),
                    confidence=min(rel.confidence, attrs["identity_confidence"]),
                    validation_status=attrs["identity_status"],
                    discovery_method="dataset-identity-normalizer",
                    attributes={**attrs, "source_relationship_type": rel.relationship_type},
                ),
            )
    return found


def _dataset_identity_relationship_type(relationship_type: str) -> str | None:
    return {
        "READS_DATASET": "READS_DATASET_IDENTITY",
        "WRITES_DATASET": "WRITES_DATASET_IDENTITY",
        "USES_DATASET": "USES_DATASET_IDENTITY",
        "BINDS_DATASET": "BINDS_DATASET_IDENTITY",
    }.get(relationship_type.upper())


def _dataset_identity_asset(
    run_id: str,
    canonical_dataset: str,
    *,
    confidence: float,
    validation_status: str,
    attributes: dict[str, Any],
) -> Asset:
    canonical = _clean_dataset_name(canonical_dataset)
    return Asset(
        run_id=run_id,
        asset_type="DATASET_IDENTITY",
        technical_name=canonical,
        display_name=canonical,
        confidence=confidence,
        validation_status=validation_status,
        discovery_method="dataset-identity-normalizer",
        attributes=attributes,
    )


def _dataset_identity_attrs(dataset_name: str, rel_attrs: dict[str, Any]) -> dict[str, Any]:
    raw = _clean_dataset_name(dataset_name)
    gdg = _jcl_gdg(raw)
    canonical = gdg["base"] if gdg.get("is_gdg") else raw
    unresolved_symbolics = sorted(set(_unresolved_symbolics(raw) + list(rel_attrs.get("unresolved_symbolics") or [])))
    has_symbolics = bool(unresolved_symbolics)
    status = "needs_review" if has_symbolics else "inferred"
    confidence = 0.45 if has_symbolics else 0.86
    return {
        "raw_dataset": raw,
        "canonical_dataset": canonical,
        "normalized_base": canonical,
        "gdg": gdg,
        "is_gdg": bool(gdg.get("is_gdg")),
        "generation": gdg.get("generation"),
        "unresolved_symbolics": unresolved_symbolics,
        "has_symbolics": has_symbolics,
        "dd_name": rel_attrs.get("dd_name"),
        "disp": rel_attrs.get("disp"),
        "identity_status": status,
        "identity_confidence": confidence,
        "dataset_identity_normalized": not has_symbolics,
    }


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
    current_step: Asset | None = None
    previous_step: Asset | None = None
    active_conditions: list[Asset] = []
    for statement in _jcl_logical_statements(item.lines):
        line_no = statement["line"]
        line = statement["text"]
        upper = line.upper()
        if_match = re.match(r"^\s*//\s*IF\s+\((.*?)\)\s+THEN\b", upper)
        if if_match:
            condition = _jcl_condition_asset(item.member.run_id, source.technical_name, line_no, if_match.group(1))
            active_conditions.append(condition)
            found.append(
                _found_existing(
                    item,
                    source,
                    "DEFINES_CONDITION",
                    condition,
                    line_no,
                    line,
                    confidence=0.88,
                    validation_status="inferred",
                    discovery_method="observed",
                    attributes={"condition": if_match.group(1).strip(), "condition_kind": "IF_THEN"},
                )
            )
            found.extend(_jcl_condition_reference_relationships(item, source, condition, if_match.group(1), line_no, line))
            continue
        if re.match(r"^\s*//\s*ELSE\b", upper):
            if active_conditions:
                prior = active_conditions.pop()
                condition = _jcl_condition_asset(item.member.run_id, source.technical_name, line_no, f"NOT {prior.display_name}")
                active_conditions.append(condition)
                found.append(
                    _found_existing(
                        item,
                        source,
                        "DEFINES_CONDITION",
                        condition,
                        line_no,
                        line,
                        confidence=0.78,
                        validation_status="inferred",
                        discovery_method="observed",
                        attributes={"condition": condition.display_name, "condition_kind": "ELSE"},
                    )
                )
            continue
        if re.match(r"^\s*//\s*ENDIF\b", upper):
            if active_conditions:
                active_conditions.pop()
            continue
        step_match = re.match(r"^\s*//([A-Z0-9#$@_-]+)\s+EXEC\b", upper)
        if step_match:
            step_name = _clean_name(step_match.group(1))
            current_step = _jcl_step_asset(item.member.run_id, source, step_name)
            found.append(
                _found_existing(
                    item,
                    source,
                    "CONTAINS_STEP",
                    current_step,
                    line_no,
                    line,
                    confidence=0.95,
                    validation_status="confirmed",
                    discovery_method="observed",
                    attributes={"step_name": step_name},
                )
            )
            if previous_step is not None:
                found.append(
                    _found_existing(
                        item,
                        previous_step,
                        "EXECUTES_BEFORE",
                        current_step,
                        line_no,
                        line,
                        confidence=0.76,
                        validation_status="inferred",
                        discovery_method="observed",
                        attributes={"execution_order": "source_order"},
                    )
                )
            previous_step = current_step
            cond_text = _jcl_cond_clause(upper)
            if cond_text:
                condition = _jcl_condition_asset(item.member.run_id, source.technical_name, line_no, cond_text)
                found.append(
                    _found_existing(
                        item,
                        source,
                        "DEFINES_CONDITION",
                        condition,
                        line_no,
                        line,
                        confidence=0.78,
                        validation_status="inferred",
                        discovery_method="observed",
                        attributes={"condition": cond_text, "condition_kind": "COND"},
                    )
                )
                found.extend(_jcl_condition_reference_relationships(item, source, condition, cond_text, line_no, line))
                found.append(
                    _found_existing(
                        item,
                        condition,
                        "CONTROLS_STEP",
                        current_step,
                        line_no,
                        line,
                        confidence=0.78,
                        validation_status="inferred",
                        discovery_method="observed",
                        attributes={"condition": cond_text},
                    )
                )
            for condition in active_conditions:
                found.append(
                    _found_existing(
                        item,
                        condition,
                        "CONTROLS_STEP",
                        current_step,
                        line_no,
                        line,
                        confidence=0.78,
                        validation_status="inferred",
                        discovery_method="observed",
                        attributes={"condition": condition.display_name, "condition_kind": "IF_BLOCK"},
                    )
                )
        for match in re.finditer(r"\bEXEC\s+(?:(PGM|PROC)=)?([A-Z0-9#$@_-]+)", upper):
            kind = match.group(1)
            target = match.group(2)
            if target in {"PGM", "PROC"}:
                continue
            target_type = "PROGRAM" if kind == "PGM" else "PROC"
            rel_type = "EXECUTES"
            found.append(_found(item, source, rel_type, target_type, target, line_no, line, confidence=0.95))
            if target_type == "PROC":
                found.append(
                    _found(
                        item,
                        source,
                        "INVOKES_PROC",
                        "PROC",
                        target,
                        line_no,
                        line,
                        confidence=0.88,
                        validation_status="inferred",
                        discovery_method="observed",
                        attributes={"symbolic_parameters": _jcl_exec_parameters(line)},
                    )
                )
            if current_step is not None:
                found.append(
                    _found_existing(
                        item,
                        current_step,
                        rel_type,
                        _asset(item.member.run_id, target_type, target, confidence=0.95, validation_status="confirmed"),
                        line_no,
                        line,
                        confidence=0.95,
                        validation_status="confirmed",
                        discovery_method="observed",
                        attributes={"step_name": current_step.display_name, "target_kind": target_type, "symbolic_parameters": _jcl_exec_parameters(line)},
                    )
                )
                if target_type == "PROC":
                    found.append(
                        _found_existing(
                            item,
                            current_step,
                            "INVOKES_PROC",
                            _asset(item.member.run_id, "PROC", target, confidence=0.88, validation_status="inferred"),
                            line_no,
                            line,
                            confidence=0.88,
                            validation_status="inferred",
                            discovery_method="observed",
                            attributes={"step_name": current_step.display_name, "symbolic_parameters": _jcl_exec_parameters(line)},
                        )
                    )
        for match in re.finditer(r"\bDSN=([A-Z0-9.$#@_-]+(?:\([+-]?\d+\))?)", upper):
            rel_type = "WRITES_DATASET" if any(token in upper for token in ("DISP=(NEW", "DISP=NEW", "DISP=MOD")) else "READS_DATASET"
            dataset_name = _clean_dataset_name(match.group(1))
            attrs = {
                "step_name": current_step.display_name if current_step else None,
                "dd_name": _jcl_dd_name(upper),
                "disp": _jcl_disp(upper),
                "gdg": _jcl_gdg(match.group(1)),
            }
            if current_step is not None:
                dd_name = attrs["dd_name"]
                if dd_name:
                    dd_asset = _jcl_dd_asset(item.member.run_id, current_step, dd_name, attrs)
                    dataset_asset = _asset(item.member.run_id, "DATASET", dataset_name, confidence=0.75, validation_status="inferred")
                    found.append(
                        _found_existing(
                            item,
                            current_step,
                            "DECLARES_DD",
                            dd_asset,
                            line_no,
                            line,
                            confidence=0.78,
                            validation_status="inferred",
                            discovery_method="observed",
                            attributes=attrs,
                        )
                    )
                    found.append(
                        _found_existing(
                            item,
                            dd_asset,
                            "BINDS_DATASET",
                            dataset_asset,
                            line_no,
                            line,
                            confidence=0.78,
                            validation_status="inferred",
                            discovery_method="observed",
                            attributes=attrs,
                        )
                    )
                    found.append(
                        _found_existing(
                            item,
                            dd_asset,
                            rel_type,
                            dataset_asset,
                            line_no,
                            line,
                            confidence=0.75,
                            validation_status="inferred",
                            discovery_method="observed",
                            attributes=attrs,
                        )
                    )
                found.append(
                    _found_existing(
                        item,
                        current_step,
                        rel_type,
                        _asset(item.member.run_id, "DATASET", dataset_name, confidence=0.75, validation_status="inferred"),
                        line_no,
                        line,
                        confidence=0.75,
                        validation_status="inferred",
                        discovery_method="observed",
                        attributes=attrs,
                    )
                )
            found.append(
                _found(
                    item,
                    source,
                    rel_type,
                    "DATASET",
                    dataset_name,
                    line_no,
                    line,
                    confidence=0.75,
                    validation_status="inferred",
                    attributes=attrs,
                )
            )
    seen: set[tuple[str, str, str, str]] = set()
    for rel in list(found):
        _append_found([], seen, rel)
    for rel in _db2_package_relationships(item, source, item.text, confidence=0.78):
        _append_found(found, seen, rel)
    return found


def _jcl_logical_statements(lines: tuple[str, ...]) -> list[dict[str, Any]]:
    statements: list[dict[str, Any]] = []
    current: dict[str, Any] | None = None

    def flush() -> None:
        nonlocal current
        if current is not None:
            current["text"] = " ".join(str(current["text"]).split())
            statements.append(current)
            current = None

    for line_no, line in enumerate(lines, 1):
        if not line.strip() or not re.match(r"^\s*//", line):
            flush()
            continue
        if re.match(r"^\s*//\*", line):
            continue

        upper = line.upper()
        starts_control = bool(re.match(r"^\s*//\s*(IF|ELSE|ENDIF)\b", upper))
        starts_named = bool(re.match(r"^\s*//[A-Z0-9#$@_-]+\s+(JOB|EXEC|DD|PROC)\b", upper))
        if current is not None and not starts_control and not starts_named:
            continuation = re.sub(r"^\s*//\s*", "", line).strip()
            current["text"] = f"{current['text'].rstrip()} {continuation}"
            current["end_line"] = line_no
            current["raw_lines"].append(line)
            continue

        flush()
        current = {"line": line_no, "end_line": line_no, "text": line.rstrip(), "raw_lines": [line]}

    flush()
    return statements


def _jcl_step_asset(run_id: str, source: Asset, step_name: str) -> Asset:
    step = _clean_name(step_name)
    asset_type = "PROC_STEP" if source.asset_type == "PROC" else "JOB_STEP"
    return Asset(
        run_id=run_id,
        asset_type=asset_type,
        technical_name=f"{source.technical_name}::{step}",
        display_name=step,
        confidence=0.95,
        validation_status="confirmed",
        discovery_method="observed",
        attributes={
            "owner": source.technical_name,
            "owner_type": source.asset_type,
            "step_name": step,
        },
    )


def _jcl_condition_asset(run_id: str, owner_name: str, line_no: int, condition: str) -> Asset:
    text = " ".join(str(condition).strip().split())
    display = text[:120] or f"LINE-{line_no}"
    return Asset(
        run_id=run_id,
        asset_type="JCL_CONDITION",
        technical_name=f"{_clean_name(owner_name)}::COND::{line_no}",
        display_name=display,
        confidence=0.78,
        validation_status="inferred",
        discovery_method="observed",
        attributes={"owner": _clean_name(owner_name), "condition": text, "line": line_no},
    )


def _jcl_condition_reference_relationships(
    item: ClassifiedMember,
    source: Asset,
    condition: Asset,
    condition_text: str,
    line_no: int,
    line: str,
) -> list[FoundRelationship]:
    found: list[FoundRelationship] = []
    refs: list[str] = []
    for match in re.finditer(r"\b([A-Z0-9#$@_-]+)\.RC\b", condition_text, re.I):
        refs.append(_clean_name(match.group(1)))
    cond_tuple = re.match(r"\s*\d+\s*,\s*[A-Z]+\s*,\s*([A-Z0-9#$@_-]+)", condition_text, re.I)
    if cond_tuple:
        refs.append(_clean_name(cond_tuple.group(1)))
    for step_name in sorted({ref for ref in refs if ref}):
        step = _jcl_step_asset(item.member.run_id, source, step_name)
        rc = _return_code_asset(item.member.run_id, source.technical_name, step_name)
        found.append(
            _found_existing(
                item,
                condition,
                "CONDITION_REFERENCES_STEP",
                step,
                line_no,
                line,
                confidence=0.76,
                validation_status="inferred",
                discovery_method="observed",
                attributes={"condition": condition_text, "referenced_step": step_name},
            )
        )
        found.append(
            _found_existing(
                item,
                condition,
                "CONDITION_CHECKS_RETURN_CODE",
                rc,
                line_no,
                line,
                confidence=0.74,
                validation_status="inferred",
                discovery_method="observed",
                attributes={"condition": condition_text, "referenced_step": step_name, "return_code": "RC"},
            )
        )
    return found


def _jcl_dd_asset(run_id: str, step: Asset, dd_name: str, attrs: dict[str, Any]) -> Asset:
    name = _clean_name(dd_name)
    return Asset(
        run_id=run_id,
        asset_type="JCL_DD",
        technical_name=f"{step.technical_name}::{name}",
        display_name=name,
        confidence=0.78,
        validation_status="inferred",
        discovery_method="observed",
        attributes={
            "step": step.technical_name,
            "dd_name": name,
            "disp": attrs.get("disp"),
            "gdg": attrs.get("gdg"),
        },
    )


def _return_code_asset(run_id: str, job_name: str, step_name: str) -> Asset:
    job = _clean_name(job_name)
    step = _clean_name(step_name)
    return Asset(
        run_id=run_id,
        asset_type="RETURN_CODE",
        technical_name=f"{job}::{step}::RC",
        display_name=f"{step}.RC",
        confidence=0.74,
        validation_status="inferred",
        discovery_method="observed",
        attributes={"job": job, "step": step, "code": "RC"},
    )


def _jcl_dd_name(line: str) -> str | None:
    match = re.match(r"^\s*//([A-Z0-9#$@_-]+)\s+DD\b", line)
    return _clean_name(match.group(1)) if match else None


def _jcl_disp(line: str) -> str | None:
    match = re.search(r"\bDISP=\(?([A-Z,]+)\)?", line)
    return match.group(1) if match else None


def _jcl_gdg(dsn: str) -> dict[str, Any]:
    match = re.search(r"\(([+-]?\d+)\)\s*$", dsn)
    return {
        "is_gdg": bool(match),
        "generation": int(match.group(1)) if match else None,
        "base": _clean_name(re.sub(r"\([+-]?\d+\)\s*$", "", dsn)),
    }


def _jcl_cond_clause(line: str) -> str | None:
    match = re.search(r"\bCOND=\(([^)]*)\)|\bCOND=([A-Z0-9,]+)", line)
    if not match:
        return None
    return (match.group(1) or match.group(2) or "").strip()


def _jcl_exec_parameters(line: str) -> dict[str, str]:
    params: dict[str, str] = {}
    if "," not in line:
        return params
    tail = line.split(",", 1)[1]
    for key, value in re.findall(r"\b([A-Z0-9#$@_-]+)=([^,\s]+)", tail, flags=re.I):
        if key.upper() in {"PGM", "PROC", "COND", "PARM"}:
            continue
        params[_clean_name(key)] = value.strip().strip("'\"")
    return params


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
    name = _clean_dataset_name(technical_name) if asset_type == "DATASET" else _clean_name(technical_name)
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


def _field_asset(
    run_id: str,
    program_name: str,
    field_name: str,
    *,
    confidence: float,
    validation_status: str,
    attributes: dict[str, Any] | None = None,
) -> Asset:
    field = _clean_name(field_name)
    if "." in field:
        asset_type = "DB2_COLUMN"
        technical_name = field
    else:
        asset_type = "FIELD"
        technical_name = f"{_clean_name(program_name)}::{field}"
    return Asset(
        run_id=run_id,
        asset_type=asset_type,
        technical_name=technical_name,
        display_name=technical_name,
        confidence=confidence,
        validation_status=validation_status,
        discovery_method="reference-parser",
        attributes={"reference_only": True, **(attributes or {})},
    )


def _paragraph_asset(
    run_id: str,
    program_name: str,
    paragraph_name: str,
    *,
    confidence: float,
) -> Asset:
    program = _clean_name(program_name)
    paragraph = _clean_name(paragraph_name)
    return Asset(
        run_id=run_id,
        asset_type="PARAGRAPH",
        technical_name=f"{program}::{paragraph}",
        display_name=paragraph,
        confidence=confidence,
        validation_status="confirmed" if confidence >= 0.7 else "inferred",
        discovery_method="reference-parser",
        attributes={"program": program, "paragraph": paragraph},
    )


def _section_asset(run_id: str, program_name: str, section_name: str, *, confidence: float) -> Asset:
    program = _clean_name(program_name)
    section = _clean_name(section_name)
    return Asset(
        run_id=run_id,
        asset_type="SECTION",
        technical_name=f"{program}::{section}",
        display_name=section,
        confidence=confidence,
        validation_status="inferred",
        discovery_method="reference-parser",
        attributes={"program": program, "section": section},
    )


def _statement_asset(
    run_id: str,
    program_name: str,
    paragraph_name: str,
    verb: str,
    line_no: int,
    sequence: int,
    text: str,
    *,
    confidence: float,
) -> Asset:
    program = _clean_name(program_name)
    paragraph = _clean_name(paragraph_name or "MAIN")
    statement_verb = _clean_name(verb or "STATEMENT")
    return Asset(
        run_id=run_id,
        asset_type="STATEMENT",
        technical_name=f"{program}::STMT::{sequence:05d}::{line_no}::{statement_verb}",
        display_name=f"{statement_verb} line {line_no}",
        confidence=confidence,
        validation_status="inferred",
        discovery_method="reference-parser",
        attributes={
            "program": program,
            "paragraph": paragraph,
            "verb": statement_verb,
            "line": line_no,
            "sequence": sequence,
            "statement_text": text[:500],
        },
    )


def _business_rule_asset(
    run_id: str,
    program_name: str,
    rule: dict[str, Any],
    index: int,
    *,
    confidence: float,
) -> Asset:
    program = _clean_name(program_name)
    rule_id = _clean_name(str(rule.get("id") or f"{program}-R{index:03d}"))
    return Asset(
        run_id=run_id,
        asset_type="BUSINESS_RULE",
        technical_name=f"{program}::RULE::{rule_id}",
        display_name=rule_id,
        confidence=confidence,
        validation_status=str(rule.get("validation_status") or "inferred"),
        discovery_method="business-rule-extractor",
        attributes={
            "program": program,
            "rule_id": rule_id,
            "kind": rule.get("kind"),
            "condition": rule.get("condition"),
            "action": rule.get("action"),
            "statement": rule.get("statement"),
            "fields": rule.get("fields", []),
            "source_evidence": rule.get("source_evidence"),
        },
    )


def _transformation_asset(
    run_id: str,
    program_name: str,
    rule: dict[str, Any],
    index: int,
    *,
    confidence: float,
) -> Asset:
    program = _clean_name(program_name)
    digest = hashlib.sha1(str(rule.get("condition") or index).encode("utf-8", errors="replace")).hexdigest()[:10]
    return Asset(
        run_id=run_id,
        asset_type="TRANSFORMATION",
        technical_name=f"{program}::XFORM::{index:03d}::{digest}",
        display_name=f"Transformation {index:03d}",
        confidence=confidence,
        validation_status="inferred",
        discovery_method="business-rule-extractor",
        attributes={
            "program": program,
            "rule_id": rule.get("id"),
            "expression": rule.get("condition"),
            "statement": rule.get("statement"),
        },
    )


def _calculation_fields(expression: str) -> tuple[list[str], list[str]]:
    if "=" not in expression:
        return [], []
    left, right = expression.split("=", 1)
    outputs = [_clean_name(name) for name in re.findall(r"\b[A-Z][A-Z0-9-]*\b", left, re.I)]
    inputs = [
        _clean_name(name)
        for name in re.findall(r"\b[A-Z][A-Z0-9-]*\b", right, re.I)
        if _clean_name(name) not in {"ROUNDED", "BY", "TO", "FROM"}
    ]
    return sorted({name for name in outputs if name}), sorted({name for name in inputs if name})


def _cics_contract_asset(
    run_id: str,
    program_name: str,
    verb: str,
    line_no: int,
    contract: dict[str, Any],
    *,
    confidence: float,
) -> Asset:
    program = _clean_name(program_name)
    cics_verb = _clean_name(verb)
    return Asset(
        run_id=run_id,
        asset_type="CICS_CONTRACT",
        technical_name=f"{program}::CICS::{line_no}::{cics_verb}",
        display_name=f"{cics_verb} line {line_no}",
        confidence=confidence,
        validation_status="inferred",
        discovery_method="cics-contract-extractor",
        attributes={"program": program, "verb": cics_verb, "line": line_no, "data_contract": contract},
    )


def _cics_condition_asset(
    run_id: str,
    program_name: str,
    condition_name: str,
    line_no: int,
    *,
    confidence: float,
) -> Asset:
    program = _clean_name(program_name)
    condition = _clean_name(condition_name)
    return Asset(
        run_id=run_id,
        asset_type="CICS_CONDITION",
        technical_name=f"{program}::CICSCOND::{condition}::{line_no}",
        display_name=condition,
        confidence=confidence,
        validation_status="inferred",
        discovery_method="cics-contract-extractor",
        attributes={"program": program, "condition": condition, "line": line_no},
    )


def _file_io_asset(run_id: str, program_name: str, operation: dict[str, Any]) -> Asset:
    program = _clean_name(program_name)
    verb = _clean_name(str(operation.get("verb") or "FILEIO"))
    file_name = _clean_name(str(operation.get("file") or "UNKNOWN"))
    line_no = int(operation.get("line") or 1)
    return Asset(
        run_id=run_id,
        asset_type="FILE_IO_OPERATION",
        technical_name=f"{program}::FILEIO::{verb}::{line_no}::{file_name}",
        display_name=f"{verb} {file_name}",
        confidence=0.78,
        validation_status="inferred",
        discovery_method="file-io-extractor",
        attributes={"program": program, **operation},
    )


def _file_record_asset(run_id: str, program_name: str, file_name: str, record_name: str) -> Asset:
    program = _clean_name(program_name)
    file_clean = _clean_name(file_name)
    record = _clean_name(record_name)
    return Asset(
        run_id=run_id,
        asset_type="FILE_RECORD",
        technical_name=f"{program}::{file_clean}::{record}",
        display_name=record,
        confidence=0.82,
        validation_status="inferred",
        discovery_method="file-io-extractor",
        attributes={"program": program, "file": file_clean, "record": record},
    )


def _sort_merge_asset(run_id: str, program_name: str, verb: str, line_no: int, work_file: str, tail: str) -> Asset:
    program = _clean_name(program_name)
    sort_verb = _clean_name(verb)
    work = _clean_name(work_file)
    return Asset(
        run_id=run_id,
        asset_type="SORT_MERGE_OPERATION",
        technical_name=f"{program}::SORTMERGE::{sort_verb}::{line_no}::{work}",
        display_name=f"{sort_verb} {work}",
        confidence=0.82,
        validation_status="inferred",
        discovery_method="sort-merge-extractor",
        attributes={"program": program, "verb": sort_verb, "work_file": work, "clause": tail.strip()[:500]},
    )


def _clean_name(value: str) -> str:
    return value.strip().strip("'\"()[],.").upper()


def _clean_dataset_name(value: str) -> str:
    return value.strip().strip("'\"[],.").upper()


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
