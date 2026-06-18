from __future__ import annotations

from collections import defaultdict, deque
from typing import Any

from mip.persistence import SQLiteRepository


class ModernizationSimulator:
    """Simulates retire, modify, extract-service, replatform, and data-change scenarios."""

    def __init__(self, repository: SQLiteRepository, run_id: str | None = None) -> None:
        self.repository = repository
        self.run_id = run_id or repository.latest_run_id()
        self.assets = self.repository.list_assets(run_id=self.run_id, limit=1_000_000)
        self.by_id = {item["id"]: item for item in self.assets}
        self.relationships = self.repository.relationship_rows(self.run_id)

    def simulate(
        self,
        target_name: str,
        scenario: str = "modify",
        max_depth: int = 10,
    ) -> dict[str, Any]:
        matches = self.repository.find_assets(target_name, run_id=self.run_id)
        if not matches:
            raise KeyError(f"asset not found: {target_name}")
        target = matches[0]
        reverse: dict[str, list[dict[str, Any]]] = defaultdict(list)
        forward: dict[str, list[dict[str, Any]]] = defaultdict(list)
        for rel in self.relationships:
            forward[rel["source_asset_id"]].append(rel)
            reverse[rel["target_asset_id"]].append(rel)

        impacted, paths = self._walk(reverse, target["id"], max_depth)
        dependencies, dependency_paths = self._walk(forward, target["id"], max_depth)
        impacted_assets = [self.by_id[item] for item in impacted if item in self.by_id]
        dependency_assets = [self.by_id[item] for item in dependencies if item in self.by_id]
        criticality = self._criticality(impacted_assets, dependency_assets)
        breakages = self._breakages(scenario, target, reverse, forward)
        mitigation = self._mitigations(scenario, breakages, criticality)
        readiness = self._readiness(target, impacted_assets, dependency_assets)
        result: dict[str, Any] = {
            "scenario": scenario.upper(),
            "target": target,
            "blast_radius": len(impacted_assets),
            "dependency_count": len(dependency_assets),
            "risk_score": criticality,
            "readiness_score": readiness,
            "affected_assets": sorted(
                impacted_assets, key=lambda item: (item["asset_type"], item["technical_name"])
            ),
            "required_dependencies": sorted(
                dependency_assets, key=lambda item: (item["asset_type"], item["technical_name"])
            ),
            "impact_paths": paths,
            "dependency_paths": dependency_paths,
            "predicted_breakages": breakages,
            "mitigations": mitigation,
            "recommendation": self._recommendation(scenario, criticality, readiness),
            "confidence": round(min(0.98, 0.55 + min(len(self.relationships), 100) / 500), 2),
        }
        if self.run_id:
            self.repository.insert_insight(
                str(self.run_id),
                "MODERNIZATION_SCENARIO",
                f"{target['technical_name']}:{scenario.upper()}",
                result,
                float(result["confidence"]),
            )
        return result

    def compare(self, target_name: str, scenarios: list[str] | None = None) -> dict[str, Any]:
        selected = scenarios or ["modify", "retire", "extract-service", "replatform"]
        results = [self.simulate(target_name, scenario) for scenario in selected]
        return {
            "target": target_name,
            "scenarios": results,
            "recommended": max(
                results, key=lambda item: item["readiness_score"] - item["risk_score"]
            ),
        }

    @staticmethod
    def _walk(
        adjacency: dict[str, list[dict[str, Any]]], start: str, max_depth: int
    ) -> tuple[set[str], list[list[str]]]:
        visited = {start}
        queue: deque[tuple[str, int, list[str]]] = deque([(start, 0, [start])])
        paths: list[list[str]] = []
        while queue:
            node, depth, path = queue.popleft()
            if depth >= max_depth:
                continue
            for rel in adjacency.get(node, []):
                next_id = (
                    rel["source_asset_id"]
                    if rel["target_asset_id"] == node
                    else rel["target_asset_id"]
                )
                next_path = path + [next_id]
                paths.append(next_path)
                if next_id not in visited:
                    visited.add(next_id)
                    queue.append((next_id, depth + 1, next_path))
        visited.discard(start)
        return visited, paths[:200]

    @staticmethod
    def _criticality(impacted: list[dict[str, Any]], dependencies: list[dict[str, Any]]) -> int:
        weights = {
            "JOB": 8,
            "PROGRAM": 6,
            "TABLE": 8,
            "DATASET": 5,
            "TRANSACTION": 10,
            "MQ_QUEUE": 7,
        }
        score = sum(weights.get(item["asset_type"], 3) for item in impacted)
        score += sum(weights.get(item["asset_type"], 2) // 2 for item in dependencies)
        return min(100, score)

    @staticmethod
    def _breakages(
        scenario: str,
        target: dict[str, Any],
        reverse: dict[str, list[dict[str, Any]]],
        forward: dict[str, list[dict[str, Any]]],
    ) -> list[dict[str, Any]]:
        scenario = scenario.lower()
        items: list[dict[str, Any]] = []
        if scenario == "retire":
            for rel in reverse.get(target["id"], []):
                items.append(
                    {
                        "type": "BROKEN_CONSUMER",
                        "relationship": rel["relationship_type"],
                        "consumer": rel["source_name"],
                    }
                )
        elif scenario == "extract-service":
            for rel in reverse.get(target["id"], []) + forward.get(target["id"], []):
                items.append(
                    {
                        "type": "CONTRACT_REQUIRED",
                        "relationship": rel["relationship_type"],
                        "peer": rel["source_name"]
                        if rel["target_asset_id"] == target["id"]
                        else rel["target_name"],
                    }
                )
        elif scenario == "replatform":
            for rel in forward.get(target["id"], []):
                if rel["relationship_type"] in {
                    "READS_TABLE",
                    "WRITES_TABLE",
                    "READS_FILE",
                    "WRITES_FILE",
                    "READS_DATASET",
                    "WRITES_DATASET",
                }:
                    items.append(
                        {
                            "type": "DATA_COMPATIBILITY",
                            "relationship": rel["relationship_type"],
                            "dependency": rel["target_name"],
                        }
                    )
        else:
            for rel in reverse.get(target["id"], []):
                items.append(
                    {
                        "type": "REGRESSION_RISK",
                        "relationship": rel["relationship_type"],
                        "consumer": rel["source_name"],
                    }
                )
        return items

    @staticmethod
    def _mitigations(scenario: str, breakages: list[dict[str, Any]], risk: int) -> list[str]:
        result = [
            "Create characterization and regression tests",
            "Validate all graph paths with source evidence",
        ]
        if scenario.lower() == "retire":
            result.extend(["Confirm zero runtime usage", "Provide rollback and restore path"])
        if scenario.lower() == "extract-service":
            result.extend(
                [
                    "Define versioned contracts",
                    "Use strangler/coexistence routing",
                    "Preserve transaction and batch semantics",
                ]
            )
        if scenario.lower() == "replatform":
            result.extend(
                [
                    "Run data reconciliation",
                    "Validate encoding, precision, ordering, and restart behavior",
                ]
            )
        if risk >= 70:
            result.append("Require architecture and operations approval")
        if breakages:
            result.append(f"Resolve {len(breakages)} predicted compatibility points")
        return result

    @staticmethod
    def _readiness(
        target: dict[str, Any], impacted: list[dict[str, Any]], dependencies: list[dict[str, Any]]
    ) -> int:
        confidence = float(target.get("confidence", 0.0))
        coupling_penalty = min(50, len(impacted) * 3 + len(dependencies) * 2)
        return max(0, min(100, int(confidence * 100) - coupling_penalty))

    @staticmethod
    def _recommendation(scenario: str, risk: int, readiness: int) -> str:
        if risk >= 75:
            return (
                f"Do not execute {scenario} directly; use staged coexistence with human approval."
            )
        if readiness < 40:
            return f"Improve metadata, test coverage, and dependency isolation before {scenario}."
        return f"Proceed with a controlled {scenario} pilot and automated equivalence gates."
