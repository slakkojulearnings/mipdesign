from __future__ import annotations

from collections import defaultdict
from typing import Any

from mip.models import AssetType, RelationshipType
from mip.persistence import SQLiteRepository


class BusinessRuleCatalogService:
    def __init__(self, repository: SQLiteRepository, run_id: str | None = None) -> None:
        self.repository = repository
        self.run_id = run_id or repository.latest_run_id()

    def catalog(self, capability: str | None = None) -> dict[str, Any]:
        rules = [
            item
            for item in self.repository.list_assets(
                asset_type=AssetType.BUSINESS_RULE.value, run_id=self.run_id, limit=1_000_000
            )
            if item["status"] == "OBSERVED"
        ]
        relationships = self.repository.relationship_rows(self.run_id)
        program_for_rule: dict[str, list[str]] = defaultdict(list)
        for rel in relationships:
            if rel["relationship_type"] == RelationshipType.IMPLEMENTS_RULE.value:
                program_for_rule[rel["target_asset_id"]].append(rel["source_name"])
        if capability:
            cap = capability.upper()
            rules = [
                rule
                for rule in rules
                if cap in str(rule.get("readable_name", "")).upper()
                or cap in rule["technical_name"].upper()
                or any(cap in program.upper() for program in program_for_rule.get(rule["id"], []))
            ]
        items = []
        for rule in rules:
            attributes = rule.get("attributes", {})
            expression = (
                attributes.get("expression") or rule.get("readable_name") or rule["technical_name"]
            )
            kind = self._classify(expression)
            items.append(
                {
                    "rule_id": rule["technical_name"],
                    "rule_kind": kind,
                    "expression": expression,
                    "implemented_by": sorted(set(program_for_rule.get(rule["id"], []))),
                    "source_path": rule.get("source_path"),
                    "confidence": rule.get("confidence"),
                }
            )
        grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
        for item in items:
            grouped[item["rule_kind"]].append(item)
        return {"rule_count": len(items), "rules": items, "rules_by_kind": dict(grouped)}

    @staticmethod
    def _classify(expression: str) -> str:
        upper = expression.upper()
        if any(
            token in upper for token in ["LIMIT", "AMOUNT", "BALANCE", "RATE", "INTEREST", "FEE"]
        ):
            return "CALCULATION_OR_THRESHOLD"
        if any(token in upper for token in ["VALID", "STATUS", "ERROR", "INVALID"]):
            return "VALIDATION"
        if any(token in upper for token in ["APPROV", "AUTH", "DECLINE", "BLOCK"]):
            return "AUTHORIZATION"
        return "DECISION"
