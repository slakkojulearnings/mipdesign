from __future__ import annotations

import json
import sqlite3
from abc import ABC, abstractmethod
from collections.abc import Iterable
from contextlib import contextmanager
from pathlib import Path
from typing import Any

from .models import Asset, Evidence, Relationship, SourceMember, now_iso, stable_id

SCHEMA_VERSION = 2


class AssetRepository(ABC):
    @abstractmethod
    def search_assets(
        self, run_id: str, query: str, *, limit: int = 50, offset: int = 0
    ) -> list[dict[str, Any]]:
        raise NotImplementedError

    @abstractmethod
    def get_asset(self, asset_id: str) -> dict[str, Any] | None:
        raise NotImplementedError


class RelationshipRepository(ABC):
    @abstractmethod
    def relationships_for_asset(
        self,
        run_id: str,
        asset_id: str,
        *,
        direction: str = "both",
        relationship_types: Iterable[str] = (),
        confidence_min: float = 0.0,
        limit: int = 1000,
    ) -> list[dict[str, Any]]:
        raise NotImplementedError

    @abstractmethod
    def get_relationship(self, relationship_id: str) -> dict[str, Any] | None:
        raise NotImplementedError


class GraphSliceRepository(ABC):
    @abstractmethod
    def get_cached_slice(self, cache_key: str) -> dict[str, Any] | None:
        raise NotImplementedError

    @abstractmethod
    def put_cached_slice(
        self,
        *,
        cache_key: str,
        run_id: str,
        root_asset_id: str,
        mode: str,
        depth: int,
        limit: int,
        relationship_types: Iterable[str],
        confidence_min: float,
        payload: dict[str, Any],
    ) -> None:
        raise NotImplementedError


