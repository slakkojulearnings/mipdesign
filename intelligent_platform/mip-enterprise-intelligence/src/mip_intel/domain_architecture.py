from __future__ import annotations

import re
from typing import Any

from .models import stable_id
from .repositories import SQLiteGraphRepository


DATA_ASSET_TYPES = {
    "TABLE",
    "FILE",
    "DATASET",
    "COPYBOOK",
    "MQ_QUEUE",
    "MAP",
    "IMS_DATABASE",
    "IMS_SEGMENT",
    "DB2_DATABASE",
    "DB2_TABLESPACE",
}
WRITE_RELS = {"WRITES_TABLE", "WRITES_FILE", "WRITES_DATASET", "WRITES_QUEUE"}
READ_RELS = {"READS_TABLE", "READS_FILE", "READS_DATASET", "READS_QUEUE", "USES_DATASET"}
ENTRY_RELS = {"EXECUTES", "STARTS_PROGRAM", "STARTS_TRANSACTION", "TRIGGERS"}
CONTROL_RELS = {"CALLS", "DYNAMIC_CALL", "EXECUTES", "STARTS_PROGRAM", "STARTS_TRANSACTION", "TRIGGERS"}


class DomainArchitectureService:
    """Build DDD and modernization read models from persisted graph evidence."""

    def __init__(self, repository: SQLiteGraphRepository) -> None:
        self.repository = repository

    def bounded_contexts(self, run_id: str, *, limit: int = 50) -> dict[str, Any]:
        contexts = [self._context_from_cluster(run_id, cluster) for cluster in self.repository.list_clusters(run_id, limit=limit)]
        return {
            "run_id": run_id,
            "architecture_style": "layered_ddd_read_model",
            "membership_rule": "Clusters and ownership are graph-derived; LLM naming is advisory only.",
            "contexts": contexts,
        }

    def service_candidates(self, run_id: str, *, limit: int = 50) -> dict[str, Any]:
        contexts = self.bounded_contexts(run_id, limit=limit)["contexts"]
        return {
            "run_id": run_id,
            "service_candidates": [self._service_from_context(context) for context in contexts],
        }

    def modernization_roadmap(self, run_id: str, *, limit: int = 50) -> dict[str, Any]:
        candidates = self.service_candidates(run_id, limit=limit)["service_candidates"]
        ordered = sorted(candidates, key=lambda item: (-item["risk_score"], item["confidence"], item["name"]))
        packages = []
        for sequence, service in enumerate(ordered, 1):
            packages.append(
                {
                    "sequence": sequence,
                    "bounded_context": service["bounded_context"],
                    "service_candidate": service["name"],
                    "risk_score": service["risk_score"],
                    "confidence": service["confidence"],
                    "validation_status": service["validation_status"],
                    "steps": [
                        {
                            "kind": "stabilize_facts",
                            "title": "Validate parser, graph, and unresolved dependency facts",
                            "exit_criteria": "Evidence validation passes and needs_review edges are triaged.",
                        },
                        {
                            "kind": "strangler_facade",
                            "title": f"Expose facade around {service['java_service_candidate']}",
                            "exit_criteria": "Facade contract tests pass against mainframe golden outputs.",
                        },
                        {
                            "kind": "data_contracts",
                            "title": "Protect owned tables/files behind explicit contracts",
                            "exit_criteria": "Read/write ownership and test data fixtures are reconciled.",
                        },
                        {
                            "kind": "incremental_cutover",
                            "title": "Migrate one operation at a time with dual-run checks",
                            "exit_criteria": "Dual-run deltas stay within agreed tolerance for consecutive cycles.",
                        },
                    ],
                    "feedback_loop": {
                        "hypothesis": f"{service['name']} can be extracted behind stable APIs without changing upstream jobs.",
                        "quality_gates": service["feedback_loop"]["quality_gates"],
                        "telemetry": [
                            "contract_test_pass_rate",
                            "dual_run_delta_count",
                            "unresolved_dependency_trend",
                            "production_error_budget",
                        ],
                        "rollback_signal": "Contract drift, unresolved writes, or dual-run mismatch above tolerance.",
                    },
                    "evidence": service["evidence"],
                }
            )
        return {
            "run_id": run_id,
            "roadmap_method": "risk_confidence_ordered_strangler_sequence",
            "work_packages": packages,
        }

    def _context_from_cluster(self, run_id: str, cluster: dict[str, Any]) -> dict[str, Any]:
        attrs = cluster.get("attributes", {})
        sample_assets = attrs.get("sample_assets", [])
        asset_ids = [asset["asset_id"] for asset in sample_assets if asset.get("asset_id")]
        relationships = self._relationships_for_assets(run_id, asset_ids)
        member_asset_ids = set(asset_ids)
        naming = attrs.get("naming", {})
        capability = self._clean_cluster_name(cluster.get("name", "Needs Review"))
        confidence = round(float(attrs.get("confidence") or cluster.get("confidence") or 0.55), 3)
        truncated_membership = int(cluster.get("asset_count") or 0) > len(sample_assets)
        if truncated_membership:
            confidence = min(confidence, 0.82)
        validation_status = str(attrs.get("validation_status") or cluster.get("validation_status") or "inferred")
        if truncated_membership and validation_status == "confirmed":
            validation_status = "inferred"

        aggregate_candidates = self._aggregate_candidates(relationships, member_asset_ids)
        api_candidates = self._api_candidates(cluster, attrs, relationships, member_asset_ids)
        event_candidates = self._event_candidates(relationships, member_asset_ids)
        dependencies = self._external_dependencies(relationships, member_asset_ids)
        citations = self._citations(cluster, sample_assets, relationships)

        return {
            "context_id": cluster.get("cluster_id") or stable_id(run_id, "context", capability),
            "name": capability,
            "domain": attrs.get("domain") or naming.get("domain") or "Unknown",
            "capability": naming.get("name") or capability,
            "root_asset_id": cluster.get("root_asset_id"),
            "java_service_candidate": attrs.get("java_service_candidate") or naming.get("java_service") or self._service_name(capability),
            "package_candidate": self._java_package(attrs.get("domain") or naming.get("domain") or "legacy", capability),
            "membership_method": "graph_cluster_read_model",
            "membership_scope": "sampled" if truncated_membership else "complete",
            "llm_membership_used": bool(attrs.get("signals", {}).get("llm_membership_used", False)),
            "asset_count": cluster.get("asset_count", len(sample_assets)),
            "program_count": cluster.get("program_count", 0),
            "data_count": cluster.get("data_count", 0),
            "risk_score": round(float(cluster.get("risk_score") or attrs.get("risk_score") or 0.0), 3),
            "confidence": confidence,
            "validation_status": validation_status,
            "aggregate_candidates": aggregate_candidates,
            "api_candidates": api_candidates,
            "event_candidates": event_candidates,
            "external_dependencies": dependencies,
            "evidence": {
                "citations": citations,
                "sample_assets": sample_assets[:25],
                "relationship_count": len(relationships),
                "cluster_signals": attrs.get("signals", {}),
            },
            "feedback_loop": self._feedback_loop(capability),
        }

    def _service_from_context(self, context: dict[str, Any]) -> dict[str, Any]:
        candidate_id = stable_id(context["context_id"], "service", context["java_service_candidate"])
        return {
            "candidate_id": candidate_id,
            "name": context["name"],
            "bounded_context": context["name"],
            "domain": context["domain"],
            "capability": context["capability"],
            "java_service_candidate": context["java_service_candidate"],
            "package_candidate": context["package_candidate"],
            "decision_status": "candidate",
            "risk_score": context["risk_score"],
            "confidence": context["confidence"],
            "validation_status": context["validation_status"],
            "api_candidates": context["api_candidates"],
            "data_contracts": context["aggregate_candidates"][:12],
            "event_candidates": context["event_candidates"],
            "external_dependencies": context["external_dependencies"][:12],
            "feedback_loop": {
                "hypothesis": f"{context['name']} behavior is cohesive enough for a Java service boundary.",
                "quality_gates": [
                    "evidence_validation",
                    "contract_tests",
                    "golden_master_regression",
                    "dual_run_reconciliation",
                    "operational_readiness_review",
                ],
                "self_correction": "If gates fail, split the context by data ownership or keep the dependency on the mainframe.",
            },
            "evidence": context["evidence"],
        }

    def _relationships_for_assets(self, run_id: str, asset_ids: list[str]) -> list[dict[str, Any]]:
        if not asset_ids:
            return []
        placeholders = ",".join("?" for _ in asset_ids)
        with self.repository.connect() as conn:
            rows = conn.execute(
                f"""
                SELECT r.*, s.technical_name AS source_name, s.asset_type AS source_type,
                       t.technical_name AS target_name, t.asset_type AS target_type
                FROM relationship r
                JOIN asset s ON s.asset_id = r.source_asset_id
                JOIN asset t ON t.asset_id = r.target_asset_id
                WHERE r.run_id = ?
                  AND (r.source_asset_id IN ({placeholders}) OR r.target_asset_id IN ({placeholders}))
                ORDER BY r.relationship_type, s.technical_name, t.technical_name
                LIMIT 5000
                """,
                (run_id, *asset_ids, *asset_ids),
            ).fetchall()
            return [self.repository._relationship_row(row) for row in rows]

    def _aggregate_candidates(
        self, relationships: list[dict[str, Any]], member_asset_ids: set[str]
    ) -> list[dict[str, Any]]:
        candidates: dict[str, dict[str, Any]] = {}
        for rel in relationships:
            target_inside = rel["target_asset_id"] in member_asset_ids
            if rel["target_type"] not in DATA_ASSET_TYPES or not target_inside:
                continue
            rel_type = rel["relationship_type"]
            if rel_type in WRITE_RELS:
                role = "owned_write_model"
            elif rel_type in READ_RELS:
                role = "read_dependency"
            elif rel_type == "USES_COPYBOOK":
                role = "copybook_contract"
            elif rel_type in {"USES_MAP", "READS_QUEUE", "WRITES_QUEUE", "USES_QUEUE"}:
                role = "integration_contract"
            else:
                continue
            key = rel["target_asset_id"]
            existing = candidates.get(key)
            score = float(rel["confidence"]) + (0.2 if role == "owned_write_model" else 0.0)
            if existing and existing["score"] >= score:
                continue
            candidates[key] = {
                "asset_id": rel["target_asset_id"],
                "asset_type": rel["target_type"],
                "technical_name": rel["target_name"],
                "role": role,
                "source": rel_type,
                "score": round(score, 3),
                "confidence": rel["confidence"],
                "validation_status": rel["validation_status"],
            }
        return sorted(candidates.values(), key=lambda item: (-item["score"], item["technical_name"]))[:25]

    def _api_candidates(
        self,
        cluster: dict[str, Any],
        attrs: dict[str, Any],
        relationships: list[dict[str, Any]],
        member_asset_ids: set[str],
    ) -> list[dict[str, Any]]:
        entries: dict[str, dict[str, Any]] = {}
        root_id = cluster.get("root_asset_id")
        if root_id:
            root = next((asset for asset in attrs.get("sample_assets", []) if asset.get("asset_id") == root_id), None)
            if root:
                entries[root_id] = self._api_candidate(root["technical_name"], root["asset_type"], "cluster_root", 0.86)
        for rel in relationships:
            if rel["relationship_type"] not in ENTRY_RELS or rel["target_asset_id"] not in member_asset_ids:
                continue
            entries.setdefault(
                rel["target_asset_id"],
                self._api_candidate(rel["target_name"], rel["target_type"], rel["relationship_type"], rel["confidence"]),
            )
        if not entries and attrs.get("sample_assets"):
            asset = attrs["sample_assets"][0]
            entries[asset["asset_id"]] = self._api_candidate(asset["technical_name"], asset["asset_type"], "sample_asset", 0.55)
        return sorted(entries.values(), key=lambda item: item["operation"])[:12]

    def _event_candidates(
        self, relationships: list[dict[str, Any]], member_asset_ids: set[str]
    ) -> list[dict[str, Any]]:
        events = []
        for rel in relationships:
            if rel["source_asset_id"] not in member_asset_ids:
                continue
            if rel["relationship_type"] in {"WRITES_QUEUE", "WRITES_DATASET", "WRITES_TABLE"}:
                events.append(
                    {
                        "name": self._event_name(rel["target_name"]),
                        "publisher": rel["source_name"],
                        "target": rel["target_name"],
                        "target_type": rel["target_type"],
                        "source": rel["relationship_type"],
                        "confidence": rel["confidence"],
                        "validation_status": rel["validation_status"],
                    }
                )
        return events[:12]

    def _external_dependencies(
        self, relationships: list[dict[str, Any]], member_asset_ids: set[str]
    ) -> list[dict[str, Any]]:
        deps = []
        for rel in relationships:
            source_inside = rel["source_asset_id"] in member_asset_ids
            target_inside = rel["target_asset_id"] in member_asset_ids
            if source_inside == target_inside:
                continue
            deps.append(
                {
                    "relationship_type": rel["relationship_type"],
                    "source": rel["source_name"],
                    "target": rel["target_name"],
                    "direction": "outbound" if source_inside else "inbound",
                    "confidence": rel["confidence"],
                    "validation_status": rel["validation_status"],
                }
            )
        return deps[:25]

    @staticmethod
    def _api_candidate(name: str, asset_type: str, source: str, confidence: float) -> dict[str, Any]:
        operation = _camel("process " + name)
        return {
            "operation": operation,
            "interface_type": "batch_command" if asset_type in {"JOB", "SCHEDULE"} else "application_command",
            "source": source,
            "confidence": round(float(confidence), 3),
            "validation_status": "inferred",
        }

    @staticmethod
    def _event_name(target: str) -> str:
        return _camel(target + " changed") + "Event"

    @staticmethod
    def _service_name(capability: str) -> str:
        return _pascal(capability) + "Service"

    @staticmethod
    def _java_package(domain: str, capability: str) -> str:
        parts = re.findall(r"[A-Za-z0-9]+", f"{domain} {capability}".lower())
        return "com.mip." + ".".join(parts[:5] or ["legacy"])

    @staticmethod
    def _clean_cluster_name(name: str) -> str:
        return re.sub(r"\s+Cluster\s+\d+$", "", name).strip() or "Needs Review"

    @staticmethod
    def _feedback_loop(capability: str) -> dict[str, Any]:
        return {
            "hypothesis": f"{capability} can be understood and modernized as an independently reviewed slice.",
            "quality_gates": [
                "parser_confidence_threshold",
                "graph_boundary_review",
                "business_rule_traceability",
                "contract_tests",
                "dual_run_reconciliation",
            ],
            "correction_actions": [
                "raise needs_review facts",
                "split context by table ownership",
                "merge context when shared writes dominate",
                "add golden-master fixtures",
            ],
        }

    @staticmethod
    def _citations(
        cluster: dict[str, Any], sample_assets: list[dict[str, Any]], relationships: list[dict[str, Any]]
    ) -> list[dict[str, str]]:
        citations = [{"entity_kind": "CLUSTER", "entity_id": cluster.get("cluster_id", "")}]
        for asset in sample_assets[:5]:
            citations.append({"entity_kind": "ASSET", "entity_id": asset["asset_id"]})
        for rel in relationships[:5]:
            citations.append({"entity_kind": "RELATIONSHIP", "entity_id": rel["relationship_id"]})
        return [item for item in citations if item["entity_id"]]


def _camel(text: str) -> str:
    pascal = _pascal(text)
    return pascal[:1].lower() + pascal[1:] if pascal else "process"


def _pascal(text: str) -> str:
    parts = re.findall(r"[A-Za-z0-9]+", text)
    return "".join(part[:1].upper() + part[1:].lower() for part in parts) or "Legacy"
