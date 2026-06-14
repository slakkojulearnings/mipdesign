from __future__ import annotations

import re
from collections import defaultdict, deque
from typing import Any

from mip.models import RelationshipType
from mip.persistence import SQLiteRepository

_TOKEN = re.compile(r"[A-Z0-9]+")

CARD_CAPABILITY_KEYWORDS: dict[str, set[str]] = {
    "card activation": {"CARD", "ACTIV", "STATUS", "PIN", "OPEN"},
    "authorization": {"AUTH", "LIMIT", "VALID", "DECLINE", "APPROVE", "FRAUD"},
    "balance inquiry": {"BAL", "BALANCE", "INQ", "INQUIRY"},
    "interest calculation": {"INT", "INTEREST", "APR", "RATE", "ACCRUAL"},
    "fee calculation": {"FEE", "CHARGE", "WAIVE", "ASSESS"},
    "transaction posting": {"POST", "TXN", "TRAN", "LEDGER", "SETTLE"},
    "statement generation": {"STMT", "STATEMENT", "BILL", "CYCLE"},
    "fraud check": {"FRAUD", "RISK", "SCORE", "RULE"},
    "card blocking": {"BLOCK", "HOT", "LOST", "STOLEN", "STATUS"},
    "rewards": {"REWARD", "POINT", "LOYAL", "CASHBACK"},
}

RELATIONSHIP_WEIGHT = {
    RelationshipType.CALLS.value: 6,
    RelationshipType.DYNAMIC_CALL.value: 4,
    RelationshipType.EXECUTES.value: 7,
    RelationshipType.USES_COPYBOOK.value: 5,
    RelationshipType.READS_TABLE.value: 5,
    RelationshipType.WRITES_TABLE.value: 6,
    RelationshipType.READS_FILE.value: 4,
    RelationshipType.WRITES_FILE.value: 5,
    RelationshipType.READS_DATASET.value: 4,
    RelationshipType.WRITES_DATASET.value: 5,
    RelationshipType.IMPLEMENTS_RULE.value: 8,
    RelationshipType.PUTS_MESSAGE.value: 5,
    RelationshipType.GETS_MESSAGE.value: 5,
}


