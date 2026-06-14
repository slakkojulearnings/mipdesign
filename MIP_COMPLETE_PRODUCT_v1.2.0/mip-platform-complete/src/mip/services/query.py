from __future__ import annotations

import re
from typing import Any

from mip.graph import KnowledgeGraph
from mip.persistence import SQLiteRepository
from mip.services.business_rules import BusinessRuleCatalogService
from mip.services.capability import CapabilityDiscoveryService


class QueryService:
    def __init__(self, repository: SQLiteRepository, run_id: str | None = None) -> None:
        self.repository = repository
        self.graph = KnowledgeGraph(repository, run_id)

    def ask(self, question: str) -> dict[str, Any]:
        value = question.strip()
        patterns: list[tuple[re.Pattern[str], str]] = [
            (re.compile(r"^(?:who|which programs?)\s+calls?\s+(.+?)\??$", re.I), "callers"),
            (re.compile(r"^(?:what|which programs?)\s+does\s+(.+?)\s+call\??$", re.I), "callees"),
            (re.compile(r"^which\s+jobs?\s+execute(?:s)?\s+(.+?)\??$", re.I), "jobs"),
            (re.compile(r"^(?:what is the )?impact(?: of)?\s+(.+?)\??$", re.I), "impact"),
            (re.compile(r"^(?:show|list)\s+(?:the\s+)?root\s+programs?\??$", re.I), "roots"),
            (
                re.compile(r"^(?:show|trace)\s+(?:root\s+)?chain\s+(?:for\s+)?(.+?)\??$", re.I),
                "root_chain",
            ),
            (
                re.compile(
                    r"^(?:show|find|list)\s+files\s+(?:for\s+)?capability\s+(.+?)\??$", re.I
                ),
                "capability",
            ),
            (
                re.compile(r"^(?:show|list)\s+(?:business\s+)?rules(?:\s+for\s+(.+?))?\??$", re.I),
                "rules",
            ),
            (
                re.compile(r"^(?:show|give|what are)\s+(?:the\s+)?stats(?:istics)?\??$", re.I),
                "stats",
            ),
        ]
        for pattern, operation in patterns:
            match = pattern.match(value)
            if not match:
                continue
            target = match.group(1).strip() if match.groups() else None
            if operation == "callers":
                return {"question": question, "answer": self.graph.callers(target or "")}
            if operation == "callees":
                return {"question": question, "answer": self.graph.callees(target or "")}
            if operation == "jobs":
                return {"question": question, "answer": self.graph.jobs_executing(target or "")}
            if operation == "impact":
                return {"question": question, "answer": self.graph.impact(target or "")}
            if operation == "roots":
                return {"question": question, "answer": self.graph.root_programs()}
            if operation == "stats":
                return {"question": question, "answer": self.repository.stats(self.graph.run_id)}
            if operation == "root_chain":
                return {
                    "question": question,
                    "answer": CapabilityDiscoveryService(
                        self.repository, self.graph.run_id
                    ).root_driver_chain(target or ""),
                }
            if operation == "capability":
                return {
                    "question": question,
                    "answer": CapabilityDiscoveryService(
                        self.repository, self.graph.run_id
                    ).discover_capability(target or ""),
                }
            if operation == "rules":
                return {
                    "question": question,
                    "answer": BusinessRuleCatalogService(
                        self.repository, self.graph.run_id
                    ).catalog(target),
                }
        return {
            "question": question,
            "error": "Unsupported deterministic question",
            "supported_examples": [
                "Who calls PROGRAMX?",
                "What does PROGRAMX call?",
                "Which jobs execute PROGRAMX?",
                "Impact of PROGRAMX",
                "Show root programs",
                "Show statistics",
                "Show chain for PROGRAMX",
                "Find files for capability authorization",
                "Show business rules",
            ],
        }
