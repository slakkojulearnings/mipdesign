from __future__ import annotations

import json
import os
import urllib.error
import urllib.request
from dataclasses import dataclass
from typing import Any

from .graph_service import GraphService
from .models import now_iso, stable_id
from .repositories import SQLiteGraphRepository


@dataclass(frozen=True)
class LlmConfig:
    provider: str = "offline"
    endpoint: str = ""
    api_key: str = ""
    model: str = ""
    timeout_seconds: int = 30

    @staticmethod
    def from_env() -> "LlmConfig":
        return LlmConfig(
            provider=os.getenv("MIP_LLM_PROVIDER", "offline").strip().lower(),
            endpoint=os.getenv("MIP_LLM_ENDPOINT", "").strip(),
            api_key=os.getenv("MIP_LLM_API_KEY", "").strip(),
            model=os.getenv("MIP_LLM_MODEL", "").strip(),
            timeout_seconds=int(os.getenv("MIP_LLM_TIMEOUT", "30")),
        )


class EvidenceGroundedInsightService:
    """Generate developer-facing insights from persisted evidence.

    The deterministic summary always works. If an OpenAI-compatible endpoint is configured,
    the LLM receives only compact cited facts and must return JSON with citations. Responses
    with no citations are downgraded to needs_review.
    """

    def __init__(self, repository: SQLiteGraphRepository, config: LlmConfig | None = None) -> None:
        self.repository = repository
        self.graph = GraphService(repository)
        self.config = config or LlmConfig.from_env()

    def explain_node(self, run_id: str, asset_id: str) -> dict[str, Any]:
        profile = self.graph.node_profile(run_id, asset_id)
        facts = self._facts_from_profile(profile)
        deterministic = self._deterministic_node_summary(profile, facts)
        if self.config.provider == "offline" or not self.config.endpoint:
            return deterministic
        return self._llm_or_fallback("node_explanation", facts, deterministic)

    def explain_root_functionality(self, run_id: str, root_asset_id: str) -> dict[str, Any]:
        slice_payload = self.graph.graph_slice(
            request=__import__("mip_intel.models", fromlist=["GraphSliceRequest"]).GraphSliceRequest(
                run_id=run_id,
                root_asset_id=root_asset_id,
                depth=3,
                limit=300,
            )
        )
        facts = {
            "root_asset_id": root_asset_id,
            "nodes": slice_payload["nodes"][:100],
            "edges": slice_payload["edges"][:200],
            "stats": slice_payload["stats"],
        }
        title = "Functionality summary"
        body = self._root_summary_body(facts)
        fallback = self._insight("ROOT_FUNCTIONALITY", title, body, 0.55, "inferred", facts)
        if self.config.provider == "offline" or not self.config.endpoint:
            return fallback
        return self._llm_or_fallback("root_functionality", facts, fallback)

    def persist(self, run_id: str, subject_asset_id: str | None, insight: dict[str, Any]) -> str:
        insight_id = stable_id(
            run_id,
            "insight",
            insight.get("insight_type"),
            subject_asset_id,
            insight.get("title"),
            insight.get("body"),
        )
        with self.repository.connect() as conn:
            conn.execute(
                """
                INSERT OR REPLACE INTO insight(
                    insight_id, run_id, insight_type, subject_asset_id, title, body,
                    confidence, validation_status, citations_json, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    insight_id,
                    run_id,
                    insight.get("insight_type", "EXPLANATION"),
                    subject_asset_id,
                    insight.get("title", "Insight"),
                    insight.get("body", ""),
                    insight.get("confidence", 0.5),
                    insight.get("validation_status", "needs_review"),
                    json.dumps(insight.get("citations", []), sort_keys=True),
                    now_iso(),
                ),
            )
        return insight_id

    def list_insights(self, run_id: str, *, limit: int = 200) -> list[dict[str, Any]]:
        with self.repository.connect() as conn:
            rows = conn.execute(
                """
                SELECT * FROM insight
                WHERE run_id = ?
                ORDER BY created_at DESC
                LIMIT ?
                """,
                (run_id, min(limit, 1000)),
            ).fetchall()
            out = []
            for row in rows:
                item = dict(row)
                item["citations"] = json.loads(item.pop("citations_json"))
                out.append(item)
            return out

    def _llm_or_fallback(
        self, task: str, facts: dict[str, Any], fallback: dict[str, Any]
    ) -> dict[str, Any]:
        prompt = {
            "task": task,
            "instructions": (
                "Return JSON with title, body, confidence, validation_status, citations. "
                "Use only supplied facts. Mark inference as inferred or needs_review."
            ),
            "facts": facts,
        }
        try:
            response = self._call_openai_compatible(prompt)
            citations = response.get("citations") or []
            if not citations:
                response["validation_status"] = "needs_review"
                response["confidence"] = min(float(response.get("confidence", 0.4)), 0.4)
            return {
                "insight_type": response.get("insight_type", fallback["insight_type"]),
                "title": response.get("title", fallback["title"]),
                "body": response.get("body", fallback["body"]),
                "confidence": float(response.get("confidence", fallback["confidence"])),
                "validation_status": response.get(
                    "validation_status", fallback["validation_status"]
                ),
                "citations": citations,
                "llm_provider": self.config.provider,
            }
        except (OSError, ValueError, KeyError, urllib.error.URLError, TimeoutError):
            return fallback

    def _call_openai_compatible(self, prompt: dict[str, Any]) -> dict[str, Any]:
        payload = {
            "model": self.config.model or "default",
            "messages": [
                {"role": "system", "content": "You are an evidence-grounded code analyst."},
                {"role": "user", "content": json.dumps(prompt, sort_keys=True)},
            ],
            "temperature": 0,
            "response_format": {"type": "json_object"},
        }
        request = urllib.request.Request(
            self.config.endpoint,
            data=json.dumps(payload).encode("utf-8"),
            headers={
                "Content-Type": "application/json",
                **({"Authorization": f"Bearer {self.config.api_key}"} if self.config.api_key else {}),
            },
            method="POST",
        )
        with urllib.request.urlopen(request, timeout=self.config.timeout_seconds) as response:
            raw = json.loads(response.read().decode("utf-8"))
        content = raw["choices"][0]["message"]["content"]
        return json.loads(content)

    @staticmethod
    def _facts_from_profile(profile: dict[str, Any]) -> dict[str, Any]:
        return {
            "asset": profile["asset"],
            "metrics": profile["metrics"],
            "functionality": profile["functionality"],
            "incoming": profile["incoming"][:50],
            "outgoing": profile["outgoing"][:50],
            "evidence": [
                {
                    "source_path": item["source_path"],
                    "line_start": item["line_start"],
                    "evidence_text": item["evidence_text"],
                    "confidence": item["confidence"],
                    "validation_status": item["validation_status"],
                }
                for item in profile["evidence"][:20]
            ],
        }

    def _deterministic_node_summary(
        self, profile: dict[str, Any], facts: dict[str, Any]
    ) -> dict[str, Any]:
        asset = profile["asset"]
        metrics = profile["metrics"]
        body = (
            f"{asset['technical_name']} is a {asset['asset_type']} with "
            f"{metrics['incoming_count']} incoming and {metrics['outgoing_count']} outgoing "
            f"relationships. Functionality label: {profile['functionality']}. "
            f"{metrics['unresolved_relationships']} relationship(s) need review."
        )
        return self._insight(
            "NODE_EXPLANATION",
            f"{asset['technical_name']} summary",
            body,
            min(float(asset["confidence"]), 0.75),
            "inferred",
            facts,
        )

    @staticmethod
    def _root_summary_body(facts: dict[str, Any]) -> str:
        program_count = sum(1 for node in facts["nodes"] if node["type"] == "PROGRAM")
        data_count = sum(
            1
            for node in facts["nodes"]
            if node["type"] in {"TABLE", "FILE", "DATASET", "COPYBOOK", "MQ_QUEUE", "MAP"}
        )
        unresolved = facts["stats"].get("needs_review_edges", 0)
        return (
            f"This root slice contains {program_count} program node(s), {data_count} "
            f"data/support node(s), and {unresolved} relationship(s) requiring review."
        )

    @staticmethod
    def _insight(
        insight_type: str,
        title: str,
        body: str,
        confidence: float,
        validation_status: str,
        facts: dict[str, Any],
    ) -> dict[str, Any]:
        citations = []
        for item in facts.get("evidence", []):
            citations.append(
                {
                    "source_path": item.get("source_path"),
                    "line_start": item.get("line_start"),
                    "confidence": item.get("confidence"),
                    "validation_status": item.get("validation_status"),
                }
            )
        for edge in facts.get("edges", [])[:10]:
            citations.append(
                {
                    "relationship": edge.get("id"),
                    "source": edge.get("source_name"),
                    "target": edge.get("target_name"),
                    "confidence": edge.get("confidence"),
                    "validation_status": edge.get("validation_status"),
                }
            )
        return {
            "insight_type": insight_type,
            "title": title,
            "body": body,
            "confidence": confidence,
            "validation_status": validation_status,
            "citations": citations,
            "llm_provider": "offline",
        }
