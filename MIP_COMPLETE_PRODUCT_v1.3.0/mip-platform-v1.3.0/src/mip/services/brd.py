from __future__ import annotations

from collections import defaultdict
from pathlib import Path
from typing import Any

from mip.persistence import SQLiteRepository
from mip.services.business_rules import BusinessRuleCatalogService
from mip.services.capability import CapabilityDiscoveryService
from mip.services.scenarios import TestScenarioGenerator


class BRDGenerator:
    def __init__(self, repository: SQLiteRepository, run_id: str | None = None) -> None:
        self.repository = repository
        self.run_id = run_id or repository.latest_run_id()
        self.capabilities = CapabilityDiscoveryService(repository, self.run_id)

    def from_root(self, root_name: str, output: Path | None = None) -> dict[str, Any]:
        chain = self.capabilities.root_driver_chain(root_name)
        title = f"Business Requirements Document — Root Driver {root_name.upper()}"
        return self._generate(title, root_name, chain["assets"], chain["relationships"], output)

    def from_capability(self, capability: str, output: Path | None = None) -> dict[str, Any]:
        discovery = self.capabilities.discover_capability(capability)
        title = f"Business Requirements Document — {capability.title()} Capability"
        return self._generate(
            title, capability, discovery["assets"], discovery["relationships"], output
        )

    def _generate(
        self,
        title: str,
        scope: str,
        assets: list[dict[str, Any]],
        relationships: list[dict[str, Any]],
        output: Path | None,
    ) -> dict[str, Any]:
        by_type: dict[str, list[dict[str, Any]]] = defaultdict(list)
        for asset in assets:
            by_type[asset["asset_type"]].append(asset)
        rules = BusinessRuleCatalogService(self.repository, self.run_id).catalog(scope)
        if rules["rule_count"] == 0:
            rules = BusinessRuleCatalogService(self.repository, self.run_id).catalog()
        scenarios = TestScenarioGenerator(self.repository, self.run_id).generate(scope)
        markdown = self._markdown(title, scope, by_type, relationships, rules, scenarios)
        path: str | None = None
        if output:
            output.parent.mkdir(parents=True, exist_ok=True)
            output.write_text(markdown, encoding="utf-8")
            path = str(output)
        return {
            "title": title,
            "scope": scope,
            "asset_count": len(assets),
            "relationship_count": len(relationships),
            "rule_count": rules["rule_count"],
            "scenario_count": scenarios["scenario_count"],
            "output_path": path,
            "markdown": markdown,
        }

    @staticmethod
    def _markdown(
        title: str,
        scope: str,
        by_type: dict[str, list[dict[str, Any]]],
        relationships: list[dict[str, Any]],
        rules: dict[str, Any],
        scenarios: dict[str, Any],
    ) -> str:
        def names(asset_type: str) -> str:
            items = by_type.get(asset_type, [])
            return (
                "\n".join(f"- `{item['technical_name']}`" for item in items) or "- None discovered"
            )

        rel_lines = (
            "\n".join(
                f"- `{rel['source_name']}` **{rel['relationship_type']}** `{rel['target_name']}`"
                for rel in relationships[:200]
            )
            or "- None discovered"
        )
        rule_lines = (
            "\n".join(
                f"- **{rule['rule_kind']}**: {rule['expression']} — implemented by {', '.join(rule['implemented_by']) or 'unknown'}"
                for rule in rules["rules"][:100]
            )
            or "- No explicit rules discovered; characterize behavior with tests."
        )
        scenario_lines = "\n".join(
            f"- **{item['id']}** {item['title']} — {item['then']}"
            for item in scenarios["scenarios"][:100]
        )
        return f"""# {title}

## 1. Scope

This BRD was generated from evidence-backed MIP metadata for `{scope}`. It should be reviewed by business and technology owners before implementation.

## 2. Business Objective

Reconstruct and modernize the selected functionality while preserving externally observable behavior, data semantics, validations, calculations, and operational controls.

## 3. In-Scope Programs

{names("PROGRAM")}

## 4. In-Scope Jobs and Steps

{names("JOB")}

## 5. Data Structures and Copybooks

{names("COPYBOOK")}

## 6. Files, Datasets, Tables, Queues, and Transactions

### Files
{names("FILE")}

### Datasets
{names("DATASET")}

### Tables
{names("TABLE")}

### MQ Queues
{names("MQ_QUEUE")}

### Transactions
{names("TRANSACTION")}

## 7. Functional Flow

{rel_lines}

## 8. Business Rules

{rule_lines}

## 9. Functional Requirements

1. The modernized functionality shall accept equivalent input structures and preserve field-level semantics.
2. The modernized functionality shall apply all extracted validation, calculation, authorization, and routing rules.
3. The modernized functionality shall preserve success, rejection, error, and default paths.
4. The modernized functionality shall produce equivalent output records, messages, table updates, or service responses.
5. The modernized functionality shall expose behavior through clear Python and Java service functions when generated.

## 10. Non-Functional Requirements

- Evidence traceability from requirement to source artifact.
- Deterministic regression tests.
- Byte-equivalence for fixed-length file outputs where applicable.
- Audit logging for business decisions and exceptions.
- Configuration-driven bank/card/product variants.

## 11. Acceptance Criteria and Test Scenarios

{scenario_lines}

## 12. Open Questions

- Which inferred rules require business approval?
- Which datasets/tables need production-like sample data?
- Which outputs require byte-for-byte equivalence versus business equivalence?
- Which bank/product variations must be configured first?
"""
