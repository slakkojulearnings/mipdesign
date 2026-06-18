from __future__ import annotations

import json
import sqlite3
from collections.abc import Iterator
from contextlib import contextmanager
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from uuid import uuid4

from mip import __version__
from mip.models import (
    AssetCandidate,
    DiscoveredFile,
    EvidenceCandidate,
    ParseIssue,
    RelationshipCandidate,
)
from mip.utils.ids import stable_id


def utc_now() -> str:
    return datetime.now(UTC).isoformat()


class SQLiteRepository:
    def __init__(self, db_path: Path | str) -> None:
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)

    @contextmanager
    def connect(self) -> Iterator[sqlite3.Connection]:
        connection = sqlite3.connect(self.db_path)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys = ON")
        try:
            yield connection
            connection.commit()
        except Exception:
            connection.rollback()
            raise
        finally:
            connection.close()

    def initialize(self) -> None:
        schema_path = Path(__file__).with_name("schema.sql")
        with self.connect() as connection:
            connection.executescript(schema_path.read_text(encoding="utf-8"))

    def create_tenant(self, tenant_id: str, name: str | None = None) -> None:
        with self.connect() as connection:
            connection.execute(
                "INSERT OR IGNORE INTO tenant(id, name) VALUES (?, ?)",
                (tenant_id, name or tenant_id),
            )

    def list_tenants(self) -> list[dict[str, Any]]:
        self.initialize()
        with self.connect() as connection:
            return [
                dict(row)
                for row in connection.execute("SELECT * FROM tenant ORDER BY id").fetchall()
            ]

    def create_run(self, source_root: str) -> str:
        run_id = str(uuid4())
        with self.connect() as connection:
            connection.execute(
                """
                INSERT INTO scan_run(id, source_root, started_at, status, tool_version)
                VALUES (?, ?, ?, 'RUNNING', ?)
                """,
                (run_id, source_root, utc_now(), __version__),
            )
        return run_id

    def complete_run(self, run_id: str, *, status: str = "COMPLETED") -> None:
        with self.connect() as connection:
            counts = connection.execute(
                """
                SELECT
                  (SELECT COUNT(*) FROM source_file WHERE scan_id = ?) AS file_count,
                  (SELECT COUNT(*) FROM source_file WHERE scan_id = ? AND parse_status = 'PARSED') AS parsed_count,
                  (SELECT COUNT(*) FROM source_file WHERE scan_id = ? AND artifact_type IN ('UNKNOWN','BINARY')) AS unknown_count,
                  (SELECT COUNT(*) FROM asset WHERE scan_id = ?) AS asset_count,
                  (SELECT COUNT(*) FROM relationship WHERE scan_id = ?) AS relationship_count,
                  (SELECT COUNT(*) FROM parse_issue WHERE scan_id = ?) AS issue_count
                """,
                (run_id, run_id, run_id, run_id, run_id, run_id),
            ).fetchone()
            connection.execute(
                """
                UPDATE scan_run
                SET completed_at = ?, status = ?, file_count = ?, parsed_count = ?,
                    unknown_count = ?, asset_count = ?, relationship_count = ?, issue_count = ?
                WHERE id = ?
                """,
                (
                    utc_now(),
                    status,
                    counts["file_count"],
                    counts["parsed_count"],
                    counts["unknown_count"],
                    counts["asset_count"],
                    counts["relationship_count"],
                    counts["issue_count"],
                    run_id,
                ),
            )

    def insert_source_file(self, run_id: str, source: DiscoveredFile) -> str:
        source_id = stable_id(run_id, "SOURCE_FILE", source.relative_path)
        with self.connect() as connection:
            connection.execute(
                """
                INSERT OR REPLACE INTO source_file(
                    id, scan_id, relative_path, sha256, size_bytes, artifact_type,
                    classification_confidence, classification_reasons_json,
                    encoding, is_binary, parse_status
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'DISCOVERED')
                """,
                (
                    source_id,
                    run_id,
                    source.relative_path,
                    source.sha256,
                    source.size_bytes,
                    source.artifact_type.value,
                    source.classification_confidence,
                    json.dumps(source.classification_reasons, sort_keys=True),
                    source.encoding,
                    int(source.is_binary),
                ),
            )
        return source_id

    def mark_source_status(self, source_file_id: str, status: str) -> None:
        with self.connect() as connection:
            connection.execute(
                "UPDATE source_file SET parse_status = ? WHERE id = ?",
                (status, source_file_id),
            )

    def upsert_asset(
        self,
        run_id: str,
        candidate: AssetCandidate,
        source_file_id: str | None,
        *,
        placeholder: bool = False,
    ) -> str:
        asset_id = stable_id(run_id, candidate.asset_type.value, candidate.technical_name)
        status = "UNRESOLVED" if placeholder else "OBSERVED"
        with self.connect() as connection:
            existing = connection.execute(
                "SELECT * FROM asset WHERE id = ?", (asset_id,)
            ).fetchone()
            if existing:
                attributes = json.loads(existing["attributes_json"])
                attributes.update(candidate.attributes)
                confidence = max(float(existing["confidence"]), candidate.confidence)
                source_id = existing["source_file_id"] or source_file_id
                new_status = "OBSERVED" if not placeholder else existing["status"]
                connection.execute(
                    """
                    UPDATE asset SET source_file_id = ?, readable_name = COALESCE(?, readable_name),
                        attributes_json = ?, confidence = ?, status = ? WHERE id = ?
                    """,
                    (
                        source_id,
                        candidate.readable_name,
                        json.dumps(attributes, sort_keys=True),
                        confidence,
                        new_status,
                        asset_id,
                    ),
                )
            else:
                connection.execute(
                    """
                    INSERT INTO asset(
                        id, scan_id, source_file_id, asset_type, technical_name,
                        readable_name, attributes_json, confidence, status
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        asset_id,
                        run_id,
                        source_file_id,
                        candidate.asset_type.value,
                        candidate.technical_name,
                        candidate.readable_name,
                        json.dumps(candidate.attributes, sort_keys=True),
                        candidate.confidence,
                        status,
                    ),
                )
        return asset_id

    def insert_relationship(
        self,
        run_id: str,
        candidate: RelationshipCandidate,
        source_asset_id: str,
        target_asset_id: str,
    ) -> str:
        attributes_json = json.dumps(candidate.attributes, sort_keys=True)
        relationship_id = stable_id(
            run_id,
            candidate.relationship_type.value,
            source_asset_id,
            target_asset_id,
            attributes_json,
        )
        with self.connect() as connection:
            connection.execute(
                """
                INSERT OR IGNORE INTO relationship(
                    id, scan_id, relationship_type, source_asset_id,
                    target_asset_id, attributes_json, confidence, status
                ) VALUES (?, ?, ?, ?, ?, ?, ?, 'OBSERVED')
                """,
                (
                    relationship_id,
                    run_id,
                    candidate.relationship_type.value,
                    source_asset_id,
                    target_asset_id,
                    attributes_json,
                    candidate.confidence,
                ),
            )
        return relationship_id

    def insert_evidence(
        self,
        run_id: str,
        entity_kind: str,
        entity_id: str,
        evidence: EvidenceCandidate,
    ) -> str:
        evidence_id = stable_id(
            run_id,
            "EVIDENCE",
            entity_kind,
            entity_id,
            evidence.source_path,
            str(evidence.line_start),
            evidence.evidence_text,
        )
        with self.connect() as connection:
            connection.execute(
                """
                INSERT OR IGNORE INTO evidence(
                    id, scan_id, entity_kind, entity_id, source_path,
                    line_start, line_end, evidence_text, extractor, confidence
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
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
                    evidence.confidence,
                ),
            )
        return evidence_id

    def insert_issue(
        self,
        run_id: str,
        source_file_id: str | None,
        issue: ParseIssue,
    ) -> str:
        issue_id = stable_id(
            run_id,
            "ISSUE",
            issue.source_path,
            str(issue.line_number),
            issue.message,
        )
        with self.connect() as connection:
            connection.execute(
                """
                INSERT OR IGNORE INTO parse_issue(
                    id, scan_id, source_file_id, severity, message, line_number
                ) VALUES (?, ?, ?, ?, ?, ?)
                """,
                (
                    issue_id,
                    run_id,
                    source_file_id,
                    issue.severity,
                    issue.message,
                    issue.line_number,
                ),
            )
        return issue_id

    def latest_run_id(self) -> str | None:
        self.initialize()
        with self.connect() as connection:
            row = connection.execute(
                "SELECT id FROM scan_run ORDER BY started_at DESC LIMIT 1"
            ).fetchone()
            return str(row["id"]) if row else None

    def get_run(self, run_id: str | None = None) -> dict[str, Any] | None:
        selected = run_id or self.latest_run_id()
        if selected is None:
            return None
        with self.connect() as connection:
            row = connection.execute("SELECT * FROM scan_run WHERE id = ?", (selected,)).fetchone()
            return dict(row) if row else None

    def stats(self, run_id: str | None = None) -> dict[str, Any]:
        selected = run_id or self.latest_run_id()
        if selected is None:
            return {"run": None, "assets": {}, "files": {}, "relationships": {}}
        with self.connect() as connection:
            run = connection.execute("SELECT * FROM scan_run WHERE id = ?", (selected,)).fetchone()
            assets = connection.execute(
                "SELECT asset_type, COUNT(*) AS count FROM asset WHERE scan_id = ? GROUP BY asset_type ORDER BY asset_type",
                (selected,),
            ).fetchall()
            files = connection.execute(
                "SELECT artifact_type, COUNT(*) AS count FROM source_file WHERE scan_id = ? GROUP BY artifact_type ORDER BY artifact_type",
                (selected,),
            ).fetchall()
            relationships = connection.execute(
                "SELECT relationship_type, COUNT(*) AS count FROM relationship WHERE scan_id = ? GROUP BY relationship_type ORDER BY relationship_type",
                (selected,),
            ).fetchall()
            return {
                "run": dict(run) if run else None,
                "assets": {row["asset_type"]: row["count"] for row in assets},
                "files": {row["artifact_type"]: row["count"] for row in files},
                "relationships": {row["relationship_type"]: row["count"] for row in relationships},
            }

    def list_assets(
        self,
        asset_type: str | None = None,
        run_id: str | None = None,
        limit: int = 500,
    ) -> list[dict[str, Any]]:
        selected = run_id or self.latest_run_id()
        if selected is None:
            return []
        sql = "SELECT a.*, sf.relative_path AS source_path FROM asset a LEFT JOIN source_file sf ON sf.id = a.source_file_id WHERE a.scan_id = ?"
        params: list[Any] = [selected]
        if asset_type:
            sql += " AND a.asset_type = ?"
            params.append(asset_type.upper())
        sql += " ORDER BY a.asset_type, a.technical_name LIMIT ?"
        params.append(limit)
        with self.connect() as connection:
            rows = connection.execute(sql, params).fetchall()
            return [self._asset_row(row) for row in rows]

    def find_assets(
        self,
        name: str,
        asset_type: str | None = None,
        run_id: str | None = None,
    ) -> list[dict[str, Any]]:
        selected = run_id or self.latest_run_id()
        if selected is None:
            return []
        sql = "SELECT a.*, sf.relative_path AS source_path FROM asset a LEFT JOIN source_file sf ON sf.id = a.source_file_id WHERE a.scan_id = ? AND UPPER(a.technical_name) = UPPER(?)"
        params: list[Any] = [selected, name]
        if asset_type:
            sql += " AND a.asset_type = ?"
            params.append(asset_type.upper())
        with self.connect() as connection:
            return [self._asset_row(row) for row in connection.execute(sql, params)]

    def get_asset(self, asset_id: str) -> dict[str, Any] | None:
        with self.connect() as connection:
            row = connection.execute(
                "SELECT a.*, sf.relative_path AS source_path FROM asset a LEFT JOIN source_file sf ON sf.id = a.source_file_id WHERE a.id = ?",
                (asset_id,),
            ).fetchone()
            return self._asset_row(row) if row else None

    def relationship_rows(self, run_id: str | None = None) -> list[dict[str, Any]]:
        selected = run_id or self.latest_run_id()
        if selected is None:
            return []
        with self.connect() as connection:
            rows = connection.execute(
                """
                SELECT r.*, s.asset_type AS source_type, s.technical_name AS source_name,
                       t.asset_type AS target_type, t.technical_name AS target_name,
                       (SELECT e.source_path FROM evidence e WHERE e.entity_kind = 'RELATIONSHIP' AND e.entity_id = r.id ORDER BY e.line_start LIMIT 1) AS evidence_source_path,
                       (SELECT e.line_start FROM evidence e WHERE e.entity_kind = 'RELATIONSHIP' AND e.entity_id = r.id ORDER BY e.line_start LIMIT 1) AS evidence_line_start,
                       (SELECT e.line_end FROM evidence e WHERE e.entity_kind = 'RELATIONSHIP' AND e.entity_id = r.id ORDER BY e.line_start LIMIT 1) AS evidence_line_end
                FROM relationship r
                JOIN asset s ON s.id = r.source_asset_id
                JOIN asset t ON t.id = r.target_asset_id
                WHERE r.scan_id = ?
                ORDER BY r.relationship_type, s.technical_name, t.technical_name
                """,
                (selected,),
            ).fetchall()
            return [self._relationship_row(row) for row in rows]

    def relationships_for_asset(
        self, asset_id: str, direction: str = "both"
    ) -> list[dict[str, Any]]:
        conditions: list[str] = []
        params: list[Any] = []
        if direction in {"out", "both"}:
            conditions.append("r.source_asset_id = ?")
            params.append(asset_id)
        if direction in {"in", "both"}:
            conditions.append("r.target_asset_id = ?")
            params.append(asset_id)
        if not conditions:
            return []
        with self.connect() as connection:
            rows = connection.execute(
                f"""
                SELECT r.*, s.asset_type AS source_type, s.technical_name AS source_name,
                       t.asset_type AS target_type, t.technical_name AS target_name,
                       (SELECT e.source_path FROM evidence e WHERE e.entity_kind = 'RELATIONSHIP' AND e.entity_id = r.id ORDER BY e.line_start LIMIT 1) AS evidence_source_path,
                       (SELECT e.line_start FROM evidence e WHERE e.entity_kind = 'RELATIONSHIP' AND e.entity_id = r.id ORDER BY e.line_start LIMIT 1) AS evidence_line_start,
                       (SELECT e.line_end FROM evidence e WHERE e.entity_kind = 'RELATIONSHIP' AND e.entity_id = r.id ORDER BY e.line_start LIMIT 1) AS evidence_line_end
                FROM relationship r
                JOIN asset s ON s.id = r.source_asset_id
                JOIN asset t ON t.id = r.target_asset_id
                WHERE {" OR ".join(conditions)}
                ORDER BY r.relationship_type
                """,
                params,
            ).fetchall()
            return [self._relationship_row(row) for row in rows]

    def source_files(self, run_id: str | None = None) -> list[dict[str, Any]]:
        selected = run_id or self.latest_run_id()
        if selected is None:
            return []
        with self.connect() as connection:
            return [
                dict(row)
                for row in connection.execute(
                    "SELECT * FROM source_file WHERE scan_id = ? ORDER BY relative_path",
                    (selected,),
                )
            ]

    def recent_runs(self, limit: int = 10) -> list[dict[str, Any]]:
        with self.connect() as connection:
            return [
                dict(row)
                for row in connection.execute(
                    "SELECT * FROM scan_run ORDER BY started_at DESC LIMIT ?", (limit,)
                )
            ]

    def diff_runs(
        self, newer_run_id: str | None = None, older_run_id: str | None = None
    ) -> dict[str, Any]:
        runs = self.recent_runs(2)
        newer = newer_run_id or (runs[0]["id"] if runs else None)
        older = older_run_id or (runs[1]["id"] if len(runs) > 1 else None)
        if not newer or not older:
            return {
                "newer_run": newer,
                "older_run": older,
                "added": [],
                "removed": [],
                "changed": [],
            }
        newer_files = {row["relative_path"]: row for row in self.source_files(str(newer))}
        older_files = {row["relative_path"]: row for row in self.source_files(str(older))}
        added = sorted(set(newer_files) - set(older_files))
        removed = sorted(set(older_files) - set(newer_files))
        changed = sorted(
            path
            for path in set(newer_files) & set(older_files)
            if newer_files[path]["sha256"] != older_files[path]["sha256"]
        )
        return {
            "newer_run": newer,
            "older_run": older,
            "added": added,
            "removed": removed,
            "changed": changed,
        }

    def evidence_for_entity(self, entity_kind: str, entity_id: str) -> list[dict[str, Any]]:
        with self.connect() as connection:
            return [
                dict(row)
                for row in connection.execute(
                    "SELECT * FROM evidence WHERE entity_kind = ? AND entity_id = ? ORDER BY source_path, line_start",
                    (entity_kind.upper(), entity_id),
                )
            ]

    def insert_insight(
        self,
        run_id: str,
        insight_type: str,
        subject: str,
        payload: dict[str, Any],
        confidence: float = 0.5,
        status: str = "GENERATED",
    ) -> str:
        payload_json = json.dumps(payload, sort_keys=True, default=str)
        insight_id = stable_id(run_id, "INSIGHT", insight_type, subject, payload_json)
        with self.connect() as connection:
            connection.execute(
                """
                INSERT OR REPLACE INTO derived_insight(
                    id, scan_id, insight_type, subject, payload_json, confidence, status
                ) VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    insight_id,
                    run_id,
                    insight_type.upper(),
                    subject,
                    payload_json,
                    max(0.0, min(1.0, confidence)),
                    status,
                ),
            )
        return insight_id

    def list_insights(
        self,
        insight_type: str | None = None,
        run_id: str | None = None,
        limit: int = 1000,
    ) -> list[dict[str, Any]]:
        selected = run_id or self.latest_run_id()
        if selected is None:
            return []
        sql = "SELECT * FROM derived_insight WHERE scan_id = ?"
        params: list[Any] = [selected]
        if insight_type:
            sql += " AND insight_type = ?"
            params.append(insight_type.upper())
        sql += " ORDER BY insight_type, subject LIMIT ?"
        params.append(limit)
        with self.connect() as connection:
            rows = connection.execute(sql, params).fetchall()
            result: list[dict[str, Any]] = []
            for row in rows:
                item = dict(row)
                item["payload"] = json.loads(item.pop("payload_json"))
                result.append(item)
            return result

    def parse_issues(self, run_id: str | None = None) -> list[dict[str, Any]]:
        selected = run_id or self.latest_run_id()
        if selected is None:
            return []
        with self.connect() as connection:
            return [
                dict(row)
                for row in connection.execute(
                    "SELECT * FROM parse_issue WHERE scan_id = ? ORDER BY severity DESC, message",
                    (selected,),
                )
            ]

    @staticmethod
    def _asset_row(row: sqlite3.Row) -> dict[str, Any]:
        item = dict(row)
        item["attributes"] = json.loads(item.pop("attributes_json"))
        return item

    @staticmethod
    def _relationship_row(row: sqlite3.Row) -> dict[str, Any]:
        item = dict(row)
        item["attributes"] = json.loads(item.pop("attributes_json"))
        return item
