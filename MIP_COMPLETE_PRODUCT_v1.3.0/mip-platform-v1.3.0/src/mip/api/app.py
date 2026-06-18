from __future__ import annotations

import os
from pathlib import Path
from typing import Any

from fastapi import FastAPI, HTTPException, Query
from fastapi.responses import HTMLResponse
from pydantic import BaseModel, Field

from mip import __version__
from mip.api.dashboard import dashboard_html
from mip.graph import KnowledgeGraph
from mip.persistence import SQLiteRepository
from mip.services.business_rule_engine import BusinessRuleExtractionEngine
from mip.services.business_rules import BusinessRuleCatalogService
from mip.services.capability import CapabilityDiscoveryService
from mip.services.domain_discovery import DomainModelDiscoveryService
from mip.services.event_discovery import EventDiscoveryService
from mip.services.modernization_simulator import ModernizationSimulator
from mip.services.query import QueryService
from mip.services.scenarios import TestScenarioGenerator
from mip.services.service_boundary import ServiceBoundaryDiscoveryService
from mip.services.validation import ValidationService


class QuestionRequest(BaseModel):
    question: str = Field(min_length=2, max_length=500)


def create_app(db_path: Path | str | None = None) -> FastAPI:
    selected_value: Path | str = db_path or os.getenv("MIP_DB_PATH") or "data/mip.db"
    selected_db = Path(selected_value)
    repository = SQLiteRepository(selected_db)
    repository.initialize()
    app = FastAPI(
        title="Mainframe Intelligence Platform API",
        version=__version__,
        description="Evidence-backed legacy repository discovery and dependency intelligence.",
    )

    @app.get("/", response_class=HTMLResponse)
    def dashboard() -> str:
        return dashboard_html()

    @app.get("/health")
    def health() -> dict[str, Any]:
        return {
            "status": "ok",
            "version": __version__,
            "database": str(selected_db),
            "latest_run": repository.latest_run_id(),
        }

    @app.get("/stats")
    def stats() -> dict[str, Any]:
        return repository.stats()

    @app.get("/assets")
    def assets(
        asset_type: str | None = None,
        limit: int = Query(default=200, ge=1, le=5000),
    ) -> list[dict[str, Any]]:
        return repository.list_assets(asset_type=asset_type, limit=limit)

    @app.get("/assets/{name}")
    def asset(name: str, asset_type: str | None = None) -> dict[str, Any]:
        matches = repository.find_assets(name, asset_type)
        if not matches:
            raise HTTPException(status_code=404, detail=f"asset not found: {name}")
        item = matches[0]
        item["relationships"] = repository.relationships_for_asset(item["id"])
        return item

    @app.get("/programs/{name}/callers")
    def callers(name: str) -> list[dict[str, Any]]:
        try:
            return KnowledgeGraph(repository).callers(name)
        except KeyError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc

    @app.get("/programs/{name}/callees")
    def callees(name: str) -> list[dict[str, Any]]:
        try:
            return KnowledgeGraph(repository).callees(name)
        except KeyError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc

    @app.get("/programs/{name}/jobs")
    def jobs(name: str) -> list[dict[str, Any]]:
        try:
            return KnowledgeGraph(repository).jobs_executing(name)
        except KeyError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc

    @app.get("/impact/{name}")
    def impact(
        name: str, asset_type: str | None = None, max_depth: int = Query(8, ge=1, le=25)
    ) -> dict[str, Any]:
        try:
            return KnowledgeGraph(repository).impact(name, asset_type, max_depth)
        except KeyError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc

    @app.get("/roots")
    def roots() -> list[dict[str, Any]]:
        return KnowledgeGraph(repository).root_programs()

    @app.get("/lineage/{name}")
    def lineage(
        name: str,
        direction: str = Query("downstream", pattern="^(upstream|downstream)$"),
        max_depth: int = Query(8, ge=1, le=25),
    ) -> dict[str, Any]:
        try:
            return KnowledgeGraph(repository).lineage(name, direction, max_depth)
        except KeyError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc

    @app.get("/graph/metrics")
    def graph_metrics() -> dict[str, Any]:
        return KnowledgeGraph(repository).metrics()

    @app.get("/runs")
    def runs(limit: int = Query(10, ge=1, le=100)) -> list[dict[str, Any]]:
        return repository.recent_runs(limit)

    @app.get("/evidence/{entity_kind}/{entity_id}")
    def evidence(entity_kind: str, entity_id: str) -> list[dict[str, Any]]:
        return repository.evidence_for_entity(entity_kind, entity_id)

    @app.get("/validation")
    def validation() -> dict[str, Any]:
        return ValidationService(repository).validate()

    @app.get("/diff")
    def diff(newer_run: str | None = None, older_run: str | None = None) -> dict[str, Any]:
        return repository.diff_runs(newer_run, older_run)

    @app.get("/root-chain/{name}")
    def root_chain(name: str, max_depth: int = Query(12, ge=1, le=50)) -> dict[str, Any]:
        try:
            return CapabilityDiscoveryService(repository).root_driver_chain(name, max_depth)
        except KeyError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc

    @app.get("/capabilities/{capability}/files")
    def capability_files(capability: str, max_depth: int = Query(4, ge=0, le=12)) -> dict[str, Any]:
        return CapabilityDiscoveryService(repository).discover_capability(capability, max_depth)

    @app.get("/rules")
    def rules(capability: str | None = None) -> dict[str, Any]:
        return BusinessRuleCatalogService(repository).catalog(capability)

    @app.get("/test-scenarios")
    def test_scenarios(capability: str | None = None) -> dict[str, Any]:
        return TestScenarioGenerator(repository).generate(capability)

    @app.get("/insights")
    def insights(
        insight_type: str | None = None,
        limit: int = Query(1000, ge=1, le=100000),
    ) -> list[dict[str, Any]]:
        return repository.list_insights(insight_type, limit=limit)

    @app.get("/intelligence/business-rules")
    def structured_rules(capability: str | None = None) -> dict[str, Any]:
        return BusinessRuleExtractionEngine(repository).extract(capability)

    @app.get("/intelligence/domain-model")
    def domain_model(minimum_score: int = Query(2, ge=1, le=100)) -> dict[str, Any]:
        return DomainModelDiscoveryService(repository).discover(minimum_score)

    @app.get("/intelligence/events")
    def events(capability: str | None = None) -> dict[str, Any]:
        return EventDiscoveryService(repository).discover(capability)

    @app.get("/intelligence/service-boundaries")
    def service_boundaries(minimum_programs: int = Query(1, ge=1, le=1000)) -> dict[str, Any]:
        return ServiceBoundaryDiscoveryService(repository).discover(minimum_programs)

    @app.get("/modernization/simulate/{target}")
    def modernization_simulation(
        target: str,
        scenario: str = Query("modify", pattern="^(modify|retire|extract-service|replatform)$"),
        max_depth: int = Query(10, ge=1, le=50),
    ) -> dict[str, Any]:
        try:
            return ModernizationSimulator(repository).simulate(target, scenario, max_depth)
        except KeyError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc

    @app.post("/ask")
    def ask(request: QuestionRequest) -> dict[str, Any]:
        try:
            return QueryService(repository).ask(request.question)
        except KeyError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc

    return app


app = create_app()
