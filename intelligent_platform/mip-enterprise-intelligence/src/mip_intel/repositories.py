from __future__ import annotations

import json
import sqlite3
from abc import ABC, abstractmethod
from collections.abc import Iterable
from contextlib import contextmanager
from pathlib import Path
from typing import Any

from .models import Asset, Evidence, Relationship, SourceMember, now_iso, stable_id


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

    def create_run(self, source_root: str, *, run_id: str | None = None) -> str:
        self.initialize()
        selected = run_id or stable_id("run", source_root, now_iso())
        with self.connect() as conn:
            conn.execute(
                """
                INSERT OR REPLACE INTO run_manifest(run_id, source_root, started_at, status)
                VALUES (?, ?, ?, 'RUNNING')
                """,
                (selected, source_root, now_iso()),
            )
        return selected

    def complete_run(self, run_id: str, status: str = "COMPLETED") -> None:
        with self.connect() as conn:
            counts = conn.execute(
                """
                SELECT
                    (SELECT COUNT(*) FROM source_member WHERE run_id = ?) AS file_count,
                    (SELECT COUNT(*) FROM asset WHERE run_id = ?) AS asset_count,
                    (SELECT COUNT(*) FROM relationship WHERE run_id = ?) AS relationship_count,
                    (SELECT COUNT(*) FROM source_member WHERE run_id = ? AND artifact_type LIKE 'UNKNOWN%') AS unknown_count,
                    (SELECT COUNT(*) FROM source_member WHERE run_id = ? AND is_binary = 1) AS binary_count
                """,
                (run_id, run_id, run_id, run_id, run_id),
            ).fetchone()
            conn.execute(
                """
                UPDATE run_manifest
                SET completed_at = ?, status = ?, file_count = ?, asset_count = ?,
                    relationship_count = ?, unknown_count = ?, binary_count = ?
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
                self._insert_evidence(conn, asset.run_id, "ASSET", asset.asset_id, item)
        return asset.asset_id

    def insert_relationship(
        self, relationship: Relationship, evidence: Iterable[Evidence] = ()
    ) -> str:
        with self.connect() as conn:
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
            }

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
