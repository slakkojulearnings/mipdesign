from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from mip.persistence import SQLiteRepository
from mip.services.business_rule_engine import BusinessRuleExtractionEngine
from mip.services.domain_discovery import DomainModelDiscoveryService
from mip.services.event_discovery import EventDiscoveryService
from mip.services.service_boundary import ServiceBoundaryDiscoveryService


class IntelligenceSuite:
    def __init__(self, repository: SQLiteRepository, run_id: str | None = None) -> None:
        self.repository = repository
        self.run_id = run_id or repository.latest_run_id()

    def generate(self, output_dir: Path, capability: str | None = None) -> dict[str, Any]:
        output_dir.mkdir(parents=True, exist_ok=True)
        outputs: dict[str, dict[str, Any]] = {
            "business_rules": BusinessRuleExtractionEngine(self.repository, self.run_id).extract(
                capability
            ),
            "domain_model": DomainModelDiscoveryService(self.repository, self.run_id).discover(),
            "events": EventDiscoveryService(self.repository, self.run_id).discover(capability),
            "service_boundaries": ServiceBoundaryDiscoveryService(
                self.repository, self.run_id
            ).discover(),
        }
        paths: dict[str, str] = {}
        summary: dict[str, int] = {}
        count_fields = {
            "business_rules": "rule_count",
            "domain_model": "entity_count",
            "events": "event_count",
            "service_boundaries": "service_count",
        }
        item_fields = {
            "business_rules": ("rules", "rule_id"),
            "domain_model": ("entities", "technical_key"),
            "events": ("events", "event_name"),
            "service_boundaries": ("services", "service_name"),
        }
        insight_types = {
            "business_rules": "BUSINESS_RULE",
            "domain_model": "DOMAIN_ENTITY",
            "events": "EVENT_CANDIDATE",
            "service_boundaries": "SERVICE_CANDIDATE",
        }
        for name, payload in outputs.items():
            path = output_dir / f"{name}.json"
            path.write_text(json.dumps(payload, indent=2, default=str), encoding="utf-8")
            paths[name] = str(path)
            summary[name] = int(payload.get(count_fields[name], 0))
            collection_field, subject_field = item_fields[name]
            for item in payload.get(collection_field, []):
                if not isinstance(item, dict):
                    continue
                subject = str(item.get(subject_field, "UNKNOWN"))
                confidence = float(item.get("confidence", 0.5))
                self.repository.insert_insight(
                    str(self.run_id), insight_types[name], subject, item, confidence
                )
        return {"run_id": self.run_id, "outputs": paths, "summary": summary}
