from __future__ import annotations

import re
from collections import defaultdict
from typing import Any

from mip.persistence import SQLiteRepository
from mip.services.business_rule_engine import BusinessRuleExtractionEngine


class EventDiscoveryService:
    """Discovers candidate domain events from state changes, writes, messages, and batch outputs."""

    def __init__(self, repository: SQLiteRepository, run_id: str | None = None) -> None:
        self.repository = repository
        self.run_id = run_id or repository.latest_run_id()

    def discover(self, capability: str | None = None) -> dict[str, Any]:
        relationships = self.repository.relationship_rows(self.run_id)
        rules = BusinessRuleExtractionEngine(self.repository, self.run_id).extract(capability)[
            "rules"
        ]
        candidates: dict[tuple[str, str], dict[str, Any]] = {}

        for rel in relationships:
            rel_type = rel["relationship_type"]
            if rel_type not in {
                "WRITES_TABLE",
                "WRITES_FILE",
                "WRITES_DATASET",
                "PUTS_MESSAGE",
                "STARTS_TRANSACTION",
            }:
                continue
            subject = self._subject(rel["target_name"])
            verb = {
                "WRITES_TABLE": "Updated",
                "WRITES_FILE": "Produced",
                "WRITES_DATASET": "Produced",
                "PUTS_MESSAGE": "Published",
                "STARTS_TRANSACTION": "Started",
            }[rel_type]
            name = f"{subject}{verb}"
            candidates[(name, rel["source_name"])] = {
                "event_name": name,
                "producer": rel["source_name"],
                "trigger": rel_type,
                "payload_source": rel["target_name"],
                "confidence": 0.8 if rel_type == "PUTS_MESSAGE" else 0.68,
                "evidence": self._relationship_evidence(rel),
            }

        for rule in rules:
            if rule["kind"] != "STATE_TRANSITION":
                continue
            target = str(rule.get("target", "STATE"))
            value = self._subject(str(rule.get("expression", "Changed")))
            subject = self._subject(target.replace("STATUS", "").replace("STATE", "")) or "Entity"
            name = f"{subject}{value.title()}"
            candidates[(name, str(rule["program"]))] = {
                "event_name": name,
                "producer": rule["program"],
                "trigger": "STATE_TRANSITION",
                "payload_source": target,
                "confidence": 0.86,
                "evidence": {
                    "source_path": rule["source_path"],
                    "line": rule["line"],
                    "text": rule["evidence"],
                },
            }

        consumers: dict[str, set[str]] = defaultdict(set)
        for rel in relationships:
            if rel["relationship_type"] in {
                "READS_TABLE",
                "READS_FILE",
                "READS_DATASET",
                "GETS_MESSAGE",
            }:
                consumers[rel["target_name"]].add(rel["source_name"])
        for event in candidates.values():
            event["candidate_consumers"] = sorted(
                consumers.get(str(event["payload_source"]), set())
            )

        events = sorted(
            candidates.values(), key=lambda item: (item["event_name"], item["producer"])
        )
        return {"event_count": len(events), "events": events}

    @staticmethod
    def _subject(value: str) -> str:
        words = [word for word in re.split(r"[^A-Z0-9]+", value.upper()) if word]
        return "".join(
            word.title() for word in words if word not in {"FILE", "TABLE", "DATASET", "QUEUE"}
        )

    @staticmethod
    def _relationship_evidence(rel: dict[str, Any]) -> dict[str, Any]:
        return {
            "source_path": rel.get("evidence_source_path"),
            "line_start": rel.get("evidence_line_start"),
            "line_end": rel.get("evidence_line_end"),
        }
