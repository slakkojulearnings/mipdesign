from __future__ import annotations

import re
from collections import Counter, defaultdict
from typing import Any

import networkx as nx

from mip.persistence import SQLiteRepository

_TECHNICAL_RELATIONSHIPS = {
    "CALLS",
    "DYNAMIC_CALL",
    "READS_TABLE",
    "WRITES_TABLE",
    "READS_FILE",
    "WRITES_FILE",
    "READS_DATASET",
    "WRITES_DATASET",
    "USES_COPYBOOK",
    "PUTS_MESSAGE",
    "GETS_MESSAGE",
}


class ServiceBoundaryDiscoveryService:
    """Proposes service boundaries using graph communities plus data and rule affinity."""

    def __init__(self, repository: SQLiteRepository, run_id: str | None = None) -> None:
        self.repository = repository
        self.run_id = run_id or repository.latest_run_id()

    def discover(self, minimum_programs: int = 1) -> dict[str, Any]:
        assets = self.repository.list_assets(run_id=self.run_id, limit=1_000_000)
        relationships = self.repository.relationship_rows(self.run_id)
        programs = {
            item["id"]: item
            for item in assets
            if item["asset_type"] == "PROGRAM" and item["status"] == "OBSERVED"
        }
        graph = nx.Graph()
        graph.add_nodes_from(programs)
        shared_targets: dict[str, set[str]] = defaultdict(set)
        for rel in relationships:
            if rel["relationship_type"] not in _TECHNICAL_RELATIONSHIPS:
                continue
            source = rel["source_asset_id"]
            target = rel["target_asset_id"]
            if source in programs and target in programs:
                weight = graph.get_edge_data(source, target, {}).get("weight", 0) + 3
                graph.add_edge(source, target, weight=weight)
            elif source in programs:
                shared_targets[target].add(source)
        for users in shared_targets.values():
            ordered = sorted(users)
            for index, left in enumerate(ordered):
                for right in ordered[index + 1 :]:
                    weight = graph.get_edge_data(left, right, {}).get("weight", 0) + 1
                    graph.add_edge(left, right, weight=weight)

        if not graph.nodes:
            return {"service_count": 0, "services": []}
        communities = list(nx.community.greedy_modularity_communities(graph, weight="weight"))
        # Isolated nodes are still valid single-capability boundaries.
        assigned = set().union(*communities) if communities else set()
        communities.extend([{node} for node in graph.nodes if node not in assigned])

        service_candidates: list[dict[str, Any]] = []
        for number, community in enumerate(communities, 1):
            if len(community) < minimum_programs:
                continue
            members = [programs[item] for item in sorted(community)]
            member_ids = set(community)
            internal = 0
            external = 0
            data_targets: Counter[str] = Counter()
            for rel in relationships:
                source_inside = rel["source_asset_id"] in member_ids
                target_inside = rel["target_asset_id"] in member_ids
                if source_inside and target_inside:
                    internal += 1
                elif source_inside or target_inside:
                    external += 1
                if source_inside and rel["relationship_type"] in {
                    "READS_TABLE",
                    "WRITES_TABLE",
                    "READS_FILE",
                    "WRITES_FILE",
                    "READS_DATASET",
                    "WRITES_DATASET",
                }:
                    data_targets[rel["target_name"]] += 1
            cohesion = internal / max(internal + external, 1)
            coupling = external / max(internal + external, 1)
            name = self._name(members, number)
            service_candidates.append(
                {
                    "service_name": name,
                    "programs": [member["technical_name"] for member in members],
                    "shared_data": [item for item, _ in data_targets.most_common(10)],
                    "internal_relationships": internal,
                    "external_relationships": external,
                    "cohesion": round(cohesion, 3),
                    "coupling": round(coupling, 3),
                    "fitness_score": round(
                        max(0.0, min(100.0, 50 + cohesion * 50 - coupling * 20)), 2
                    ),
                    "confidence": round(min(0.95, 0.55 + len(members) * 0.04 + cohesion * 0.2), 2),
                    "recommended_pattern": "MODULAR_MONOLITH"
                    if coupling > 0.55
                    else "EXTRACTABLE_SERVICE",
                    "evidence": {
                        "community_algorithm": "greedy_modularity",
                        "member_count": len(members),
                        "shared_data_count": len(data_targets),
                    },
                }
            )
        return {
            "service_count": len(service_candidates),
            "services": sorted(
                service_candidates, key=lambda item: item["fitness_score"], reverse=True
            ),
        }

    @staticmethod
    def _name(members: list[dict[str, Any]], number: int) -> str:
        tokens: Counter[str] = Counter()
        for member in members:
            for token in re.split(r"[^A-Z0-9]+", member["technical_name"].upper()):
                if len(token) >= 3 and token not in {
                    "PGM",
                    "PROG",
                    "PROGRAM",
                    "MAIN",
                    "DRV",
                    "DRIVER",
                }:
                    tokens[token] += 1
        common = tokens.most_common(1)
        return f"{common[0][0].title()}Service" if common else f"LegacyCapabilityService{number}"
