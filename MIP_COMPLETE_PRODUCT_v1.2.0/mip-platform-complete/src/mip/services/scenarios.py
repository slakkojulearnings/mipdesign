from __future__ import annotations

from typing import Any

from mip.persistence import SQLiteRepository
from mip.services.business_rules import BusinessRuleCatalogService


class FunctionalTestScenarioGenerator:
    def __init__(self, repository: SQLiteRepository, run_id: str | None = None) -> None:
        self.repository = repository
        self.run_id = run_id or repository.latest_run_id()

    def generate(self, capability: str | None = None) -> dict[str, Any]:
        catalog = BusinessRuleCatalogService(self.repository, self.run_id).catalog(capability)
        scenarios = []
        for index, rule in enumerate(catalog["rules"], 1):
            scenarios.extend(
                [
                    {
                        "id": f"TC-{index:04d}-TRUE",
                        "title": f"Rule satisfied: {rule['expression']}",
                        "type": "positive",
                        "given": "Input data satisfies the extracted condition.",
                        "when": f"Programs {', '.join(rule['implemented_by']) or 'under analysis'} execute.",
                        "then": "Processing follows the true/accepted branch with expected outputs.",
                        "source_rule": rule["rule_id"],
                    },
                    {
                        "id": f"TC-{index:04d}-FALSE",
                        "title": f"Rule not satisfied: {rule['expression']}",
                        "type": "negative",
                        "given": "Input data violates or bypasses the extracted condition.",
                        "when": f"Programs {', '.join(rule['implemented_by']) or 'under analysis'} execute.",
                        "then": "Processing follows the false/rejection/default branch.",
                        "source_rule": rule["rule_id"],
                    },
                ]
            )
        if not scenarios:
            scenarios.append(
                {
                    "id": "TC-0000-SMOKE",
                    "title": "Capability smoke test",
                    "type": "smoke",
                    "given": "Representative input records and reference data are available.",
                    "when": "The capability workflow executes end to end.",
                    "then": "Outputs, status, and side effects match the approved baseline.",
                    "source_rule": None,
                }
            )
        return {"scenario_count": len(scenarios), "scenarios": scenarios}


TestScenarioGenerator = FunctionalTestScenarioGenerator
TestScenarioGenerator.__test__ = False  # type: ignore[attr-defined]
