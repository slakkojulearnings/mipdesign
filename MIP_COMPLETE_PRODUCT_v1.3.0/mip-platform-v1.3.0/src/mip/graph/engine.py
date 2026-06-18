from __future__ import annotations

from collections import deque
from typing import Any, cast

import networkx as nx

from mip.models import AssetType, RelationshipType
from mip.persistence.sqlite import SQLiteRepository

DEPENDENCY_RELATIONSHIPS = {
    RelationshipType.CALLS.value,
    RelationshipType.DYNAMIC_CALL.value,
    RelationshipType.EXECUTES.value,
    RelationshipType.CONTAINS_STEP.value,
    RelationshipType.USES_PROCEDURE.value,
    RelationshipType.USES_COPYBOOK.value,
    RelationshipType.READS_TABLE.value,
    RelationshipType.WRITES_TABLE.value,
    RelationshipType.READS_DATASET.value,
    RelationshipType.WRITES_DATASET.value,
    RelationshipType.USES_DATASET.value,
    RelationshipType.READS_FILE.value,
    RelationshipType.WRITES_FILE.value,
    RelationshipType.STARTS_PROGRAM.value,
    RelationshipType.USES_MAP.value,
    RelationshipType.IMPLEMENTS_RULE.value,
    RelationshipType.EXPANDS_TO.value,
    RelationshipType.RESOLVES_SYMBOL.value,
    RelationshipType.PUTS_MESSAGE.value,
    RelationshipType.GETS_MESSAGE.value,
    RelationshipType.USES_QUEUE.value,
    RelationshipType.CONTAINS_SEGMENT.value,
    RelationshipType.PARENT_SEGMENT.value,
    RelationshipType.SCHEDULES.value,
    RelationshipType.TRIGGERS.value,
}


