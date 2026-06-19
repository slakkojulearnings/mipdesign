from __future__ import annotations

from collections import deque
from typing import Any

from .capability_naming import name_card_capability
from .models import GraphSliceRequest
from .repositories import SQLiteGraphRepository


CONTROL_RELS = {"CALLS", "DYNAMIC_CALL", "EXECUTES", "STARTS_PROGRAM", "STARTS_TRANSACTION"}
DATA_RELS = {
    "USES_COPYBOOK",
    "READS_TABLE",
    "WRITES_TABLE",
    "READS_FILE",
    "WRITES_FILE",
    "READS_DATASET",
    "WRITES_DATASET",
    "USES_QUEUE",
    "USES_MAP",
}
RISKY_STATUSES = {"needs_review", "inferred"}
CALL_GRAPH_RELS = CONTROL_RELS | {"TRIGGERS"}
DEPENDENCY_RELS = CALL_GRAPH_RELS | DATA_RELS | {"READS_DATASET", "WRITES_DATASET"}


class GraphService:
    def __init__(self, repository: SQLiteGraphRepository) -> None:
        self.repository = repository

    def graph_slice(self, request: GraphSliceRequest) -> dict[str, Any]:
        req = request.normalized()
        cached = self.repository.get_cached_slice(req.cache_key)
        if cached is not None:
            cached["cached"] = True
            return cached

        nodes: dict[str, dict[str, Any]] = {}
        edges: dict[str, dict[str, Any]] = {}
        queue: deque[tuple[str, int]] = deque([(req.root_asset_id, 0)])
        seen_depth = {req.root_asset_id: 0}
        truncated = False

        while queue and len(nodes) < req.limit:
            asset_id, depth = queue.popleft()
            asset = self.repository.get_asset(asset_id)
            if asset is None:
                continue
            nodes[asset_id] = self._node(asset, depth)
            if depth >= req.depth:
                continue

            for rel in self.repository.relationships_for_asset(
                req.run_id,
                asset_id,
                direction="both",
                relationship_types=req.relationship_types,
                confidence_min=req.confidence_min,
                limit=req.limit * 4,
            ):
                if rel["relationship_id"] not in edges:
                    edges[rel["relationship_id"]] = self._edge(rel)
                for neighbor in (rel["source_asset_id"], rel["target_asset_id"]):
                    if neighbor == asset_id:
                        continue
                    if neighbor not in seen_depth and len(nodes) + len(queue) < req.limit:
                        seen_depth[neighbor] = depth + 1
                        queue.append((neighbor, depth + 1))
                    elif neighbor not in seen_depth:
                        truncated = True

        visible_edges = [
            edge
            for edge in edges.values()
            if edge["source"] in nodes and edge["target"] in nodes
        ]
        payload = {
            "run_id": req.run_id,
            "root_asset_id": req.root_asset_id,
            "mode": req.mode,
            "depth": req.depth,
            "limit": req.limit,
            "truncated": truncated or bool(queue),
            "cached": False,
            "nodes": sorted(nodes.values(), key=lambda item: (item["depth"], item["label"])),
            "edges": visible_edges,
            "stats": {
                "node_count": len(nodes),
                "edge_count": len(visible_edges),
                "needs_review_edges": sum(
                    1 for edge in visible_edges if edge["validation_status"] in RISKY_STATUSES
                ),
            },
            "query_limits": {
                "requested_limit": request.limit,
                "effective_limit": req.limit,
                "requested_depth": request.depth,
                "effective_depth": req.depth,
                "relationship_fetch_limit_per_node": req.limit * 4,
                "truncated": truncated or bool(queue),
            },
        }
        self.repository.put_cached_slice(
            cache_key=req.cache_key,
            run_id=req.run_id,
            root_asset_id=req.root_asset_id,
            mode=req.mode,
            depth=req.depth,
            limit=req.limit,
            relationship_types=req.relationship_types,
            confidence_min=req.confidence_min,
            payload=payload,
        )
        return payload

    def node_profile(self, run_id: str, asset_id: str) -> dict[str, Any]:
        asset = self.repository.get_asset(asset_id)
        if asset is None:
            raise KeyError(f"asset not found: {asset_id}")
        incoming = self.repository.relationships_for_asset(run_id, asset_id, direction="in", limit=500)
        outgoing = self.repository.relationships_for_asset(run_id, asset_id, direction="out", limit=500)
        evidence = self.repository.evidence_for(run_id, "ASSET", asset_id)
        return {
            "asset": asset,
            "incoming": incoming,
            "outgoing": outgoing,
            "evidence": evidence,
            "metrics": {
                "incoming_count": len(incoming),
                "outgoing_count": len(outgoing),
                "unresolved_relationships": sum(
                    1 for rel in incoming + outgoing if rel["validation_status"] in RISKY_STATUSES
                ),
                "data_touchpoints": sum(1 for rel in outgoing if rel["relationship_type"] in DATA_RELS),
            },
            "functionality": self._functionality_label(asset, outgoing),
        }

    def edge_profile(self, run_id: str, relationship_id: str) -> dict[str, Any]:
        rel = self.repository.get_relationship(relationship_id)
        if rel is None:
            raise KeyError(f"relationship not found: {relationship_id}")
        return {
            "relationship": rel,
            "evidence": self.repository.evidence_for(run_id, "RELATIONSHIP", relationship_id),
        }

    def search(self, run_id: str, query: str, *, limit: int = 50, offset: int = 0) -> dict[str, Any]:
        return {
            "query": query,
            "limit": min(limit, 200),
            "offset": max(offset, 0),
            "results": self.repository.search_assets(run_id, query, limit=limit, offset=offset),
        }

    def root_portfolio(self, run_id: str, *, limit: int = 200) -> dict[str, Any]:
        return {"roots": self.repository.list_roots(run_id, limit=limit)}

    def application_clusters(self, run_id: str, *, limit: int = 200) -> dict[str, Any]:
        return {"clusters": self.repository.list_clusters(run_id, limit=limit)}

    def call_graph(
        self,
        run_id: str,
        asset_id: str,
        *,
        direction: str = "both",
        depth: int = 8,
        limit: int = 1500,
    ) -> dict[str, Any]:
        return self._relationship_graph(
            run_id,
            asset_id,
            direction=direction,
            depth=depth,
            limit=limit,
            relationship_types=CALL_GRAPH_RELS,
            graph_type="call_graph_360",
        )

    def dependency_graph(
        self,
        run_id: str,
        asset_id: str,
        *,
        direction: str = "both",
        depth: int = 4,
        limit: int = 1500,
    ) -> dict[str, Any]:
        return self._relationship_graph(
            run_id,
            asset_id,
            direction=direction,
            depth=depth,
            limit=limit,
            relationship_types=DEPENDENCY_RELS,
            graph_type="dependency_graph",
        )

    def required_files(
        self,
        run_id: str,
        asset_id: str,
        *,
        depth: int = 8,
        limit: int = 5000,
    ) -> dict[str, Any]:
        graph = self.dependency_graph(run_id, asset_id, direction="both", depth=depth, limit=limit)
        asset_ids = [node["id"] for node in graph["nodes"]]
        if not asset_ids:
            return {"run_id": run_id, "root_asset_id": asset_id, "files": [], "assets": [], "relationships": []}
        placeholders = ",".join("?" for _ in asset_ids)
        with self.repository.connect() as conn:
            run = conn.execute("SELECT * FROM run_manifest WHERE run_id = ?", (run_id,)).fetchone()
            asset_rows = conn.execute(
                f"""
                SELECT a.*, sm.relative_path, sm.folder_path AS source_folder_path,
                       sm.member_name, sm.sha256, sm.size_bytes, sm.encoding,
                       sm.text_status, sm.artifact_type, sm.classification_basis
                FROM asset a LEFT JOIN source_member sm ON sm.member_id = a.member_id
                WHERE a.run_id = ? AND a.asset_id IN ({placeholders})
                ORDER BY COALESCE(sm.relative_path, a.technical_name)
                """,
                (run_id, *asset_ids),
            ).fetchall()
            edge_ids = [edge["id"] for edge in graph["edges"]]
            if edge_ids:
                edge_placeholders = ",".join("?" for _ in edge_ids)
                evidence_sql = f"""
                    SELECT *
                    FROM evidence
                    WHERE run_id = ? AND (
                        entity_id IN ({placeholders}) OR entity_id IN ({edge_placeholders})
                    )
                    ORDER BY source_path, line_start
                    LIMIT 2000
                """
                evidence_params = (run_id, *asset_ids, *edge_ids)
            else:
                evidence_sql = f"""
                    SELECT *
                    FROM evidence
                    WHERE run_id = ? AND entity_id IN ({placeholders})
                    ORDER BY source_path, line_start
                    LIMIT 2000
                """
                evidence_params = (run_id, *asset_ids)
            evidence_rows = conn.execute(evidence_sql, evidence_params).fetchall()
        source_root = dict(run)["source_root"] if run else ""
        assets = [self.repository._asset_row(row) for row in asset_rows]
        files = []
        for asset in assets:
            relative_path = asset.get("relative_path")
            if not relative_path:
                continue
            absolute_path = ""
            if source_root and "://" not in source_root:
                relative_windows = relative_path.replace("/", "\\")
                clean_root = source_root.rstrip("/\\")
                candidate = f"{clean_root}\\{relative_windows}"
                absolute_path = candidate
            files.append(
                {
                    "asset_id": asset["asset_id"],
                    "asset_type": asset["asset_type"],
                    "technical_name": asset["technical_name"],
                    "relative_path": relative_path,
                    "absolute_path": absolute_path,
                    "folder_path": asset.get("source_folder_path"),
                    "member_name": asset.get("member_name"),
                    "artifact_type": asset.get("artifact_type"),
                    "sha256": asset.get("sha256"),
                    "size_bytes": asset.get("size_bytes"),
                    "encoding": asset.get("encoding"),
                    "text_status": asset.get("text_status"),
                    "confidence": asset.get("confidence"),
                    "validation_status": asset.get("validation_status"),
                }
            )
        ast_summaries = [
            {
                "asset_id": asset["asset_id"],
                "technical_name": asset["technical_name"],
                "relative_path": asset.get("relative_path"),
                "ast_summary": asset.get("attributes", {}).get("ast_summary"),
            }
            for asset in assets
            if asset.get("attributes", {}).get("ast_summary")
        ]
        minimal_context = {
            "programs": sorted(a["technical_name"] for a in assets if a["asset_type"] == "PROGRAM"),
            "jobs": sorted(a["technical_name"] for a in assets if a["asset_type"] == "JOB"),
            "copybooks": sorted(a["technical_name"] for a in assets if a["asset_type"] == "COPYBOOK"),
            "data_assets": sorted(
                a["technical_name"]
                for a in assets
                if a["asset_type"] in {"TABLE", "FILE", "DATASET", "MQ_QUEUE", "MAP"}
            ),
            "unresolved": sorted(a["technical_name"] for a in assets if a["validation_status"] in RISKY_STATUSES),
        }
        return {
            "run_id": run_id,
            "root_asset_id": asset_id,
            "source_root": source_root,
            "depth": depth,
            "limit": limit,
            "truncated": graph["truncated"],
            "files": files,
            "assets": assets,
            "relationships": graph["edges"],
            "evidence": [dict(row) for row in evidence_rows],
            "ast_summaries": ast_summaries,
            "minimal_context": minimal_context,
        }

    def ast_tree(self, run_id: str, asset_id: str) -> dict[str, Any]:
        del run_id
        asset = self.repository.get_asset(asset_id)
        if asset is None:
            raise KeyError(f"asset not found: {asset_id}")
        tree = asset.get("attributes", {}).get("ast_tree")
        return {
            "asset": asset,
            "ast_tree": tree
            or {
                "type": asset["asset_type"],
                "label": asset["technical_name"],
                "children": [],
                "parser": {"effective": "not_available"},
            },
        }

    def heatmap(self, run_id: str, left_type: str, right_type: str, rel_type: str) -> dict[str, Any]:
        # A compact matrix payload can drive virtualized tables or heatmaps without graph rendering.
        rows = []
        with self.repository.connect() as conn:
            for row in conn.execute(
                """
                SELECT s.technical_name AS left_name, t.technical_name AS right_name, COUNT(*) AS weight
                FROM relationship r
                JOIN asset s ON s.asset_id = r.source_asset_id
                JOIN asset t ON t.asset_id = r.target_asset_id
                WHERE r.run_id = ? AND s.asset_type = ? AND t.asset_type = ?
                  AND r.relationship_type = ?
                GROUP BY s.technical_name, t.technical_name
                ORDER BY weight DESC, left_name, right_name
                LIMIT 5000
                """,
                (run_id, left_type.upper(), right_type.upper(), rel_type.upper()),
            ):
                rows.append(dict(row))
        return {
            "run_id": run_id,
            "left_type": left_type.upper(),
            "right_type": right_type.upper(),
            "relationship_type": rel_type.upper(),
            "cells": rows,
        }

    def recompute_summaries(self, run_id: str) -> None:
        with self.repository.connect() as conn:
            conn.execute("DELETE FROM root_summary WHERE run_id = ?", (run_id,))
            conn.execute("DELETE FROM app_cluster WHERE run_id = ?", (run_id,))
            conn.execute("DELETE FROM node_degree WHERE run_id = ?", (run_id,))
            conn.execute("DELETE FROM graph_slice_cache WHERE run_id = ?", (run_id,))
        with self.repository.connect() as conn:
            asset_ids = [row["asset_id"] for row in conn.execute(
                "SELECT asset_id FROM asset WHERE run_id = ?", (run_id,)
            )]
            degrees = []
            for asset_id in asset_ids:
                in_d = conn.execute(
                    "SELECT COUNT(*) FROM relationship WHERE run_id = ? AND target_asset_id = ?",
                    (run_id, asset_id),
                ).fetchone()[0]
                out_d = conn.execute(
                    "SELECT COUNT(*) FROM relationship WHERE run_id = ? AND source_asset_id = ?",
                    (run_id, asset_id),
                ).fetchone()[0]
                degrees.append((asset_id, in_d, out_d))
        self.repository.upsert_degrees(run_id, degrees)

        roots = self._discover_roots(run_id)
        for root_id in roots:
            summary = self._root_summary(run_id, root_id)
            self.repository.upsert_root_summary(run_id, root_id, summary)
        clusters = self._community_clusters(run_id, roots)
        for cluster in clusters:
            self.repository.upsert_cluster(run_id, cluster["name"], cluster)

    def _relationship_graph(
        self,
        run_id: str,
        asset_id: str,
        *,
        direction: str,
        depth: int,
        limit: int,
        relationship_types: set[str],
        graph_type: str,
    ) -> dict[str, Any]:
        selected_direction = direction if direction in {"upstream", "downstream", "both"} else "both"
        rel_direction = {"upstream": "in", "downstream": "out"}.get(selected_direction, "both")
        max_depth = min(max(depth, 0), 12)
        max_limit = min(max(limit, 1), 10000)
        nodes: dict[str, dict[str, Any]] = {}
        edges: dict[str, dict[str, Any]] = {}
        queue: deque[tuple[str, int]] = deque([(asset_id, 0)])
        seen_depth = {asset_id: 0}
        truncated = False

        while queue and len(nodes) < max_limit:
            current_id, current_depth = queue.popleft()
            asset = self.repository.get_asset(current_id)
            if asset is None:
                continue
            nodes[current_id] = self._node(asset, current_depth)
            if current_depth >= max_depth:
                continue
            for rel in self.repository.relationships_for_asset(
                run_id,
                current_id,
                direction=rel_direction,
                relationship_types=relationship_types,
                limit=max_limit * 3,
            ):
                if rel["relationship_id"] not in edges:
                    edges[rel["relationship_id"]] = self._edge(rel)
                neighbors = self._next_neighbors(current_id, rel, selected_direction)
                for neighbor in neighbors:
                    if neighbor not in seen_depth and len(nodes) + len(queue) < max_limit:
                        seen_depth[neighbor] = current_depth + 1
                        queue.append((neighbor, current_depth + 1))
                    elif neighbor not in seen_depth:
                        truncated = True
        visible_edges = [
            edge for edge in edges.values() if edge["source"] in nodes and edge["target"] in nodes
        ]
        return {
            "run_id": run_id,
            "root_asset_id": asset_id,
            "graph_type": graph_type,
            "direction": selected_direction,
            "depth": max_depth,
            "limit": max_limit,
            "truncated": truncated or bool(queue),
            "nodes": sorted(nodes.values(), key=lambda item: (item["depth"], item["label"])),
            "edges": visible_edges,
            "stats": {
                "node_count": len(nodes),
                "edge_count": len(visible_edges),
                "upstream_edges": sum(1 for edge in visible_edges if edge["target"] == asset_id),
                "downstream_edges": sum(1 for edge in visible_edges if edge["source"] == asset_id),
                "needs_review_edges": sum(
                    1 for edge in visible_edges if edge["validation_status"] in RISKY_STATUSES
                ),
            },
        }

    @staticmethod
    def _next_neighbors(current_id: str, rel: dict[str, Any], direction: str) -> list[str]:
        if direction == "upstream":
            return [rel["source_asset_id"]] if rel["target_asset_id"] == current_id else []
        if direction == "downstream":
            return [rel["target_asset_id"]] if rel["source_asset_id"] == current_id else []
        return [
            neighbor
            for neighbor in (rel["source_asset_id"], rel["target_asset_id"])
            if neighbor != current_id
        ]

    def _community_clusters(self, run_id: str, roots: list[str]) -> list[dict[str, Any]]:
        with self.repository.connect() as conn:
            asset_rows = conn.execute(
                """
                SELECT a.*, sm.relative_path
                FROM asset a LEFT JOIN source_member sm ON sm.member_id = a.member_id
                WHERE a.run_id = ?
                """,
                (run_id,),
            ).fetchall()
            rel_rows = conn.execute(
                """
                SELECT r.*, s.technical_name AS source_name, s.asset_type AS source_type,
                       t.technical_name AS target_name, t.asset_type AS target_type
                FROM relationship r
                JOIN asset s ON s.asset_id = r.source_asset_id
                JOIN asset t ON t.asset_id = r.target_asset_id
                WHERE r.run_id = ?
                """,
                (run_id,),
            ).fetchall()
        assets = {row["asset_id"]: self.repository._asset_row(row) for row in asset_rows}
        if not assets:
            return []
        parent = {asset_id: asset_id for asset_id in assets}

        def find(value: str) -> str:
            while parent[value] != value:
                parent[value] = parent[parent[value]]
                value = parent[value]
            return value

        def union(left: str, right: str) -> None:
            if left not in parent or right not in parent:
                return
            l_root, r_root = find(left), find(right)
            if l_root != r_root:
                parent[r_root] = l_root

        signal_counts = {"relationships": 0, "folders": 0}
        for row in rel_rows:
            if row["relationship_type"] in DEPENDENCY_RELS:
                union(row["source_asset_id"], row["target_asset_id"])
                signal_counts["relationships"] += 1
        folder_first: dict[str, str] = {}
        for asset in assets.values():
            folder = self._top_folder(asset.get("folder_path") or asset.get("relative_path") or "")
            if not folder:
                continue
            first = folder_first.setdefault(folder, asset["asset_id"])
            union(first, asset["asset_id"])
            signal_counts["folders"] += 1

        components: dict[str, list[dict[str, Any]]] = {}
        for asset_id, asset in assets.items():
            components.setdefault(find(asset_id), []).append(asset)

        relationships_by_component: dict[str, list[dict[str, Any]]] = {key: [] for key in components}
        for row in rel_rows:
            root = find(row["source_asset_id"]) if row["source_asset_id"] in parent else None
            if root and root == find(row["target_asset_id"]):
                relationships_by_component.setdefault(root, []).append(self.repository._relationship_row(row))

        clusters = []
        root_set = set(roots)
        for index, (component_id, members) in enumerate(
            sorted(components.items(), key=lambda item: (-len(item[1]), item[0])), 1
        ):
            rels = relationships_by_component.get(component_id, [])
            root_asset_id = next((asset["asset_id"] for asset in members if asset["asset_id"] in root_set), None)
            if root_asset_id is None:
                root_asset_id = self._best_component_root(members, rels)
            naming = self._capability_naming(members, rels)
            label = naming["name"]
            unresolved = sum(1 for rel in rels if rel["validation_status"] in RISKY_STATUSES)
            data_count = sum(
                1
                for asset in members
                if asset["asset_type"] in {"TABLE", "FILE", "DATASET", "COPYBOOK", "MQ_QUEUE", "MAP"}
            )
            program_count = sum(1 for asset in members if asset["asset_type"] == "PROGRAM")
            confidence = self._cluster_confidence(members, rels)
            clusters.append(
                {
                    "name": f"{label} Cluster {index}" if label != "Needs Review" else f"Needs Review Cluster {index}",
                    "root_asset_id": root_asset_id,
                    "asset_count": len(members),
                    "program_count": program_count,
                    "data_count": data_count,
                    "unresolved_count": unresolved,
                    "risk_score": round(min(1.0, unresolved * 0.08 + len(members) / 3000.0), 3),
                    "confidence": round(max(confidence, naming["confidence"] if label != "Needs Review" else confidence), 3),
                    "validation_status": (
                        "inferred"
                        if max(confidence, naming["confidence"]) >= 0.65 and label != "Needs Review"
                        else "needs_review"
                    ),
                    "method": "evidence_graph_components",
                    "domain": naming["domain"],
                    "java_service_candidate": naming["java_service"],
                    "naming": naming,
                    "signals": {
                        "relationship_edges": len(rels),
                        "folder_signal_used": True,
                        "shared_data_and_copybook_affinity": True,
                        "llm_membership_used": False,
                        "domain_taxonomy_naming": True,
                        "llm_naming_allowed": True,
                    },
                    "sample_assets": [
                        {
                            "asset_id": asset["asset_id"],
                            "asset_type": asset["asset_type"],
                            "technical_name": asset["technical_name"],
                        }
                        for asset in sorted(members, key=lambda item: (item["asset_type"], item["technical_name"]))[:50]
                    ],
                    "evidence": {
                        "relationship_signal_count": signal_counts["relationships"],
                        "folder_signal_count": signal_counts["folders"],
                    },
                }
            )
        return clusters

    @staticmethod
    def _top_folder(path: str) -> str:
        clean = path.replace("\\", "/").strip("/")
        if not clean:
            return ""
        parts = clean.split("/")
        return "/".join(parts[:2]) if len(parts) > 1 and parts[0].lower() == "app" else parts[0]

    @staticmethod
    def _best_component_root(members: list[dict[str, Any]], rels: list[dict[str, Any]]) -> str | None:
        scores = {asset["asset_id"]: 0 for asset in members}
        for rel in rels:
            scores[rel["source_asset_id"]] = scores.get(rel["source_asset_id"], 0) + 2
            scores[rel["target_asset_id"]] = scores.get(rel["target_asset_id"], 0) + 1
        candidates = sorted(
            members,
            key=lambda asset: (
                asset["asset_type"] not in {"PROGRAM", "JOB", "TRANSACTION", "SCHEDULE"},
                -scores.get(asset["asset_id"], 0),
                asset["technical_name"],
            ),
        )
        return candidates[0]["asset_id"] if candidates else None

    def _capability_label_from_assets(self, members: list[dict[str, Any]], rels: list[dict[str, Any]]) -> str:
        return self._capability_naming(members, rels)["name"]

    @staticmethod
    def _capability_naming(members: list[dict[str, Any]], rels: list[dict[str, Any]]) -> dict[str, Any]:
        naming = name_card_capability(members, rels)
        if naming["name"] != "Needs Review":
            return naming
        return naming

    @staticmethod
    def _cluster_confidence(members: list[dict[str, Any]], rels: list[dict[str, Any]]) -> float:
        if not members:
            return 0.0
        if not rels:
            return 0.45
        confirmed = sum(1 for rel in rels if rel["validation_status"] == "confirmed")
        avg_edge_conf = sum(float(rel["confidence"]) for rel in rels) / len(rels)
        status_ratio = confirmed / len(rels)
        confidence = 0.35 + (avg_edge_conf * 0.35) + (status_ratio * 0.20) + min(len(rels), 25) / 250
        return round(min(confidence, 0.95), 3)

    def _discover_roots(self, run_id: str) -> list[str]:
        with self.repository.connect() as conn:
            program_rows = conn.execute(
                "SELECT asset_id FROM asset WHERE run_id = ? AND asset_type = 'PROGRAM'", (run_id,)
            ).fetchall()
            roots: list[str] = []
            for row in program_rows:
                asset_id = row["asset_id"]
                callers = conn.execute(
                    """
                    SELECT COUNT(*) FROM relationship
                    WHERE run_id = ? AND target_asset_id = ?
                      AND relationship_type IN ('CALLS', 'DYNAMIC_CALL')
                      AND validation_status = 'confirmed'
                    """,
                    (run_id, asset_id),
                ).fetchone()[0]
                entry = conn.execute(
                    """
                    SELECT COUNT(*) FROM relationship
                    WHERE run_id = ? AND target_asset_id = ?
                      AND relationship_type IN ('EXECUTES', 'STARTS_PROGRAM', 'TRIGGERS')
                    """,
                    (run_id, asset_id),
                ).fetchone()[0]
                if callers == 0 and entry > 0:
                    roots.append(asset_id)
            return roots

    def _root_summary(self, run_id: str, root_asset_id: str) -> dict[str, Any]:
        req = GraphSliceRequest(run_id=run_id, root_asset_id=root_asset_id, depth=8, limit=1500)
        payload = self.graph_slice(req)
        nodes = payload["nodes"]
        edges = payload["edges"]
        programs = [node for node in nodes if node["type"] == "PROGRAM"]
        data = [
            node
            for node in nodes
            if node["type"] in {"TABLE", "FILE", "DATASET", "COPYBOOK", "MQ_QUEUE", "MAP"}
        ]
        unresolved = [edge for edge in edges if edge["validation_status"] in RISKY_STATUSES]
        root = self.repository.get_asset(root_asset_id) or {}
        root_members = [node | {"asset_type": node["type"], "display_name": node["label"]} for node in nodes]
        naming = self._capability_naming(root_members, edges)
        label = naming["name"] if naming["name"] != "Needs Review" else self._functionality_label(root, edges)
        risk = min(1.0, (len(unresolved) * 0.08) + (len(nodes) / 3000.0))
        return {
            "reachable_assets": len(nodes),
            "reachable_programs": len(programs),
            "data_touchpoints": len(data),
            "unresolved_count": len(unresolved),
            "risk_score": round(risk, 3),
            "capability_label": label,
            "capability_naming": naming,
        }

    @staticmethod
    def _node(asset: dict[str, Any], depth: int) -> dict[str, Any]:
        return {
            "id": asset["asset_id"],
            "type": asset["asset_type"],
            "label": asset["display_name"],
            "technical_name": asset["technical_name"],
            "depth": depth,
            "confidence": asset["confidence"],
            "validation_status": asset["validation_status"],
            "folder_path": asset.get("folder_path"),
        }

    @staticmethod
    def _edge(rel: dict[str, Any]) -> dict[str, Any]:
        return {
            "id": rel["relationship_id"],
            "source": rel["source_asset_id"],
            "target": rel["target_asset_id"],
            "type": rel["relationship_type"],
            "confidence": rel["confidence"],
            "validation_status": rel["validation_status"],
            "discovery_method": rel["discovery_method"],
            "source_name": rel["source_name"],
            "target_name": rel["target_name"],
        }

    @staticmethod
    def _functionality_label(asset: dict[str, Any], relationships: list[dict[str, Any]]) -> str:
        naming = name_card_capability([asset], relationships)
        return naming["name"]