class CapabilityDiscoveryService:
    """Evidence-backed capability-to-files and root-chain discovery."""

    def __init__(self, repository: SQLiteRepository, run_id: str | None = None) -> None:
        self.repository = repository
        self.run_id = run_id or repository.latest_run_id()
        self.assets = self.repository.list_assets(run_id=self.run_id, limit=1_000_000)
        self.assets_by_id = {asset["id"]: asset for asset in self.assets}
        self.relationships = self.repository.relationship_rows(self.run_id)

    def root_driver_chain(self, root_name: str, max_depth: int = 12) -> dict[str, Any]:
        root_matches = self.repository.find_assets(root_name, run_id=self.run_id)
        if not root_matches:
            raise KeyError(f"root asset not found: {root_name}")
        root = root_matches[0]
        adjacency: dict[str, list[dict[str, Any]]] = defaultdict(list)
        for rel in self.relationships:
            if rel["relationship_type"] in RELATIONSHIP_WEIGHT:
                adjacency[rel["source_asset_id"]].append(rel)

        visited = {root["id"]}
        queue: deque[tuple[str, int]] = deque([(root["id"], 0)])
        chain_relationships: list[dict[str, Any]] = []
        while queue:
            current, depth = queue.popleft()
            if depth >= max_depth:
                continue
            for rel in adjacency.get(current, []):
                target_id = rel["target_asset_id"]
                chain_relationships.append(rel)
                if target_id not in visited:
                    visited.add(target_id)
                    queue.append((target_id, depth + 1))

        return {
            "root": root,
            "assets": sorted(
                [self.assets_by_id[item] for item in visited if item in self.assets_by_id],
                key=lambda item: (item["asset_type"], item["technical_name"]),
            ),
            "relationships": chain_relationships,
            "max_depth": max_depth,
        }

    def discover_capability(self, capability: str, max_depth: int = 4) -> dict[str, Any]:
        query_tokens = self._tokens(capability)
        expanded = set(query_tokens)
        # Common enterprise abbreviations seen in legacy identifiers.
        if "CUSTOMER" in expanded:
            expanded.add("CUST")
        if "ACCOUNT" in expanded:
            expanded.add("ACCT")
        if "TRANSACTION" in expanded:
            expanded.update({"TRAN", "TXN"})
        if "VALIDATION" in expanded or "VALIDATE" in expanded:
            expanded.update({"VALID", "VAL"})
        if "AUTHORIZATION" in expanded or "AUTHORIZE" in expanded:
            expanded.add("AUTH")
        normalized = capability.lower().strip()
        for name, keywords in CARD_CAPABILITY_KEYWORDS.items():
            if normalized in name or name in normalized or query_tokens & keywords:
                expanded |= keywords

        scored: dict[str, float] = {}
        reasons: dict[str, list[str]] = defaultdict(list)
        for asset in self.assets:
            text = " ".join(
                [
                    str(asset.get("technical_name", "")),
                    str(asset.get("readable_name", "")),
                    " ".join(str(v) for v in asset.get("attributes", {}).values()),
                ]
            )
            tokens = self._tokens(text)
            overlap = tokens & expanded
            prefix_overlap = {
                kw
                for kw in expanded
                for token in tokens
                if token.startswith(kw) or kw.startswith(token)
            }
            overlap |= prefix_overlap
            if overlap:
                scored[asset["id"]] = scored.get(asset["id"], 0.0) + len(overlap) * 10
                reasons[asset["id"]].append(f"keyword overlap: {', '.join(sorted(overlap))}")
            if normalized and normalized.replace(" ", "") in text.lower().replace("-", "").replace(
                "_", ""
            ):
                scored[asset["id"]] = scored.get(asset["id"], 0.0) + 25
                reasons[asset["id"]].append("name/attribute phrase match")

        # Expand from matched seeds through nearby relationships.
        if scored:
            neighborhood = self._expand_neighbors(set(scored), max_depth=max_depth)
            for asset_id, distance in neighborhood.items():
                if asset_id not in scored:
                    scored[asset_id] = max(1.0, 12.0 / max(distance, 1))
                    reasons[asset_id].append(f"related to capability seed within {distance} hops")

        ranked: list[dict[str, Any]] = []
        for asset_id, score in sorted(scored.items(), key=lambda item: item[1], reverse=True):
            ranked_asset = self.assets_by_id.get(asset_id)
            if ranked_asset is not None:
                ranked.append(
                    {
                        **ranked_asset,
                        "capability_score": round(min(score, 100.0), 2),
                        "reasons": reasons[asset_id],
                    }
                )

        grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
        for item in ranked:
            grouped[item["asset_type"]].append(item)

        related_ids = {item["id"] for item in ranked}
        related_relationships = [
            rel
            for rel in self.relationships
            if rel["source_asset_id"] in related_ids and rel["target_asset_id"] in related_ids
        ]
        return {
            "capability": capability,
            "expanded_keywords": sorted(expanded),
            "assets": ranked,
            "assets_by_type": dict(grouped),
            "relationships": related_relationships,
        }

    def _expand_neighbors(self, seeds: set[str], max_depth: int) -> dict[str, int]:
        adjacency: dict[str, set[str]] = defaultdict(set)
        for rel in self.relationships:
            adjacency[rel["source_asset_id"]].add(rel["target_asset_id"])
            adjacency[rel["target_asset_id"]].add(rel["source_asset_id"])
        distance: dict[str, int] = {seed: 0 for seed in seeds}
        queue: deque[str] = deque(seeds)
        while queue:
            current = queue.popleft()
            if distance[current] >= max_depth:
                continue
            for neighbor in adjacency.get(current, set()):
                if neighbor not in distance:
                    distance[neighbor] = distance[current] + 1
                    queue.append(neighbor)
        return distance

    @staticmethod
    def _tokens(value: str) -> set[str]:
        return {token.upper() for token in _TOKEN.findall(value.upper())}