class KnowledgeGraph:
    def __init__(self, repository: SQLiteRepository, run_id: str | None = None) -> None:
        self.repository = repository
        self.run_id = run_id or repository.latest_run_id()
        self.graph = nx.MultiDiGraph()
        if self.run_id:
            self._load()

    def _load(self) -> None:
        assert self.run_id is not None
        for asset in self.repository.list_assets(run_id=self.run_id, limit=1_000_000):
            attributes = {key: value for key, value in asset.items() if key not in {"attributes"}}
            attributes.update(asset["attributes"])
            self.graph.add_node(asset["id"], **attributes)
        for relationship in self.repository.relationship_rows(self.run_id):
            self.graph.add_edge(
                relationship["source_asset_id"],
                relationship["target_asset_id"],
                key=relationship["id"],
                relationship_type=relationship["relationship_type"],
                confidence=relationship["confidence"],
                **relationship["attributes"],
            )

    def resolve(self, name: str, asset_type: str | None = None) -> str:
        matches = self.repository.find_assets(name, asset_type, self.run_id)
        if not matches:
            raise KeyError(f"asset not found: {name}")
        observed = [item for item in matches if item["status"] == "OBSERVED"]
        return cast(str, (observed or matches)[0]["id"])

    def asset(self, node_id: str) -> dict[str, Any]:
        return dict(self.graph.nodes[node_id])

    def callers(self, program_name: str) -> list[dict[str, Any]]:
        node_id = self.resolve(program_name, AssetType.PROGRAM.value)
        results: list[dict[str, Any]] = []
        for source, _, data in self.graph.in_edges(node_id, data=True):
            if data.get("relationship_type") == RelationshipType.CALLS.value:
                results.append(self.asset(source))
        return sorted(results, key=lambda item: item["technical_name"])

    def callees(self, program_name: str) -> list[dict[str, Any]]:
        node_id = self.resolve(program_name, AssetType.PROGRAM.value)
        results: list[dict[str, Any]] = []
        for _, target, data in self.graph.out_edges(node_id, data=True):
            if data.get("relationship_type") in {
                RelationshipType.CALLS.value,
                RelationshipType.DYNAMIC_CALL.value,
            }:
                results.append(self.asset(target))
        return sorted(results, key=lambda item: item["technical_name"])

    def jobs_executing(self, program_name: str) -> list[dict[str, Any]]:
        program_id = self.resolve(program_name, AssetType.PROGRAM.value)
        jobs: dict[str, dict[str, Any]] = {}
        for step_id, _, data in self.graph.in_edges(program_id, data=True):
            if data.get("relationship_type") != RelationshipType.EXECUTES.value:
                continue
            for job_id, _, parent_data in self.graph.in_edges(step_id, data=True):
                if parent_data.get("relationship_type") == RelationshipType.CONTAINS_STEP.value:
                    jobs[job_id] = self.asset(job_id)
        return sorted(jobs.values(), key=lambda item: item["technical_name"])

    def root_programs(self) -> list[dict[str, Any]]:
        results: list[dict[str, Any]] = []
        for node_id, data in self.graph.nodes(data=True):
            if data.get("asset_type") != AssetType.PROGRAM.value:
                continue
            has_caller = any(
                edge_data.get("relationship_type") == RelationshipType.CALLS.value
                for _, _, edge_data in self.graph.in_edges(node_id, data=True)
            )
            has_entry = any(
                edge_data.get("relationship_type")
                in {
                    RelationshipType.EXECUTES.value,
                    RelationshipType.STARTS_PROGRAM.value,
                    RelationshipType.TRIGGERS.value,
                }
                for _, _, edge_data in self.graph.in_edges(node_id, data=True)
            )
            if not has_caller and (has_entry or self.graph.in_degree(node_id) == 0):
                results.append(dict(data))
        return sorted(results, key=lambda item: item["technical_name"])

    def impact(
        self, name: str, asset_type: str | None = None, max_depth: int = 8
    ) -> dict[str, Any]:
        start = self.resolve(name, asset_type)
        impacted: dict[str, int] = {}
        queue: deque[tuple[str, int]] = deque([(start, 0)])
        visited = {start}

        while queue:
            current, depth = queue.popleft()
            if depth >= max_depth:
                continue
            for predecessor, _, edge_data in self.graph.in_edges(current, data=True):
                if edge_data.get("relationship_type") not in DEPENDENCY_RELATIONSHIPS:
                    continue
                if predecessor in visited:
                    continue
                visited.add(predecessor)
                impacted[predecessor] = depth + 1
                queue.append((predecessor, depth + 1))

            # A changed container such as a JOB also affects its owned steps.
            for _, child, edge_data in self.graph.out_edges(current, data=True):
                if edge_data.get("relationship_type") != RelationshipType.CONTAINS_STEP.value:
                    continue
                if child not in visited:
                    visited.add(child)
                    impacted[child] = depth + 1
                    queue.append((child, depth + 1))

        assets = [
            {**self.asset(node_id), "impact_depth": depth} for node_id, depth in impacted.items()
        ]
        assets.sort(
            key=lambda item: (item["impact_depth"], item["asset_type"], item["technical_name"])
        )
        counts: dict[str, int] = {}
        for item in assets:
            counts[item["asset_type"]] = counts.get(item["asset_type"], 0) + 1
        return {
            "source": self.asset(start),
            "blast_radius": len(assets),
            "counts_by_type": counts,
            "affected_assets": assets,
            "max_depth": max_depth,
        }

    def lineage(
        self, name: str, direction: str = "downstream", max_depth: int = 8
    ) -> dict[str, Any]:
        start = self.resolve(name)
        reverse = direction.lower() == "upstream"
        traversal_graph = self.graph.reverse(copy=False) if reverse else self.graph
        result: list[dict[str, Any]] = []
        for target, distance in nx.single_source_shortest_path_length(
            traversal_graph, start, cutoff=max_depth
        ).items():
            if target == start:
                continue
            item = self.asset(target)
            item["distance"] = distance
            result.append(item)
        result.sort(key=lambda item: (item["distance"], item["asset_type"], item["technical_name"]))
        return {
            "source": self.asset(start),
            "direction": direction,
            "assets": result,
        }

    def metrics(self) -> dict[str, Any]:
        simple = nx.DiGraph()
        simple.add_nodes_from(self.graph.nodes)
        simple.add_edges_from((source, target) for source, target in self.graph.edges())
        if not simple:
            return {"nodes": 0, "edges": 0, "components": 0, "top_degree": []}
        degree = nx.degree_centrality(simple)
        top = sorted(degree.items(), key=lambda item: item[1], reverse=True)[:20]
        return {
            "nodes": self.graph.number_of_nodes(),
            "edges": self.graph.number_of_edges(),
            "components": nx.number_weakly_connected_components(simple),
            "top_degree": [
                {**self.asset(node_id), "degree_centrality": score} for node_id, score in top
            ],
        }