class SQLiteGraphRepository(AssetRepository, RelationshipRepository, GraphSliceRepository):
    """SQLite implementation kept behind repository interfaces for PostgreSQL parity."""

    def __init__(self, db_path: str | Path) -> None:
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)

    @contextmanager
    def connect(self):
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys = ON")
        conn.execute("PRAGMA journal_mode = WAL")
        conn.execute("PRAGMA synchronous = NORMAL")
        conn.execute("PRAGMA busy_timeout = 10000")
        conn.execute("PRAGMA temp_store = MEMORY")
        try:
            yield conn
            conn.commit()
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()

    def initialize(self) -> None:
        schema = Path(__file__).with_name("schema.sql")
        with self.connect() as conn:
            conn.executescript(schema.read_text(encoding="utf-8"))
            self._migrate_schema(conn)
            conn.execute(
                """
                INSERT OR REPLACE INTO schema_version(version, backend, description, applied_at)
                VALUES (?, 'sqlite', ?, ?)
                """,
                (SCHEMA_VERSION, "baseline plus persistent enrichment schema", now_iso()),
            )

    def _migrate_schema(self, conn) -> None:
        self._add_column_if_missing(conn, "asset", "origin", "TEXT NOT NULL DEFAULT 'baseline'")
        self._add_column_if_missing(conn, "asset", "enriched_by_member", "TEXT")
        self._add_column_if_missing(conn, "relationship", "origin", "TEXT NOT NULL DEFAULT 'baseline'")
        self._add_column_if_missing(conn, "relationship", "enriched_by_member", "TEXT")

    @staticmethod
    def _add_column_if_missing(conn, table: str, column: str, ddl: str) -> None:
        columns = {row["name"] for row in conn.execute(f"PRAGMA table_info({table})")}
        if column not in columns:
            conn.execute(f"ALTER TABLE {table} ADD COLUMN {column} {ddl}")

    def create_run(
        self,
        source_root: str,
        *,
        run_id: str | None = None,
        config: dict[str, Any] | None = None,
        resume: bool = False,
    ) -> str:
        self.initialize()
        selected = run_id or stable_id("run", source_root, now_iso())
        with self.connect() as conn:
            if not resume:
                self._clear_run_children(conn, selected)
            conn.execute(
                """
                INSERT INTO run_manifest(run_id, source_root, started_at, status, config_json)
                VALUES (?, ?, ?, 'RUNNING', ?)
                ON CONFLICT(run_id) DO UPDATE SET
                    source_root = excluded.source_root,
                    status = 'RUNNING',
                    completed_at = NULL,
                    config_json = excluded.config_json
                """,
                (selected, source_root, now_iso(), json.dumps(config or {}, sort_keys=True)),
            )
        return selected

    def _clear_run_children(self, conn, run_id: str) -> None:
        for table in (
            "enrichment_fact_source",
            "enrichment_member_status",
            "enrichment_job",
            "source_member",
            "asset",
            "relationship",
            "evidence",
            "root_summary",
            "app_cluster",
            "node_degree",
            "graph_slice_cache",
            "insight",
            "validation_result",
            "scan_progress",
            "scan_issue",
            "scan_phase_telemetry",
            "scan_file_telemetry",
            "scorecard_result",
        ):
            conn.execute(f"DELETE FROM {table} WHERE run_id = ?", (run_id,))

    def complete_run(self, run_id: str, status: str = "COMPLETED") -> None:
        with self.connect() as conn:
            counts = conn.execute(
                """
                SELECT
                    (SELECT COUNT(*) FROM source_member WHERE run_id = ?) AS file_count,
                    (SELECT COUNT(*) FROM asset WHERE run_id = ?) AS asset_count,
                    (SELECT COUNT(*) FROM relationship WHERE run_id = ?) AS relationship_count,
                    (SELECT COUNT(*) FROM source_member WHERE run_id = ? AND artifact_type LIKE 'UNKNOWN%') AS unknown_count,
                    (SELECT COUNT(*) FROM source_member WHERE run_id = ? AND is_binary = 1) AS binary_count,
                    (SELECT COUNT(*) FROM scan_issue WHERE run_id = ?) AS warning_count
                """,
                (run_id, run_id, run_id, run_id, run_id, run_id),
            ).fetchone()
            conn.execute(
                """
                UPDATE run_manifest
                SET completed_at = ?, status = ?, file_count = ?, asset_count = ?,
                    relationship_count = ?, unknown_count = ?, binary_count = ?,
                    warning_count = ?
                WHERE run_id = ?
                """,
                (
                    now_iso(),
                    status,
                    counts["file_count"],
                    counts["asset_count"],
                    counts["relationship_count"],
                    counts["unknown_count"],
                    counts["binary_count"],
                    counts["warning_count"],
                    run_id,
                ),
            )

    def latest_run_id(self) -> str | None:
        self.initialize()
        with self.connect() as conn:
            row = conn.execute(
                "SELECT run_id FROM run_manifest ORDER BY started_at DESC LIMIT 1"
            ).fetchone()
            return str(row["run_id"]) if row else None

    def upsert_member(self, member: SourceMember) -> str:
        with self.connect() as conn:
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
        return member.member_id

    def upsert_asset(self, asset: Asset, evidence: Iterable[Evidence] = ()) -> str:
        with self.connect() as conn:
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
                self._insert_evidence(conn, asset.run_id, "ASSET", asset.asset_id, item)
        return asset.asset_id

    def insert_relationship(
        self, relationship: Relationship, evidence: Iterable[Evidence] = ()
    ) -> str:
        with self.connect() as conn:
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
                self._insert_evidence(
                    conn, relationship.run_id, "RELATIONSHIP", relationship.relationship_id, item
                )
        return relationship.relationship_id

    def _insert_evidence(
        self, conn, run_id: str, entity_kind: str, entity_id: str, evidence: Evidence
    ) -> None:
        evidence_id = stable_id(
            run_id,
            "evidence",
            entity_kind,
            entity_id,
            evidence.source_path,
            evidence.line_start,
            evidence.evidence_text,
        )
        conn.execute(
            """
            INSERT OR REPLACE INTO evidence(
                evidence_id, run_id, entity_kind, entity_id, source_path, line_start,
                line_end, evidence_text, extractor, discovery_method, confidence,
                validation_status, created_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                evidence_id,
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
                now_iso(),
            ),
        )

    def search_assets(
        self, run_id: str, query: str, *, limit: int = 50, offset: int = 0
    ) -> list[dict[str, Any]]:
        needle = f"%{query.upper()}%"
        with self.connect() as conn:
            rows = conn.execute(
                """
                SELECT a.*, sm.relative_path
                FROM asset a LEFT JOIN source_member sm ON sm.member_id = a.member_id
                WHERE a.run_id = ? AND (
                    UPPER(a.technical_name) LIKE ? OR UPPER(a.display_name) LIKE ?
                    OR UPPER(COALESCE(sm.relative_path, '')) LIKE ?
                )
                ORDER BY
                    CASE WHEN UPPER(a.technical_name) = UPPER(?) THEN 0 ELSE 1 END,
                    a.asset_type, a.technical_name
                LIMIT ? OFFSET ?
                """,
                (run_id, needle, needle, needle, query, min(limit, 200), max(offset, 0)),
            ).fetchall()
            return [self._asset_row(row) for row in rows]

    def get_asset(self, asset_id: str) -> dict[str, Any] | None:
        with self.connect() as conn:
            row = conn.execute(
                """
                SELECT a.*, sm.relative_path, sm.text_status, sm.classification_basis
                FROM asset a LEFT JOIN source_member sm ON sm.member_id = a.member_id
                WHERE a.asset_id = ?
                """,
                (asset_id,),
            ).fetchone()
            return self._asset_row(row) if row else None

    def relationships_for_asset(
        self,
        run_id: str,
        asset_id: str,
        *,
        direction: str = "both",
        relationship_types: Iterable[str] = (),
        confidence_min: float = 0.0,
        limit: int = 1000,
    ) -> list[dict[str, Any]]:
        rels = [item.upper() for item in relationship_types]
        conditions = ["r.run_id = ?", "r.confidence >= ?"]
        params: list[Any] = [run_id, confidence_min]
        if direction == "out":
            conditions.append("r.source_asset_id = ?")
            params.append(asset_id)
        elif direction == "in":
            conditions.append("r.target_asset_id = ?")
            params.append(asset_id)
        else:
            conditions.append("(r.source_asset_id = ? OR r.target_asset_id = ?)")
            params.extend([asset_id, asset_id])
        if rels:
            placeholders = ",".join("?" for _ in rels)
            conditions.append(f"r.relationship_type IN ({placeholders})")
            params.extend(rels)
        params.append(min(limit, 5000))
        sql = f"""
            SELECT r.*, s.technical_name AS source_name, s.asset_type AS source_type,
                   t.technical_name AS target_name, t.asset_type AS target_type
            FROM relationship r
            JOIN asset s ON s.asset_id = r.source_asset_id
            JOIN asset t ON t.asset_id = r.target_asset_id
            WHERE {" AND ".join(conditions)}
            ORDER BY r.relationship_type, s.technical_name, t.technical_name
            LIMIT ?
        """
        with self.connect() as conn:
            return [self._relationship_row(row) for row in conn.execute(sql, params)]

    def get_relationship(self, relationship_id: str) -> dict[str, Any] | None:
        with self.connect() as conn:
            row = conn.execute(
                """
                SELECT r.*, s.technical_name AS source_name, s.asset_type AS source_type,
                       t.technical_name AS target_name, t.asset_type AS target_type
                FROM relationship r
                JOIN asset s ON s.asset_id = r.source_asset_id
                JOIN asset t ON t.asset_id = r.target_asset_id
                WHERE r.relationship_id = ?
                """,
                (relationship_id,),
            ).fetchone()
            return self._relationship_row(row) if row else None

    def evidence_for(self, run_id: str, entity_kind: str, entity_id: str) -> list[dict[str, Any]]:
        with self.connect() as conn:
            rows = conn.execute(
                """
                SELECT * FROM evidence
                WHERE run_id = ? AND entity_kind = ? AND entity_id = ?
                ORDER BY source_path, line_start
                """,
                (run_id, entity_kind.upper(), entity_id),
            ).fetchall()
            return [dict(row) for row in rows]

    def list_roots(self, run_id: str, *, limit: int = 200) -> list[dict[str, Any]]:
        with self.connect() as conn:
            rows = conn.execute(
                """
                SELECT a.*, rs.reachable_assets, rs.reachable_programs, rs.data_touchpoints,
                       rs.unresolved_count, rs.risk_score, rs.capability_label
                FROM root_summary rs JOIN asset a ON a.asset_id = rs.root_asset_id
                WHERE rs.run_id = ?
                ORDER BY rs.risk_score DESC, a.technical_name
                LIMIT ?
                """,
                (run_id, min(limit, 1000)),
            ).fetchall()
            return [self._asset_row(row) for row in rows]

    def list_clusters(self, run_id: str, *, limit: int = 200) -> list[dict[str, Any]]:
        with self.connect() as conn:
            rows = conn.execute(
                """
                SELECT * FROM app_cluster
                WHERE run_id = ?
                ORDER BY risk_score DESC, name
                LIMIT ?
                """,
                (run_id, min(limit, 500)),
            ).fetchall()
            return [self._json_row(row, "attributes_json") for row in rows]

    def stats(self, run_id: str) -> dict[str, Any]:
        with self.connect() as conn:
            run = conn.execute("SELECT * FROM run_manifest WHERE run_id = ?", (run_id,)).fetchone()
            by_asset = conn.execute(
                "SELECT asset_type, COUNT(*) c FROM asset WHERE run_id = ? GROUP BY asset_type",
                (run_id,),
            ).fetchall()
            by_rel = conn.execute(
                """
                SELECT relationship_type, COUNT(*) c
                FROM relationship WHERE run_id = ? GROUP BY relationship_type
                """,
                (run_id,),
            ).fetchall()
            return {
                "run": dict(run) if run else None,
                "assets": {row["asset_type"]: row["c"] for row in by_asset},
                "relationships": {row["relationship_type"]: row["c"] for row in by_rel},
                "progress": self._progress_rows(conn, run_id),
                "issues": self._issue_summary(conn, run_id),
                "telemetry": self._telemetry_summary(conn, run_id),
            }

    def _progress_rows(self, conn, run_id: str) -> list[dict[str, Any]]:
        rows = conn.execute(
            """
            SELECT *
            FROM scan_progress
            WHERE run_id = ?
            ORDER BY started_at, phase
            """,
            (run_id,),
        ).fetchall()
        return [self._scan_progress_row(row) for row in rows]

    def _issue_summary(self, conn, run_id: str) -> dict[str, int]:
        rows = conn.execute(
            """
            SELECT stage || ':' || severity AS bucket, COUNT(*) c
            FROM scan_issue
            WHERE run_id = ?
            GROUP BY stage, severity
            """,
            (run_id,),
        ).fetchall()
        return {row["bucket"]: row["c"] for row in rows}

    def _telemetry_summary(self, conn, run_id: str) -> dict[str, Any]:
        phase_rows = conn.execute(
            """
            SELECT phase, ROUND(SUM(elapsed_ms), 3) AS elapsed_ms,
                   MAX(memory_peak_bytes) AS memory_peak_bytes
            FROM scan_phase_telemetry
            WHERE run_id = ?
            GROUP BY phase
            ORDER BY MIN(created_at)
            """,
            (run_id,),
        ).fetchall()
        file_row = conn.execute(
            """
            SELECT COUNT(*) AS file_count,
                   COALESCE(SUM(reused_classification), 0) AS reused_classifications,
                   COALESCE(SUM(parse_cache_hit), 0) AS parse_cache_hits,
                   COALESCE(SUM(skipped), 0) AS skipped_files,
                   ROUND(COALESCE(SUM(total_ms), 0), 3) AS file_total_ms
            FROM scan_file_telemetry
            WHERE run_id = ?
            """,
            (run_id,),
        ).fetchone()
        return {
            "phases": [dict(row) for row in phase_rows],
            "files": dict(file_row) if file_row else {},
        }

    def upsert_scan_progress(
        self,
        run_id: str,
        phase: str,
        *,
        total_files: int = 0,
        processed_files: int = 0,
        parsed_files: int = 0,
        cached_parse_hits: int = 0,
        failed_files: int = 0,
        details: dict[str, Any] | None = None,
    ) -> None:
        now = now_iso()
        with self.connect() as conn:
            conn.execute(
                """
                INSERT INTO scan_progress(
                    run_id, phase, total_files, processed_files, parsed_files,
                    cached_parse_hits, failed_files, started_at, updated_at, details_json
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(run_id, phase) DO UPDATE SET
                    total_files = excluded.total_files,
                    processed_files = excluded.processed_files,
                    parsed_files = excluded.parsed_files,
                    cached_parse_hits = excluded.cached_parse_hits,
                    failed_files = excluded.failed_files,
                    updated_at = excluded.updated_at,
                    details_json = excluded.details_json
                """,
                (
                    run_id,
                    phase.upper(),
                    total_files,
                    processed_files,
                    parsed_files,
                    cached_parse_hits,
                    failed_files,
                    now,
                    now,
                    json.dumps(details or {}, sort_keys=True),
                ),
            )

    def insert_scan_issue(
        self,
        run_id: str,
        relative_path: str,
        *,
        stage: str,
        severity: str,
        error_type: str,
        message: str,
        details: dict[str, Any] | None = None,
    ) -> str:
        issue_id = stable_id(
            run_id,
            "scan_issue",
            relative_path,
            stage,
            error_type,
            message,
        )
        with self.connect() as conn:
            conn.execute(
                """
                INSERT OR REPLACE INTO scan_issue(
                    issue_id, run_id, relative_path, stage, severity, error_type,
                    message, details_json, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    issue_id,
                    run_id,
                    relative_path,
                    stage.upper(),
                    severity.upper(),
                    error_type,
                    message[:1000],
                    json.dumps(details or {}, sort_keys=True),
                    now_iso(),
                ),
            )
        return issue_id

    def insert_phase_telemetry(
        self,
        run_id: str,
        phase: str,
        *,
        elapsed_ms: float,
        memory_peak_bytes: int = 0,
        details: dict[str, Any] | None = None,
    ) -> str:
        telemetry_id = stable_id(run_id, "phase_telemetry", phase.upper(), now_iso())
        with self.connect() as conn:
            conn.execute(
                """
                INSERT INTO scan_phase_telemetry(
                    telemetry_id, run_id, phase, elapsed_ms, memory_peak_bytes,
                    details_json, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    telemetry_id,
                    run_id,
                    phase.upper(),
                    float(elapsed_ms),
                    int(memory_peak_bytes or 0),
                    json.dumps(details or {}, sort_keys=True),
                    now_iso(),
                ),
            )
        return telemetry_id

    def upsert_file_telemetry(
        self,
        run_id: str,
        relative_path: str,
        *,
        sha256: str,
        size_bytes: int,
        artifact_type: str,
        classification_basis: str,
        validation_status: str,
        classify_ms: float = 0.0,
        parse_ms: float = 0.0,
        graph_ms: float = 0.0,
        total_ms: float = 0.0,
        reused_classification: bool = False,
        parse_cache_hit: bool = False,
        skipped: bool = False,
        details: dict[str, Any] | None = None,
    ) -> None:
        with self.connect() as conn:
            conn.execute(
                """
                INSERT INTO scan_file_telemetry(
                    run_id, relative_path, sha256, size_bytes, artifact_type,
                    classification_basis, validation_status, classify_ms, parse_ms,
                    graph_ms, total_ms, reused_classification, parse_cache_hit, skipped,
                    details_json, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(run_id, relative_path) DO UPDATE SET
                    sha256 = excluded.sha256,
                    size_bytes = excluded.size_bytes,
                    artifact_type = excluded.artifact_type,
                    classification_basis = excluded.classification_basis,
                    validation_status = excluded.validation_status,
                    classify_ms = CASE WHEN excluded.classify_ms > 0 THEN excluded.classify_ms ELSE scan_file_telemetry.classify_ms END,
                    parse_ms = CASE WHEN excluded.parse_ms > 0 THEN excluded.parse_ms ELSE scan_file_telemetry.parse_ms END,
                    graph_ms = CASE WHEN excluded.graph_ms > 0 THEN excluded.graph_ms ELSE scan_file_telemetry.graph_ms END,
                    total_ms = scan_file_telemetry.total_ms + excluded.total_ms,
                    reused_classification = MAX(scan_file_telemetry.reused_classification, excluded.reused_classification),
                    parse_cache_hit = MAX(scan_file_telemetry.parse_cache_hit, excluded.parse_cache_hit),
                    skipped = MAX(scan_file_telemetry.skipped, excluded.skipped),
                    details_json = CASE WHEN excluded.details_json <> '{}' THEN excluded.details_json ELSE scan_file_telemetry.details_json END,
                    created_at = excluded.created_at
                """,
                (
                    run_id,
                    relative_path,
                    sha256,
                    int(size_bytes),
                    artifact_type,
                    classification_basis,
                    validation_status,
                    float(classify_ms),
                    float(parse_ms),
                    float(graph_ms),
                    float(total_ms),
                    int(bool(reused_classification)),
                    int(bool(parse_cache_hit)),
                    int(bool(skipped)),
                    json.dumps(details or {}, sort_keys=True),
                    now_iso(),
                ),
            )

    def get_file_inventory_cache(
        self, source_root: str, relative_path: str, sha256: str
    ) -> dict[str, Any] | None:
        with self.connect() as conn:
            row = conn.execute(
                """
                SELECT *
                FROM file_inventory_cache
                WHERE source_root = ? AND relative_path = ? AND sha256 = ?
                """,
                (source_root, relative_path, sha256),
            ).fetchone()
            return dict(row) if row else None

    def put_file_inventory_cache(self, source_root: str, member: SourceMember) -> None:
        with self.connect() as conn:
            conn.execute(
                """
                INSERT INTO file_inventory_cache(
                    source_root, relative_path, sha256, size_bytes, encoding, is_binary,
                    text_status, artifact_type, classification_basis, confidence,
                    validation_status, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(source_root, relative_path) DO UPDATE SET
                    sha256 = excluded.sha256,
                    size_bytes = excluded.size_bytes,
                    encoding = excluded.encoding,
                    is_binary = excluded.is_binary,
                    text_status = excluded.text_status,
                    artifact_type = excluded.artifact_type,
                    classification_basis = excluded.classification_basis,
                    confidence = excluded.confidence,
                    validation_status = excluded.validation_status,
                    updated_at = excluded.updated_at
                """,
                (
                    source_root,
                    member.relative_path,
                    member.sha256,
                    member.size_bytes,
                    member.encoding,
                    int(member.is_binary),
                    member.text_status,
                    member.artifact_type,
                    member.classification_basis,
                    member.confidence,
                    member.validation_status,
                    now_iso(),
                ),
            )

    def add_correction(
        self,
        *,
        entity_kind: str,
        selector: str,
        action: str,
        scope_run_id: str | None = None,
        corrected_type: str | None = None,
        corrected_name: str | None = None,
        corrected_status: str | None = None,
        corrected_confidence: float | None = None,
        reason: str = "",
        attributes: dict[str, Any] | None = None,
        active: bool = True,
    ) -> str:
        kind = entity_kind.upper()
        selected_action = action.upper()
        correction_id = stable_id(
            "correction",
            scope_run_id or "GLOBAL",
            kind,
            selector,
            selected_action,
            corrected_type or "",
            corrected_name or "",
        )
        with self.connect() as conn:
            conn.execute(
                """
                INSERT OR REPLACE INTO discovery_correction(
                    correction_id, scope_run_id, entity_kind, selector, action,
                    corrected_type, corrected_name, corrected_status,
                    corrected_confidence, reason, active, attributes_json, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    correction_id,
                    scope_run_id,
                    kind,
                    selector,
                    selected_action,
                    corrected_type.upper() if corrected_type else None,
                    corrected_name.upper() if corrected_name else None,
                    corrected_status,
                    corrected_confidence,
                    reason,
                    int(active),
                    json.dumps(attributes or {}, sort_keys=True),
                    now_iso(),
                ),
            )
        return correction_id

    def list_corrections(
        self,
        run_id: str | None = None,
        *,
        entity_kind: str | None = None,
        active_only: bool = True,
    ) -> list[dict[str, Any]]:
        conditions = ["1=1"]
        params: list[Any] = []
        if run_id:
            conditions.append("(scope_run_id IS NULL OR scope_run_id = ?)")
            params.append(run_id)
        if entity_kind:
            conditions.append("entity_kind = ?")
            params.append(entity_kind.upper())
        if active_only:
            conditions.append("active = 1")
        with self.connect() as conn:
            rows = conn.execute(
                f"""
                SELECT *
                FROM discovery_correction
                WHERE {" AND ".join(conditions)}
                ORDER BY created_at DESC, entity_kind, selector
                """,
                params,
            ).fetchall()
        return [self._correction_row(row) for row in rows]

    def replace_scorecard_result(self, run_id: str, name: str, payload: dict[str, Any]) -> str:
        scorecard_id = stable_id(run_id, "scorecard", name)
        with self.connect() as conn:
            conn.execute(
                """
                INSERT OR REPLACE INTO scorecard_result(
                    scorecard_id, run_id, name, expected_count, matched_count,
                    missing_count, unexpected_count, precision, recall, status,
                    details_json, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    scorecard_id,
                    run_id,
                    name,
                    int(payload.get("expected_count") or 0),
                    int(payload.get("matched_count") or 0),
                    int(payload.get("missing_count") or 0),
                    int(payload.get("unexpected_count") or 0),
                    float(payload.get("precision") or 0.0),
                    float(payload.get("recall") or 0.0),
                    str(payload.get("status") or "unknown"),
                    json.dumps(payload.get("details") or {}, sort_keys=True),
                    now_iso(),
                ),
            )
        return scorecard_id

    def list_scorecards(self, run_id: str, *, limit: int = 50) -> list[dict[str, Any]]:
        with self.connect() as conn:
            rows = conn.execute(
                """
                SELECT *
                FROM scorecard_result
                WHERE run_id = ?
                ORDER BY created_at DESC, name
                LIMIT ?
                """,
                (run_id, min(max(limit, 1), 500)),
            ).fetchall()
        return [self._scorecard_row(row) for row in rows]

    def replace_validation_results(self, run_id: str, checks: list[dict[str, Any]]) -> None:
        with self.connect() as conn:
            conn.execute("DELETE FROM validation_result WHERE run_id = ?", (run_id,))
            for check in checks:
                check_name = str(check.get("check_name") or check.get("name") or "unknown")
                validation_id = stable_id(run_id, "validation", check_name)
                conn.execute(
                    """
                    INSERT INTO validation_result(
                        validation_id, run_id, check_name, status, details_json, created_at
                    ) VALUES (?, ?, ?, ?, ?, ?)
                    """,
                    (
                        validation_id,
                        run_id,
                        check_name,
                        str(check.get("status") or "unknown"),
                        json.dumps(check.get("details") or {}, sort_keys=True),
                        now_iso(),
                    ),
                )

    def upsert_root_summary(self, run_id: str, root_asset_id: str, payload: dict[str, Any]) -> None:
        with self.connect() as conn:
            conn.execute(
                """
                INSERT OR REPLACE INTO root_summary(
                    run_id, root_asset_id, reachable_assets, reachable_programs,
                    data_touchpoints, unresolved_count, risk_score, capability_label, summary_json
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    run_id,
                    root_asset_id,
                    payload.get("reachable_assets", 0),
                    payload.get("reachable_programs", 0),
                    payload.get("data_touchpoints", 0),
                    payload.get("unresolved_count", 0),
                    payload.get("risk_score", 0.0),
                    payload.get("capability_label", "Needs Review"),
                    json.dumps(payload, sort_keys=True),
                ),
            )

    def upsert_cluster(self, run_id: str, name: str, payload: dict[str, Any]) -> str:
        cluster_id = stable_id(run_id, "cluster", name)
        with self.connect() as conn:
            conn.execute(
                """
                INSERT OR REPLACE INTO app_cluster(
                    cluster_id, run_id, name, root_asset_id, asset_count, program_count,
                    data_count, unresolved_count, risk_score, attributes_json
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    cluster_id,
                    run_id,
                    name,
                    payload.get("root_asset_id"),
                    payload.get("asset_count", 0),
                    payload.get("program_count", 0),
                    payload.get("data_count", 0),
                    payload.get("unresolved_count", 0),
                    payload.get("risk_score", 0.0),
                    json.dumps(payload, sort_keys=True),
                ),
            )
        return cluster_id

    def upsert_degrees(self, run_id: str, degrees: Iterable[tuple[str, int, int]]) -> None:
        with self.connect() as conn:
            conn.executemany(
                """
                INSERT OR REPLACE INTO node_degree(run_id, asset_id, in_degree, out_degree, total_degree)
                VALUES (?, ?, ?, ?, ?)
                """,
                [(run_id, asset_id, in_d, out_d, in_d + out_d) for asset_id, in_d, out_d in degrees],
            )

    def get_cached_slice(self, cache_key: str) -> dict[str, Any] | None:
        with self.connect() as conn:
            row = conn.execute(
                "SELECT payload_json FROM graph_slice_cache WHERE cache_key = ?", (cache_key,)
            ).fetchone()
            return json.loads(row["payload_json"]) if row else None

    def put_cached_slice(
        self,
        *,
        cache_key: str,
        run_id: str,
        root_asset_id: str,
        mode: str,
        depth: int,
        limit: int,
        relationship_types: Iterable[str],
        confidence_min: float,
        payload: dict[str, Any],
    ) -> None:
        with self.connect() as conn:
            conn.execute(
                """
                INSERT OR REPLACE INTO graph_slice_cache(
                    cache_key, run_id, root_asset_id, mode, depth, limit_count,
                    relationship_types, confidence_min, payload_json, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    cache_key,
                    run_id,
                    root_asset_id,
                    mode,
                    depth,
                    limit,
                    ",".join(relationship_types),
                    confidence_min,
                    json.dumps(payload, sort_keys=True),
                    now_iso(),
                ),
            )

    def get_cached_parse(self, cache_key: str) -> dict[str, Any] | None:
        with self.connect() as conn:
            row = conn.execute(
                "SELECT payload_json FROM parser_result_cache WHERE cache_key = ?", (cache_key,)
            ).fetchone()
            return json.loads(row["payload_json"]) if row else None

    def put_cached_parse(
        self,
        *,
        cache_key: str,
        source_sha256: str,
        resolver_fingerprint: str,
        parser_version: str,
        payload: dict[str, Any],
    ) -> None:
        with self.connect() as conn:
            conn.execute(
                """
                INSERT OR REPLACE INTO parser_result_cache(
                    cache_key, source_sha256, resolver_fingerprint, parser_version,
                    payload_json, created_at
                ) VALUES (?, ?, ?, ?, ?, ?)
                """,
                (
                    cache_key,
                    source_sha256,
                    resolver_fingerprint,
                    parser_version,
                    json.dumps(payload, sort_keys=True),
                    now_iso(),
                ),
            )

    @staticmethod
    def _json_row(row, field: str) -> dict[str, Any]:
        item = dict(row)
        item["attributes"] = json.loads(item.pop(field))
        return item

    @staticmethod
    def _asset_row(row) -> dict[str, Any]:
        item = dict(row)
        if "attributes_json" in item:
            item["attributes"] = json.loads(item.pop("attributes_json"))
        return item

    @staticmethod
    def _relationship_row(row) -> dict[str, Any]:
        item = dict(row)
        if "attributes_json" in item:
            item["attributes"] = json.loads(item.pop("attributes_json"))
        return item

    @staticmethod
    def _correction_row(row) -> dict[str, Any]:
        item = dict(row)
        item["active"] = bool(item.get("active"))
        item["attributes"] = json.loads(item.pop("attributes_json"))
        return item

    @staticmethod
    def _scorecard_row(row) -> dict[str, Any]:
        item = dict(row)
        item["details"] = json.loads(item.pop("details_json"))
        return item

    @staticmethod
    def _scan_progress_row(row) -> dict[str, Any]:
        item = dict(row)
        item["details"] = json.loads(item.pop("details_json"))
        return item
