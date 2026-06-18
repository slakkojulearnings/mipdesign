from __future__ import annotations

import argparse
import hashlib
import json
import re
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


def scan_mainframe_tree(
    source_root: str | Path,
    db_path: str | Path,
    *,
    run_id: str | None = None,
) -> dict[str, Any]:
    """CLI-callable service function for deterministic source inventory and analysis."""
    repository = SQLiteGraphRepository(db_path)
    return scan_mainframe_estate(source_root, repository, run_id=run_id)


def scan_mainframe_estate(
    source_root: str | Path,
    repository: SQLiteGraphRepository,
    *,
    run_id: str | None = None,
) -> dict[str, Any]:
    root = Path(source_root)
    selected_run_id = repository.create_run(str(root), run_id=run_id)
    members = [_classify_path(path, root, selected_run_id) for path in _iter_files(root)]
    referenced_copies = _referenced_copy_names(members)
    members = _promote_referenced_copybooks(members, referenced_copies)
    copybooks, copybook_metadata = _copybook_index(members, referenced_copies)
    resolver_fingerprint = _copybook_fingerprint(copybooks, copybook_metadata)
    resolver = copybook_resolver(copybooks, copybook_metadata)
    cobol_analysis = {
        item.member.member_id: _parse_cobol_cached(
            repository, item, resolver=resolver, resolver_fingerprint=resolver_fingerprint
        )
        for item in members
        if item.member.artifact_type in {"COBOL", "ASSEMBLER"} and item.text
    }

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

    for item in members:
        source = member_assets[item.member.member_id]
        for rel in _relationships_for_member(item, source, cobol_analysis.get(item.member.member_id)):
            assets.setdefault(rel.target.asset_id, rel.target)
            relationships.append(rel)

    _persist_graph(repository, selected_run_id, members, assets, relationships)

    GraphService(repository).recompute_summaries(selected_run_id)
    insight_count = write_deterministic_insights(repository, selected_run_id, warnings)
    repository.complete_run(selected_run_id)
    stats = repository.stats(selected_run_id)
    return {
        "run_id": selected_run_id,
        "source_root": str(root),
        "database": str(repository.db_path),
        "file_count": stats["run"]["file_count"] if stats["run"] else len(members),
        "asset_count": stats["run"]["asset_count"] if stats["run"] else len(assets),
        "relationship_count": stats["run"]["relationship_count"] if stats["run"] else len(relationships),
        "insight_count": insight_count,
        "warnings": warnings,
    }


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
        ("DCLGEN", "content:DECLARE TABLE", 0.90, r"\bDECLARE\s+TABLE\b"),
        ("BMS_MAP", "content:BMS macros", 0.90, r"\bDFH(MSD|MDI|MDF)\b"),
        ("MQ", "content:MQ definitions", 0.80, r"\b(DEFINE\s+QLOCAL|MQPUT|MQGET|MQOPEN)\b"),
        ("IMS", "content:IMS definitions", 0.80, r"\b(PSBGEN|DBDGEN|PCB\s+TYPE=)\b"),
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
) -> dict[str, Any]:
    cache_key = stable_id("parse", item.member.sha256, resolver_fingerprint, PARSER_VERSION)
    cached = repository.get_cached_parse(cache_key)
    if cached:
        payload = json.loads(json.dumps(cached))
        parser = dict(payload.get("parser", {}))
        parser["cache_hit"] = True
        payload["parser"] = parser
        return payload
    payload = parse_cobol(item.text, resolver=resolver)
    parser = dict(payload.get("parser", {}))
    parser["cache_hit"] = False
    payload["parser"] = parser
    repository.put_cached_parse(
        cache_key=cache_key,
        source_sha256=item.member.sha256,
        resolver_fingerprint=resolver_fingerprint,
        parser_version=PARSER_VERSION,
        payload=payload,
    )
    return payload


def _asset_for_member(item: ClassifiedMember, analysis: dict[str, Any] | None = None) -> Asset:
    artifact_type = item.member.artifact_type
    asset_type = ASSET_BY_ARTIFACT.get(artifact_type, "UNKNOWN_ARTIFACT")
    technical_name = analysis.get("program_id") if analysis and analysis.get("program_id") else _primary_name(item, artifact_type)
    status = item.member.validation_status
    confidence = item.member.confidence
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
        "MQ": r"\bDEFINE\s+QLOCAL\(([^)]+)\)",
        "BMS_MAP": r"\b([A-Z0-9#$@]+)\s+DFHMSD\b",
        "IMS": r"\b(PSBGEN|DBDGEN)\s+.*?\bNAME=([A-Z0-9#$@]+)",
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
    return found


def _append_found(
    found: list[FoundRelationship], seen: set[tuple[str, str, str]], rel: FoundRelationship
) -> None:
    key = (rel.relationship_type, rel.source_asset_id, rel.target.asset_id)
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
    args = parser.parse_args(argv)
    print(json.dumps(scan_mainframe_tree(args.source_root, args.db, run_id=args.run_id), indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
