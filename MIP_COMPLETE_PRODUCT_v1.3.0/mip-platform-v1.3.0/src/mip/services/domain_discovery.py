from __future__ import annotations

import re
from collections import Counter, defaultdict
from typing import Any

from mip.persistence import SQLiteRepository

_STOP = {
    "PROGRAM",
    "JOB",
    "STEP",
    "FILE",
    "TABLE",
    "DATA",
    "REC",
    "RECORD",
    "WS",
    "INPUT",
    "OUTPUT",
    "READ",
    "WRITE",
    "COPY",
    "PROC",
    "MAIN",
    "TEMP",
    "WORK",
    "AREA",
    "SQL",
}
_SUFFIXES = ("ID", "NO", "NUMBER", "CODE", "STATUS", "DATE", "AMOUNT", "BALANCE", "TYPE", "NAME")


class DomainModelDiscoveryService:
    """Discovers domain entities, attributes, and associations from metadata and graph evidence."""

    def __init__(self, repository: SQLiteRepository, run_id: str | None = None) -> None:
        self.repository = repository
        self.run_id = run_id or repository.latest_run_id()

    def discover(self, minimum_score: int = 2) -> dict[str, Any]:
        assets = self.repository.list_assets(run_id=self.run_id, limit=1_000_000)
        relationships = self.repository.relationship_rows(self.run_id)
        candidates: Counter[str] = Counter()
        attributes: dict[str, set[str]] = defaultdict(set)
        evidence: dict[str, list[dict[str, Any]]] = defaultdict(list)

        for asset in assets:
            name = str(asset["technical_name"])
            tokens = self._tokens(name)
            if asset["asset_type"] in {"TABLE", "FILE", "COPYBOOK", "DATA_FIELD"}:
                entity = self._entity_token(tokens)
                if entity:
                    candidates[entity] += 3 if asset["asset_type"] == "TABLE" else 2
                    evidence[entity].append({"asset_type": asset["asset_type"], "name": name})
                    for token in tokens:
                        if token != entity and (token in _SUFFIXES or len(token) > 3):
                            attributes[entity].add(token)
            for value in asset.get("attributes", {}).values():
                for token in self._tokens(str(value)):
                    if len(token) >= 4 and token not in _STOP:
                        candidates[token] += 1

        associations: Counter[tuple[str, str]] = Counter()
        for rel in relationships:
            source = self._entity_token(self._tokens(rel["source_name"]))
            target = self._entity_token(self._tokens(rel["target_name"]))
            if source and target and source != target:
                left, right = sorted((source, target))
                associations[(left, right)] += 1

        entities = [
            {
                "name": name.title().replace("_", " "),
                "technical_key": name,
                "score": score,
                "attributes": sorted(attributes[name]),
                "evidence": evidence[name][:20],
                "confidence": round(min(0.99, 0.45 + score * 0.08), 2),
            }
            for name, score in candidates.most_common()
            if score >= minimum_score and name not in _STOP
        ]
        known = {item["technical_key"] for item in entities}
        links = [
            {"from": left, "to": right, "evidence_count": count, "relationship": "ASSOCIATED_WITH"}
            for (left, right), count in associations.most_common()
            if left in known and right in known
        ]
        return {"entity_count": len(entities), "entities": entities, "associations": links}

    @staticmethod
    def _tokens(value: str) -> list[str]:
        return [token for token in re.split(r"[^A-Z0-9]+", value.upper()) if token]

    @staticmethod
    def _entity_token(tokens: list[str]) -> str | None:
        meaningful = [token for token in tokens if token not in _STOP and len(token) >= 3]
        if not meaningful:
            return None
        for token in meaningful:
            if token not in _SUFFIXES:
                return token
        return meaningful[0]
