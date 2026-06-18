from __future__ import annotations

import re
from collections import defaultdict
from pathlib import Path
from typing import Any

from mip.persistence import SQLiteRepository

_IF = re.compile(r"\bIF\s+(.+?)(?:\s+THEN\b|$)", re.I)
_EVALUATE = re.compile(r"\bEVALUATE\s+(.+)$", re.I)
_WHEN = re.compile(r"\bWHEN\s+(.+)$", re.I)
_COMPUTE = re.compile(r"\bCOMPUTE\s+([A-Z0-9-]+)\s*=\s*(.+)$", re.I)
_MOVE = re.compile(r"\bMOVE\s+(.+?)\s+TO\s+([A-Z0-9-]+)", re.I)
_STATE = re.compile(r"\b(STATUS|STATE|CODE|FLAG)\b", re.I)
_THRESHOLD = re.compile(
    r"(?:>=|<=|>|<|=)\s*[-+]?\d+(?:\.\d+)?|\b(LIMIT|RATE|AMOUNT|BALANCE|FEE|INTEREST)\b", re.I
)


class BusinessRuleExtractionEngine:
    """Extracts structured, evidence-linked rules from persisted source metadata."""

    def __init__(self, repository: SQLiteRepository, run_id: str | None = None) -> None:
        self.repository = repository
        self.run_id = run_id or repository.latest_run_id()

    def extract(self, capability: str | None = None) -> dict[str, Any]:
        run = self.repository.get_run(self.run_id)
        if not run:
            return {"rule_count": 0, "rules": [], "coverage": {}}
        root = Path(str(run["source_root"]))
        programs = [
            asset
            for asset in self.repository.list_assets("PROGRAM", self.run_id, limit=1_000_000)
            if asset.get("source_path")
        ]
        rules: list[dict[str, Any]] = []
        program_counts: dict[str, int] = defaultdict(int)
        for program in programs:
            path = root / str(program["source_path"])
            if not path.exists():
                continue
            text = path.read_text(encoding="utf-8", errors="replace")
            for number, raw in enumerate(text.splitlines(), 1):
                line = raw[7:72] if len(raw) >= 7 and raw[:6].strip().isdigit() else raw
                statement = " ".join(line.strip().split())
                if not statement or statement.startswith("*>"):
                    continue
                extracted = self._extract_line(statement)
                for item in extracted:
                    item.update(
                        {
                            "program": program["technical_name"],
                            "source_path": program["source_path"],
                            "line": number,
                            "evidence": statement,
                        }
                    )
                    item["rule_id"] = f"{program['technical_name']}:L{number}:{len(rules) + 1}"
                    if capability and not self._matches_capability(item, capability):
                        continue
                    rules.append(item)
                    program_counts[program["technical_name"]] += 1
        return {
            "rule_count": len(rules),
            "rules": rules,
            "coverage": {
                "programs_examined": len(programs),
                "programs_with_rules": len(program_counts),
                "rules_by_program": dict(sorted(program_counts.items())),
            },
        }

    def decision_tables(self, capability: str | None = None) -> dict[str, Any]:
        extracted = self.extract(capability)
        tables: dict[str, dict[str, Any]] = {}
        current: dict[str, str] = {}
        for rule in extracted["rules"]:
            program = str(rule["program"])
            if rule["kind"] == "DECISION_TABLE":
                current[program] = str(rule["expression"])
                tables.setdefault(
                    f"{program}:{rule['line']}",
                    {"program": program, "subject": rule["expression"], "branches": []},
                )
            elif rule["kind"] == "DECISION_BRANCH" and program in current:
                key = next(
                    (
                        item_key
                        for item_key, value in reversed(list(tables.items()))
                        if value["program"] == program
                    ),
                    None,
                )
                if key:
                    tables[key]["branches"].append(rule)
        return {"decision_table_count": len(tables), "decision_tables": list(tables.values())}

    @staticmethod
    def _extract_line(statement: str) -> list[dict[str, Any]]:
        result: list[dict[str, Any]] = []
        if match := _IF.search(statement):
            expression = match.group(1).strip()
            result.append(
                {
                    "kind": BusinessRuleExtractionEngine._classify_condition(expression),
                    "expression": expression,
                    "confidence": 0.97,
                }
            )
        if match := _EVALUATE.search(statement):
            result.append(
                {
                    "kind": "DECISION_TABLE",
                    "expression": match.group(1).strip(),
                    "confidence": 0.95,
                }
            )
        if match := _WHEN.search(statement):
            result.append(
                {
                    "kind": "DECISION_BRANCH",
                    "expression": match.group(1).strip(),
                    "confidence": 0.95,
                }
            )
        if match := _COMPUTE.search(statement):
            result.append(
                {
                    "kind": "CALCULATION",
                    "target": match.group(1).upper(),
                    "expression": match.group(2).strip(),
                    "confidence": 0.99,
                }
            )
        if match := _MOVE.search(statement):
            target = match.group(2).upper()
            if _STATE.search(target):
                result.append(
                    {
                        "kind": "STATE_TRANSITION",
                        "target": target,
                        "expression": match.group(1).strip(),
                        "confidence": 0.92,
                    }
                )
        return result

    @staticmethod
    def _classify_condition(expression: str) -> str:
        upper = expression.upper()
        if any(token in upper for token in ("ELIGIB", "QUALIF", "AGE", "INCOME")):
            return "ELIGIBILITY"
        if any(token in upper for token in ("AUTH", "APPROV", "DECLIN", "BLOCK")):
            return "AUTHORIZATION"
        if _THRESHOLD.search(upper):
            return "THRESHOLD_OR_VALIDATION"
        return "VALIDATION"

    @staticmethod
    def _matches_capability(rule: dict[str, Any], capability: str) -> bool:
        query = {token for token in re.findall(r"[A-Z0-9]+", capability.upper()) if len(token) > 2}
        text = " ".join(str(value) for value in rule.values()).upper()
        return not query or any(token in text for token in query)
