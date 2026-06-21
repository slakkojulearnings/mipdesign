from __future__ import annotations

import csv
import hashlib
import io
import json
from pathlib import Path
from typing import Any, Callable

from .demo_seed import seed_demo
from .domain_architecture import DomainArchitectureService
from .graph_service import GraphService
from .models import GraphSliceRequest
from .repositories import SQLiteGraphRepository
from .reverse_bundle import write_reverse_engineering_bundle
from .scorecards import load_scorecard, run_scorecard


class IntelligenceApi:
    """Framework-neutral API facade used by CLI, tests, and FastAPI adapters."""

    def __init__(self, db_path: str | Path) -> None:
        self.repository = SQLiteGraphRepository(db_path)
        self.repository.initialize()
        self.graph = GraphService(self.repository)
        self.domain_architecture = DomainArchitectureService(self.repository)

    def init_demo(self) -> dict[str, Any]:
        run_id = seed_demo(self.repository.db_path)
        return {"run_id": run_id, "database": str(self.repository.db_path)}

    def analyze(
        self,
        source_root: str | Path | None = None,
        *,
        demo: bool = False,
        config: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        if demo or source_root in {None, "", "demo", "demo://card-processing"}:
            payload = self.init_demo()
            return {"status": "COMPLETED", "mode": "demo", **payload}

        backend = self._ingestion_backend()
        if backend is None:
            return {
                "status": "backend_missing",
                "source_root": str(source_root),
                "message": "No ingestion service is registered yet.",
                "hook": "Expose analyze(source_root, db_path, config) from mip_intel.ingestion_service.",
            }

        result = backend(str(source_root), self.repository.db_path, config or {})
        return result if isinstance(result, dict) else {"status": "COMPLETED", "result": result}

    def current_run(self, run_id: str | None = None) -> str:
        selected = run_id or self.repository.latest_run_id()
        if selected is None:
            raise KeyError("no analysis run available")
        return selected

    def run_status(self, run_id: str | None = None) -> dict[str, Any]:
        selected = self.current_run(run_id)
        return {"run_id": selected, **self.stats(selected)}

    def stats(self, run_id: str | None = None) -> dict[str, Any]:
        return self.repository.stats(self.current_run(run_id))

    def validate(self, run_id: str | None = None) -> dict[str, Any]:
        selected = self.current_run(run_id)
        stats = self.stats(selected)
        with self.repository.connect() as conn:
            row = conn.execute(
                """
                SELECT
                    (SELECT COUNT(*) FROM asset a
                     WHERE a.run_id = ? AND NOT EXISTS (
                         SELECT 1 FROM evidence e
                         WHERE e.run_id = a.run_id AND e.entity_kind = 'ASSET'
                           AND e.entity_id = a.asset_id
                     )) AS assets_without_evidence,
                    (SELECT COUNT(*) FROM relationship r
                     WHERE r.run_id = ? AND NOT EXISTS (
                         SELECT 1 FROM evidence e
                         WHERE e.run_id = r.run_id AND e.entity_kind = 'RELATIONSHIP'
                           AND e.entity_id = r.relationship_id
                     )) AS relationships_without_evidence,
                    (SELECT COUNT(*) FROM asset
                     WHERE run_id = ? AND validation_status <> 'confirmed') AS asset_review_count,
                    (SELECT COUNT(*) FROM relationship
                     WHERE run_id = ? AND validation_status <> 'confirmed') AS relationship_review_count,
                    (SELECT COUNT(*) FROM asset
                     WHERE run_id = ? AND confidence < 1.0) AS low_confidence_assets,
                    (SELECT COUNT(*) FROM relationship
                     WHERE run_id = ? AND confidence < 1.0) AS low_confidence_relationships,
                    (SELECT COUNT(*) FROM asset
                     WHERE run_id = ? AND asset_type = 'UNRESOLVED') AS unresolved_assets,
                    (SELECT COUNT(*) FROM asset
                     WHERE run_id = ? AND (confidence < 0 OR confidence > 1)) AS invalid_asset_confidence,
                    (SELECT COUNT(*) FROM relationship
                     WHERE run_id = ? AND (confidence < 0 OR confidence > 1)) AS invalid_relationship_confidence,
                    (SELECT COUNT(*) FROM evidence
                     WHERE run_id = ? AND (confidence < 0 OR confidence > 1)) AS invalid_evidence_confidence,
                    (SELECT COUNT(*) FROM asset
                     WHERE run_id = ? AND validation_status NOT IN ('confirmed', 'inferred', 'needs_review')) AS invalid_asset_status,
                    (SELECT COUNT(*) FROM relationship
                     WHERE run_id = ? AND validation_status NOT IN ('confirmed', 'inferred', 'needs_review')) AS invalid_relationship_status,
                    (SELECT COUNT(*) FROM evidence
                     WHERE run_id = ? AND validation_status NOT IN ('confirmed', 'inferred', 'needs_review')) AS invalid_evidence_status,
                    (SELECT COUNT(*) FROM evidence
                     WHERE run_id = ? AND line_start IS NOT NULL AND line_end IS NOT NULL
                       AND line_start > line_end) AS invalid_evidence_ranges
                """,
                (
                    selected,
                    selected,
                    selected,
                    selected,
                    selected,
                    selected,
                    selected,
                    selected,
                    selected,
                    selected,
                    selected,
                    selected,
                    selected,
                    selected,
                ),
            ).fetchone()
        checks = [
            self._check("run_exists", stats["run"] is not None, stats["run"] or {}),
            self._check("assets_have_evidence", row["assets_without_evidence"] == 0, {
                "missing_count": row["assets_without_evidence"],
            }),
            self._check("relationships_have_evidence", row["relationships_without_evidence"] == 0, {
                "missing_count": row["relationships_without_evidence"],
            }),
            self._check("review_items_are_visible", True, {
                "asset_review_count": row["asset_review_count"],
                "relationship_review_count": row["relationship_review_count"],
                "unresolved_assets": row["unresolved_assets"],
            }),
            self._check("confidence_gaps_are_visible", True, {
                "low_confidence_assets": row["low_confidence_assets"],
                "low_confidence_relationships": row["low_confidence_relationships"],
            }),
            self._check("confidence_values_in_range", (
                row["invalid_asset_confidence"] == 0
                and row["invalid_relationship_confidence"] == 0
                and row["invalid_evidence_confidence"] == 0
            ), {
                "invalid_asset_confidence": row["invalid_asset_confidence"],
                "invalid_relationship_confidence": row["invalid_relationship_confidence"],
                "invalid_evidence_confidence": row["invalid_evidence_confidence"],
            }),
            self._check("validation_status_values_allowed", (
                row["invalid_asset_status"] == 0
                and row["invalid_relationship_status"] == 0
                and row["invalid_evidence_status"] == 0
            ), {
                "invalid_asset_status": row["invalid_asset_status"],
                "invalid_relationship_status": row["invalid_relationship_status"],
                "invalid_evidence_status": row["invalid_evidence_status"],
            }),
            self._check("evidence_line_ranges_valid", row["invalid_evidence_ranges"] == 0, {
                "invalid_evidence_ranges": row["invalid_evidence_ranges"],
            }),
        ]
        failed = [check for check in checks if check["status"] != "passed"]
        self.repository.replace_validation_results(selected, checks)
        return {
            "run_id": selected,
            "status": "failed" if failed else "passed",
            "checks": checks,
            "stats": stats,
        }

    def performance(self, run_id: str | None = None, *, limit: int = 25) -> dict[str, Any]:
        selected = self.current_run(run_id)
        with self.repository.connect() as conn:
            phases = [
                dict(row)
                for row in conn.execute(
                    """
                    SELECT phase, ROUND(SUM(elapsed_ms), 3) AS elapsed_ms,
                           MAX(memory_peak_bytes) AS memory_peak_bytes, COUNT(*) AS samples
                    FROM scan_phase_telemetry
                    WHERE run_id = ?
                    GROUP BY phase
                    ORDER BY SUM(elapsed_ms) DESC
                    """,
                    (selected,),
                )
            ]
            slow_files = [
                self._file_telemetry_row(row)
                for row in conn.execute(
                    """
                    SELECT *
                    FROM scan_file_telemetry
                    WHERE run_id = ?
                    ORDER BY total_ms DESC, relative_path
                    LIMIT ?
                    """,
                    (selected, min(max(limit, 1), 200)),
                )
            ]
            by_type = [
                dict(row)
                for row in conn.execute(
                    """
                    SELECT artifact_type, COUNT(*) AS file_count,
                           ROUND(SUM(total_ms), 3) AS total_ms,
                           SUM(reused_classification) AS reused_classifications,
                           SUM(parse_cache_hit) AS parse_cache_hits
                    FROM scan_file_telemetry
                    WHERE run_id = ?
                    GROUP BY artifact_type
                    ORDER BY total_ms DESC
                    """,
                    (selected,),
                )
            ]
        return {
            "run_id": selected,
            "phases": phases,
            "slow_files": slow_files,
            "by_artifact_type": by_type,
            "feedback_loop": {
                "use": "Sort slow_files and by_artifact_type to tune copybook paths, parser timeouts, worker counts, and classification rules.",
                "next_action": "Rerun with incremental:true and compare reused_classifications and parse_cache_hits.",
            },
        }

    def add_correction(
        self,
        *,
        entity_kind: str,
        selector: str,
        action: str,
        run_id: str | None = None,
        corrected_type: str | None = None,
        corrected_name: str | None = None,
        corrected_status: str | None = None,
        corrected_confidence: float | None = None,
        reason: str = "",
    ) -> dict[str, Any]:
        correction_id = self.repository.add_correction(
            scope_run_id=run_id,
            entity_kind=entity_kind,
            selector=selector,
            action=action,
            corrected_type=corrected_type,
            corrected_name=corrected_name,
            corrected_status=corrected_status,
            corrected_confidence=corrected_confidence,
            reason=reason,
        )
        return {"correction_id": correction_id, "status": "stored"}

    def corrections(
        self,
        run_id: str | None = None,
        *,
        entity_kind: str | None = None,
        active_only: bool = True,
    ) -> dict[str, Any]:
        selected = run_id or self.repository.latest_run_id()
        return {
            "run_id": selected,
            "corrections": self.repository.list_corrections(selected, entity_kind=entity_kind, active_only=active_only),
        }

    def run_scorecard(self, manifest_path: str | Path, run_id: str | None = None) -> dict[str, Any]:
        selected = self.current_run(run_id)
        return run_scorecard(self.repository, selected, load_scorecard(manifest_path))

    def scorecards(self, run_id: str | None = None, *, limit: int = 50) -> dict[str, Any]:
        selected = self.current_run(run_id)
        return {"run_id": selected, "scorecards": self.repository.list_scorecards(selected, limit=limit)}

    def roots(self, run_id: str | None = None, limit: int = 200) -> dict[str, Any]:
        return self.graph.root_portfolio(self.current_run(run_id), limit=limit)

    def clusters(self, run_id: str | None = None, limit: int = 200) -> dict[str, Any]:
        return self.graph.application_clusters(self.current_run(run_id), limit=limit)

    def domain_contexts(self, run_id: str | None = None, limit: int = 50) -> dict[str, Any]:
        return self.domain_architecture.bounded_contexts(self.current_run(run_id), limit=limit)

    def service_candidates(self, run_id: str | None = None, limit: int = 50) -> dict[str, Any]:
        return self.domain_architecture.service_candidates(self.current_run(run_id), limit=limit)

    def modernization_roadmap(self, run_id: str | None = None, limit: int = 50) -> dict[str, Any]:
        return self.domain_architecture.modernization_roadmap(self.current_run(run_id), limit=limit)

    def search(
        self, query: str, run_id: str | None = None, limit: int = 50, offset: int = 0
    ) -> dict[str, Any]:
        return self.graph.search(self.current_run(run_id), query, limit=limit, offset=offset)

    def nodes(
        self,
        run_id: str | None = None,
        *,
        scope: str = "programs",
        q: str = "",
        limit: int = 200,
        offset: int = 0,
    ) -> dict[str, Any]:
        selected = self.current_run(run_id)
        selected_scope = scope.lower().replace("-", "_")
        max_limit = min(max(limit, 1), 500)
        max_offset = max(offset, 0)
        needle = f"%{q.upper()}%"
        type_by_scope = {
            "programs": "PROGRAM",
            "jobs": "JOB",
            "tables": "TABLE",
            "copybooks": "COPYBOOK",
            "transactions": "TRANSACTION",
        }
        with self.repository.connect() as conn:
            if selected_scope == "roots":
                params: list[Any] = [selected]
                query_clause = ""
                if q:
                    query_clause = "AND (UPPER(a.technical_name) LIKE ? OR UPPER(a.display_name) LIKE ?)"
                    params.extend([needle, needle])
                params.extend([max_limit, max_offset])
                rows = conn.execute(
                    f"""
                    SELECT a.*, sm.relative_path, 1 AS is_root
                    FROM root_summary rs
                    JOIN asset a ON a.asset_id = rs.root_asset_id
                    LEFT JOIN source_member sm ON sm.member_id = a.member_id
                    WHERE rs.run_id = ?
                    {query_clause}
                    ORDER BY rs.risk_score DESC, a.technical_name
                    LIMIT ? OFFSET ?
                    """,
                    params,
                ).fetchall()
            else:
                params = [selected]
                filters = ["a.run_id = ?"]
                if selected_scope == "normal_programs":
                    filters.append("a.asset_type = 'PROGRAM'")
                    filters.append("rs.root_asset_id IS NULL")
                elif selected_scope in type_by_scope:
                    filters.append("a.asset_type = ?")
                    params.append(type_by_scope[selected_scope])
                elif selected_scope != "all":
                    filters.append("a.asset_type = 'PROGRAM'")
                    selected_scope = "programs"
                if q:
                    filters.append("(UPPER(a.technical_name) LIKE ? OR UPPER(a.display_name) LIKE ?)")
                    params.extend([needle, needle])
                params.extend([max_limit, max_offset])
                rows = conn.execute(
                    f"""
                    SELECT a.*, sm.relative_path,
                           CASE WHEN rs.root_asset_id IS NULL THEN 0 ELSE 1 END AS is_root
                    FROM asset a
                    LEFT JOIN source_member sm ON sm.member_id = a.member_id
                    LEFT JOIN root_summary rs ON rs.run_id = a.run_id AND rs.root_asset_id = a.asset_id
                    WHERE {" AND ".join(filters)}
                    ORDER BY
                        CASE a.asset_type
                            WHEN 'PROGRAM' THEN 0
                            WHEN 'JOB' THEN 1
                            WHEN 'TRANSACTION' THEN 2
                            WHEN 'TABLE' THEN 3
                            WHEN 'COPYBOOK' THEN 4
                            ELSE 5
                        END,
                        a.technical_name
                    LIMIT ? OFFSET ?
                    """,
                    params,
                ).fetchall()
        return {
            "run_id": selected,
            "scope": selected_scope,
            "query": q,
            "limit": max_limit,
            "offset": max_offset,
            "nodes": [self.repository._asset_row(row) for row in rows],
        }

    def graph_slice(
        self,
        root_asset_id: str,
        run_id: str | None = None,
        mode: str = "neighborhood",
        direction: str = "both",
        depth: int = 1,
        limit: int = 500,
        relationship_types: tuple[str, ...] = (),
        confidence_min: float = 0.0,
    ) -> dict[str, Any]:
        selected = self.current_run(run_id)
        seed_asset_id = self.resolve_asset_id(selected, root_asset_id)
        return self.graph.graph_slice(
            GraphSliceRequest(
                run_id=selected,
                root_asset_id=seed_asset_id,
                mode=mode,
                direction=direction,
                depth=depth,
                limit=limit,
                relationship_types=relationship_types,
                confidence_min=confidence_min,
            )
        )

    def node(self, asset_id: str, run_id: str | None = None) -> dict[str, Any]:
        selected = self.current_run(run_id)
        resolved = self.resolve_asset_id(selected, asset_id)
        return self.graph.node_profile(selected, resolved)

    def coverage(self, asset: str, run_id: str | None = None) -> dict[str, Any]:
        profile = self.node(asset, run_id)
        return {
            "run_id": self.current_run(run_id),
            "asset": {
                "asset_id": profile["asset"]["asset_id"],
                "technical_name": profile["asset"]["technical_name"],
                "asset_type": profile["asset"]["asset_type"],
                "confidence": profile["asset"]["confidence"],
                "validation_status": profile["asset"]["validation_status"],
            },
            "coverage_report": profile["coverage_report"],
        }

    def edge(self, relationship_id: str, run_id: str | None = None) -> dict[str, Any]:
        return self.graph.edge_profile(self.current_run(run_id), relationship_id)

    def heatmap(
        self,
        left_type: str,
        right_type: str,
        relationship_type: str,
        run_id: str | None = None,
    ) -> dict[str, Any]:
        return self.graph.heatmap(self.current_run(run_id), left_type, right_type, relationship_type)

    def call_graph(
        self,
        asset: str,
        run_id: str | None = None,
        *,
        direction: str = "both",
        depth: int = 8,
        limit: int = 1500,
    ) -> dict[str, Any]:
        selected = self.current_run(run_id)
        asset_id = self.resolve_asset_id(selected, asset)
        return self.graph.call_graph(selected, asset_id, direction=direction, depth=depth, limit=limit)

    def dependency_graph(
        self,
        asset: str,
        run_id: str | None = None,
        *,
        direction: str = "both",
        depth: int = 4,
        limit: int = 1500,
    ) -> dict[str, Any]:
        selected = self.current_run(run_id)
        asset_id = self.resolve_asset_id(selected, asset)
        return self.graph.dependency_graph(selected, asset_id, direction=direction, depth=depth, limit=limit)

    def required_files(
        self,
        asset: str,
        run_id: str | None = None,
        *,
        depth: int = 8,
        limit: int = 5000,
    ) -> dict[str, Any]:
        selected = self.current_run(run_id)
        asset_id = self.resolve_asset_id(selected, asset)
        return self.graph.required_files(selected, asset_id, depth=depth, limit=limit)

    def ast_tree(self, asset: str, run_id: str | None = None) -> dict[str, Any]:
        selected = self.current_run(run_id)
        asset_id = self.resolve_asset_id(selected, asset)
        return self.graph.ast_tree(selected, asset_id)

    def export_bundle(
        self,
        asset: str,
        output_dir: str | Path,
        run_id: str | None = None,
        *,
        depth: int = 8,
        limit: int = 5000,
        include_sources: bool = True,
    ) -> dict[str, Any]:
        payload = self.required_files(asset, run_id, depth=depth, limit=limit)
        return write_reverse_engineering_bundle(payload, output_dir, include_sources=include_sources)

    def export(
        self,
        run_id: str | None = None,
        *,
        format: str = "json",
        limit: int = 5000,
    ) -> dict[str, Any] | str:
        selected = self.current_run(run_id)
        fmt = format.lower()
        max_rows = min(max(limit, 1), 50000)
        with self.repository.connect() as conn:
            totals = conn.execute(
                """
                SELECT
                    (SELECT COUNT(*) FROM asset WHERE run_id = ?) AS total_assets,
                    (SELECT COUNT(*) FROM relationship WHERE run_id = ?) AS total_relationships
                """,
                (selected, selected),
            ).fetchone()
            assets = [
                self.repository._asset_row(row)
                for row in conn.execute(
                    """
                    SELECT a.*, sm.relative_path
                    FROM asset a LEFT JOIN source_member sm ON sm.member_id = a.member_id
                    WHERE a.run_id = ?
                    ORDER BY a.asset_type, a.technical_name
                    LIMIT ?
                    """,
                    (selected, max_rows),
                )
            ]
            relationships = [
                self.repository._relationship_row(row)
                for row in conn.execute(
                    """
                    SELECT r.*, s.technical_name AS source_name, s.asset_type AS source_type,
                           t.technical_name AS target_name, t.asset_type AS target_type
                    FROM relationship r
                    JOIN asset s ON s.asset_id = r.source_asset_id
                    JOIN asset t ON t.asset_id = r.target_asset_id
                    WHERE r.run_id = ?
                    ORDER BY r.relationship_type, source_name, target_name
                    LIMIT ?
                    """,
                    (selected, max_rows),
                )
            ]
        manifest = self._export_manifest(selected, max_rows, dict(totals), assets, relationships)
        if fmt == "cytoscape":
            return {
                "run_id": selected,
                "format": fmt,
                "manifest": manifest,
                "elements": {
                    "nodes": [{"data": {"id": item["asset_id"], **item}} for item in assets],
                    "edges": [
                        {
                            "data": {
                                "id": item["relationship_id"],
                                "source": item["source_asset_id"],
                                "target": item["target_asset_id"],
                                **item,
                            }
                        }
                        for item in relationships
                    ],
                },
            }
        if fmt == "csv":
            return self._csv_export(assets, relationships)
        return {
            "run_id": selected,
            "format": "json",
            "truncated": manifest["truncated"],
            "manifest": manifest,
            "nodes": assets,
            "edges": relationships,
            "assets": assets,
            "relationships": relationships,
        }

    def insights(self, run_id: str | None = None, limit: int = 50) -> dict[str, Any]:
        selected = self.current_run(run_id)
        persisted = self._persisted_insights(selected, limit)
        if persisted:
            return {"run_id": selected, "insights": persisted}

        roots = self.roots(selected, limit=limit)["roots"]
        clusters = self.clusters(selected, limit=limit)["clusters"]
        validation = self.validate(selected)
        items: list[dict[str, Any]] = []
        for root in roots[: min(limit, 20)]:
            items.append(
                {
                    "insight_type": "root_risk",
                    "subject_asset_id": root["asset_id"],
                    "title": f"{root['technical_name']} drives {root.get('reachable_assets', 0)} assets",
                    "body": (
                        f"{root['technical_name']} reaches {root.get('reachable_programs', 0)} programs "
                        f"and {root.get('data_touchpoints', 0)} data touchpoints."
                    ),
                    "confidence": root.get("confidence", 1.0),
                    "validation_status": root.get("validation_status", "confirmed"),
                    "citations": [{"entity_kind": "ASSET", "entity_id": root["asset_id"]}],
                }
            )
        for cluster in clusters[: min(limit, 20)]:
            items.append(
                {
                    "insight_type": "cluster",
                    "subject_asset_id": cluster.get("root_asset_id"),
                    "title": f"{cluster['name']} cluster has risk {cluster.get('risk_score', 0.0)}",
                    "body": (
                        f"{cluster.get('program_count', 0)} programs, "
                        f"{cluster.get('data_count', 0)} data assets, "
                        f"{cluster.get('unresolved_count', 0)} unresolved relationships."
                    ),
                    "confidence": 0.8,
                    "validation_status": "inferred",
                    "citations": [{"entity_kind": "CLUSTER", "entity_id": cluster["cluster_id"]}],
                }
            )
        if validation["status"] != "passed":
            items.insert(
                0,
                {
                    "insight_type": "validation",
                    "subject_asset_id": None,
                    "title": "Validation gaps require review",
                    "body": "Some graph facts are missing direct evidence.",
                    "confidence": 1.0,
                    "validation_status": "needs_review",
                    "citations": [],
                },
            )
        return {"run_id": selected, "insights": items[:limit]}

    def resolve_asset_id(self, run_id: str, identifier: str) -> str:
        direct = self.repository.get_asset(identifier)
        if direct and direct["run_id"] == run_id:
            return identifier
        query = identifier.upper()
        with self.repository.connect() as conn:
            row = conn.execute(
                """
                SELECT asset_id
                FROM asset
                WHERE run_id = ? AND UPPER(technical_name) = ?
                ORDER BY
                    CASE asset_type
                        WHEN 'PROGRAM' THEN 0
                        WHEN 'JOB' THEN 1
                        WHEN 'TRANSACTION' THEN 2
                        ELSE 3
                    END,
                    asset_type
                LIMIT 1
                """,
                (run_id, query),
            ).fetchone()
        if row:
            return str(row["asset_id"])
        raise KeyError(f"asset not found: {identifier}")

    def _ingestion_backend(self) -> Callable[[str, Path, dict[str, Any]], dict[str, Any]] | None:
        for module_name in ("mip_intel.ingestion_service", "mip_intel.ingestion"):
            try:
                module = __import__(module_name, fromlist=["analyze"])
            except ImportError:
                continue
            analyze = getattr(module, "analyze", None)
            if callable(analyze):
                return analyze
            scan = getattr(module, "scan_mainframe_tree", None)
            if callable(scan):
                return self._scan_adapter(scan)
        return None

    @staticmethod
    def _scan_adapter(scan: Callable[..., dict[str, Any]]) -> Callable[[str, Path, dict[str, Any]], dict[str, Any]]:
        def run(source_root: str, db_path: Path, config: dict[str, Any]) -> dict[str, Any]:
            run_id = config.get("run_id")
            return scan(source_root, db_path, run_id=run_id, config=config)

        return run

    def _persisted_insights(self, run_id: str, limit: int) -> list[dict[str, Any]]:
        with self.repository.connect() as conn:
            rows = conn.execute(
                """
                SELECT *
                FROM insight
                WHERE run_id = ?
                ORDER BY created_at, insight_type, title
                LIMIT ?
                """,
                (run_id, min(max(limit, 1), 200)),
            ).fetchall()
        items = []
        for row in rows:
            item = dict(row)
            item["citations"] = json_loads(item.pop("citations_json"), [])
            items.append(item)
        return items

    @staticmethod
    def _export_manifest(
        run_id: str,
        row_limit: int,
        totals: dict[str, Any],
        assets: list[dict[str, Any]],
        relationships: list[dict[str, Any]],
    ) -> dict[str, Any]:
        total_assets = int(totals.get("total_assets") or 0)
        total_relationships = int(totals.get("total_relationships") or 0)
        digest_payload = {"run_id": run_id, "assets": assets, "relationships": relationships}
        checksum = hashlib.sha256(
            json.dumps(digest_payload, sort_keys=True, default=str).encode("utf-8")
        ).hexdigest()
        return {
            "run_id": run_id,
            "storage_backend": "sqlite",
            "row_limit": row_limit,
            "total_assets": total_assets,
            "total_relationships": total_relationships,
            "exported_assets": len(assets),
            "exported_relationships": len(relationships),
            "truncated": len(assets) < total_assets or len(relationships) < total_relationships,
            "truncated_sections": {
                "assets": len(assets) < total_assets,
                "relationships": len(relationships) < total_relationships,
                "nodes": len(assets) < total_assets,
                "edges": len(relationships) < total_relationships,
            },
            "terminology": {
                "nodes": "graph nodes; legacy table/API alias is assets",
                "edges": "graph edges; legacy table/API alias is relationships",
            },
            "checksum_sha256": checksum,
        }

    @staticmethod
    def _check(check_name: str, passed: bool, details: dict[str, Any]) -> dict[str, Any]:
        return {"check_name": check_name, "status": "passed" if passed else "failed", "details": details}

    @staticmethod
    def _csv_export(assets: list[dict[str, Any]], relationships: list[dict[str, Any]]) -> str:
        output = io.StringIO()
        writer = csv.writer(output)
        writer.writerow(["section", "id", "type", "source", "target", "name", "confidence", "status"])
        for asset in assets:
            writer.writerow(
                [
                    "asset",
                    asset["asset_id"],
                    asset["asset_type"],
                    "",
                    "",
                    asset["technical_name"],
                    asset["confidence"],
                    asset["validation_status"],
                ]
            )
        for rel in relationships:
            writer.writerow(
                [
                    "relationship",
                    rel["relationship_id"],
                    rel["relationship_type"],
                    rel["source_asset_id"],
                    rel["target_asset_id"],
                    "",
                    rel["confidence"],
                    rel["validation_status"],
                ]
            )
        return output.getvalue()

    @staticmethod
    def _file_telemetry_row(row) -> dict[str, Any]:
        item = dict(row)
        item["reused_classification"] = bool(item.get("reused_classification"))
        item["parse_cache_hit"] = bool(item.get("parse_cache_hit"))
        item["skipped"] = bool(item.get("skipped"))
        item["details"] = json_loads(item.pop("details_json"), {})
        return item


def json_loads(value: str, default: Any) -> Any:
    try:
        return json.loads(value)
    except ValueError:
        return default


def create_fastapi_app(db_path: str | Path = "data/mip-intel.db"):
    """Optional FastAPI adapter. Imported lazily so core tests do not need FastAPI."""
    from fastapi import FastAPI, HTTPException, Query
    from fastapi.middleware.cors import CORSMiddleware

    api = IntelligenceApi(db_path)
    app = FastAPI(title="MIP Enterprise Intelligence", version="0.1.0")
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_methods=["*"],
        allow_headers=["*"],
    )

    @app.post("/demo")
    def init_demo() -> dict[str, Any]:
        return api.init_demo()

    @app.post("/analyze")
    def analyze(source_root: str | None = None, demo: bool = False) -> dict[str, Any]:
        payload = api.analyze(source_root, demo=demo)
        if payload.get("status") == "backend_missing":
            raise HTTPException(501, payload)
        return payload

    @app.get("/stats")
    def stats(run_id: str | None = None) -> dict[str, Any]:
        return api.stats(run_id)

    @app.get("/runs/status")
    def latest_run_status() -> dict[str, Any]:
        return api.run_status()

    @app.get("/runs/{run_id}/status")
    def run_status(run_id: str) -> dict[str, Any]:
        return api.run_status(run_id)

    @app.get("/validate")
    def validate(run_id: str | None = None) -> dict[str, Any]:
        return api.validate(run_id)

    @app.get("/performance")
    def performance(run_id: str | None = None, limit: int = Query(default=25, ge=1, le=200)):
        return api.performance(run_id, limit=limit)

    @app.get("/corrections")
    def corrections(
        run_id: str | None = None,
        entity_kind: str | None = None,
        active_only: bool = True,
    ):
        return api.corrections(run_id, entity_kind=entity_kind, active_only=active_only)

    @app.post("/corrections")
    def add_correction(
        entity_kind: str,
        selector: str,
        action: str,
        run_id: str | None = None,
        corrected_type: str | None = None,
        corrected_name: str | None = None,
        corrected_status: str | None = None,
        corrected_confidence: float | None = None,
        reason: str = "",
    ):
        return api.add_correction(
            run_id=run_id,
            entity_kind=entity_kind,
            selector=selector,
            action=action,
            corrected_type=corrected_type,
            corrected_name=corrected_name,
            corrected_status=corrected_status,
            corrected_confidence=corrected_confidence,
            reason=reason,
        )

    @app.get("/scorecards")
    def scorecards(run_id: str | None = None, limit: int = Query(default=50, ge=1, le=500)):
        return api.scorecards(run_id, limit=limit)

    @app.post("/scorecards/run")
    def run_scorecard_endpoint(manifest_path: str, run_id: str | None = None):
        return api.run_scorecard(manifest_path, run_id)

    @app.get("/roots")
    def roots(run_id: str | None = None, limit: int = Query(default=200, ge=1, le=1000)):
        return api.roots(run_id, limit)

    @app.get("/clusters")
    def clusters(run_id: str | None = None, limit: int = Query(default=200, ge=1, le=500)):
        return api.clusters(run_id, limit)

    @app.get("/architecture/contexts")
    def domain_contexts(run_id: str | None = None, limit: int = Query(default=50, ge=1, le=200)):
        return api.domain_contexts(run_id, limit)

    @app.get("/architecture/services")
    def service_candidates(run_id: str | None = None, limit: int = Query(default=50, ge=1, le=200)):
        return api.service_candidates(run_id, limit)

    @app.get("/architecture/roadmap")
    def modernization_roadmap(run_id: str | None = None, limit: int = Query(default=50, ge=1, le=200)):
        return api.modernization_roadmap(run_id, limit)

    @app.get("/search")
    def search(
        q: str,
        run_id: str | None = None,
        limit: int = Query(default=50, ge=1, le=200),
        offset: int = Query(default=0, ge=0),
    ):
        return api.search(q, run_id, limit, offset)

    @app.get("/nodes")
    def nodes(
        run_id: str | None = None,
        scope: str = "programs",
        q: str = "",
        limit: int = Query(default=200, ge=1, le=500),
        offset: int = Query(default=0, ge=0),
    ):
        return api.nodes(run_id, scope=scope, q=q, limit=limit, offset=offset)

    @app.get("/graph/slice")
    def graph_slice(
        root_asset_id: str,
        run_id: str | None = None,
        mode: str = "neighborhood",
        direction: str = "both",
        depth: int = Query(default=1, ge=0, le=8),
        limit: int = Query(default=500, ge=1, le=1500),
        relationship_types: str = "",
        confidence_min: float = Query(default=0.0, ge=0.0, le=1.0),
    ):
        rels = tuple(item.strip() for item in relationship_types.split(",") if item.strip())
        return api.graph_slice(root_asset_id, run_id, mode, direction, depth, limit, rels, confidence_min)

    @app.get("/nodes/{asset_id}")
    def node(asset_id: str, run_id: str | None = None):
        try:
            return api.node(asset_id, run_id)
        except KeyError as exc:
            raise HTTPException(404, str(exc)) from exc

    @app.get("/coverage/{asset}")
    def coverage(asset: str, run_id: str | None = None):
        try:
            return api.coverage(asset, run_id)
        except KeyError as exc:
            raise HTTPException(404, str(exc)) from exc

    @app.get("/edges/{relationship_id}")
    def edge(relationship_id: str, run_id: str | None = None):
        try:
            return api.edge(relationship_id, run_id)
        except KeyError as exc:
            raise HTTPException(404, str(exc)) from exc

    @app.get("/heatmap")
    def heatmap(left_type: str, right_type: str, relationship_type: str, run_id: str | None = None):
        return api.heatmap(left_type, right_type, relationship_type, run_id)

    @app.get("/graphs/call")
    def call_graph(
        asset: str,
        run_id: str | None = None,
        direction: str = "both",
        depth: int = Query(default=8, ge=0, le=12),
        limit: int = Query(default=1500, ge=1, le=10000),
    ):
        try:
            return api.call_graph(asset, run_id, direction=direction, depth=depth, limit=limit)
        except KeyError as exc:
            raise HTTPException(404, str(exc)) from exc

    @app.get("/graphs/dependencies")
    def dependency_graph(
        asset: str,
        run_id: str | None = None,
        direction: str = "both",
        depth: int = Query(default=4, ge=0, le=12),
        limit: int = Query(default=1500, ge=1, le=10000),
    ):
        try:
            return api.dependency_graph(asset, run_id, direction=direction, depth=depth, limit=limit)
        except KeyError as exc:
            raise HTTPException(404, str(exc)) from exc

    @app.get("/reverse/files")
    def required_files(
        asset: str,
        run_id: str | None = None,
        depth: int = Query(default=8, ge=0, le=12),
        limit: int = Query(default=5000, ge=1, le=10000),
    ):
        try:
            return api.required_files(asset, run_id, depth=depth, limit=limit)
        except KeyError as exc:
            raise HTTPException(404, str(exc)) from exc

    @app.get("/ast")
    def ast(asset: str, run_id: str | None = None):
        try:
            return api.ast_tree(asset, run_id)
        except KeyError as exc:
            raise HTTPException(404, str(exc)) from exc

    @app.get("/export")
    def export(
        run_id: str | None = None,
        format: str = "json",
        limit: int = Query(default=5000, ge=1, le=50000),
    ):
        payload = api.export(run_id, format=format, limit=limit)
        if format.lower() == "csv":
            return {"run_id": api.current_run(run_id), "format": "csv", "content": payload}
        return payload

    @app.get("/insights")
    def insights(run_id: str | None = None, limit: int = Query(default=50, ge=1, le=200)):
        return api.insights(run_id, limit)

    return app
