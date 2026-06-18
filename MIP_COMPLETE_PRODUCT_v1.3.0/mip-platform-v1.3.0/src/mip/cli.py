from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import typer
from rich.console import Console
from rich.table import Table

from mip.api import create_app
from mip.config import Settings
from mip.graph import KnowledgeGraph
from mip.logging_config import configure_logging
from mip.persistence import SQLiteRepository
from mip.semantics import CobolSemanticAnalyzer
from mip.services.advanced_pipeline import AdvancedAnalysisPipeline
from mip.services.app_generator import ApplicationSkeletonGenerator
from mip.services.brd import BRDGenerator
from mip.services.business_rule_engine import BusinessRuleExtractionEngine
from mip.services.business_rules import BusinessRuleCatalogService
from mip.services.capability import CapabilityDiscoveryService
from mip.services.distributed import DistributedPlanner
from mip.services.domain_discovery import DomainModelDiscoveryService
from mip.services.event_discovery import EventDiscoveryService
from mip.services.exporter import MemoryExporter
from mip.services.graph_export import GraphExporter
from mip.services.intelligence_suite import IntelligenceSuite
from mip.services.jcl_expansion import EnterpriseJclExpander
from mip.services.modernization_simulator import ModernizationSimulator
from mip.services.pipeline import AnalysisPipeline
from mip.services.query import QueryService
from mip.services.report import ReportGenerator
from mip.services.scenarios import TestScenarioGenerator
from mip.services.service_boundary import ServiceBoundaryDiscoveryService
from mip.services.validation import ValidationService

app = typer.Typer(no_args_is_help=True, help="Mainframe Intelligence Platform CLI")
console = Console()


def _repo(db: Path) -> SQLiteRepository:
    repository = SQLiteRepository(db)
    repository.initialize()
    return repository


def _json(value: Any) -> None:
    console.print_json(json.dumps(value, default=str))


@app.command()
def init(db: Path = typer.Option(Path("data/mip.db"), help="SQLite database path")) -> None:
    """Initialize an empty MIP database."""
    _repo(db)
    console.print(f"Initialized [bold]{db}[/bold]")


@app.command()
def analyze(
    source: Path = typer.Argument(..., exists=True, file_okay=False, readable=True),
    db: Path = typer.Option(Path("data/mip.db"), help="SQLite database path"),
    output: Path = typer.Option(Path("output"), help="Generated output directory"),
) -> None:
    """Discover, classify, parse, persist, graph, and report a source repository."""
    configure_logging()
    settings = Settings.from_env().with_overrides(db_path=db, output_dir=output)
    summary = AnalysisPipeline(settings).analyze(source)
    _json(summary.model_dump())


@app.command()
def stats(db: Path = typer.Option(Path("data/mip.db"))) -> None:
    """Show latest analysis statistics."""
    _json(_repo(db).stats())


@app.command("list")
def list_assets(
    asset_type: str | None = typer.Argument(None, help="PROGRAM, JOB, COPYBOOK, TABLE, etc."),
    db: Path = typer.Option(Path("data/mip.db")),
    limit: int = typer.Option(200, min=1, max=5000),
) -> None:
    """List discovered assets."""
    rows = _repo(db).list_assets(asset_type, limit=limit)
    table = Table("Type", "Name", "Status", "Confidence")
    for row in rows:
        table.add_row(
            row["asset_type"],
            row["technical_name"],
            row["status"],
            f"{float(row['confidence']):.2f}",
        )
    console.print(table)


@app.command()
def show(
    name: str,
    asset_type: str | None = typer.Option(None),
    db: Path = typer.Option(Path("data/mip.db")),
) -> None:
    """Show an asset and its direct relationships."""
    repository = _repo(db)
    matches = repository.find_assets(name, asset_type)
    if not matches:
        raise typer.BadParameter(f"asset not found: {name}")
    item = matches[0]
    item["relationships"] = repository.relationships_for_asset(item["id"])
    _json(item)


@app.command()
def callers(name: str, db: Path = typer.Option(Path("data/mip.db"))) -> None:
    """List direct callers of a program."""
    _json(KnowledgeGraph(_repo(db)).callers(name))


@app.command()
def callees(name: str, db: Path = typer.Option(Path("data/mip.db"))) -> None:
    """List programs directly called by a program."""
    _json(KnowledgeGraph(_repo(db)).callees(name))


@app.command()
def jobs(name: str, db: Path = typer.Option(Path("data/mip.db"))) -> None:
    """List jobs that execute a program."""
    _json(KnowledgeGraph(_repo(db)).jobs_executing(name))


@app.command()
def roots(db: Path = typer.Option(Path("data/mip.db"))) -> None:
    """List likely root/entry programs."""
    _json(KnowledgeGraph(_repo(db)).root_programs())


@app.command()
def impact(
    name: str,
    asset_type: str | None = typer.Option(None),
    max_depth: int = typer.Option(8, min=1, max=25),
    db: Path = typer.Option(Path("data/mip.db")),
) -> None:
    """Calculate the dependency blast radius of an asset."""
    _json(KnowledgeGraph(_repo(db)).impact(name, asset_type, max_depth))


@app.command()
def lineage(
    name: str,
    direction: str = typer.Option("downstream", help="upstream or downstream"),
    max_depth: int = typer.Option(8, min=1, max=25),
    db: Path = typer.Option(Path("data/mip.db")),
) -> None:
    """Traverse graph lineage from an asset."""
    _json(KnowledgeGraph(_repo(db)).lineage(name, direction, max_depth))


@app.command()
def ask(question: str, db: Path = typer.Option(Path("data/mip.db"))) -> None:
    """Ask a deterministic natural-language repository question."""
    _json(QueryService(_repo(db)).ask(question))


@app.command()
def report(
    db: Path = typer.Option(Path("data/mip.db")),
    output: Path = typer.Option(Path("output/manual-report")),
) -> None:
    """Generate JSON, HTML, and portable memory indexes."""
    repository = _repo(db)
    report_path = ReportGenerator(repository).generate(output)
    MemoryExporter(repository).export(output / "memory")
    console.print(f"Generated [bold]{report_path}[/bold]")


@app.command()
def validate(db: Path = typer.Option(Path("data/mip.db"))) -> None:
    """Validate inventory consistency, parser health, and unresolved references."""
    result = ValidationService(_repo(db)).validate()
    _json(result)
    if result["status"] == "FAIL":
        raise typer.Exit(code=1)


@app.command()
def diff(
    db: Path = typer.Option(Path("data/mip.db")),
    newer_run: str | None = typer.Option(None),
    older_run: str | None = typer.Option(None),
) -> None:
    """Compare source-file changes between two analysis runs."""
    _json(_repo(db).diff_runs(newer_run, older_run))


@app.command("graph-export")
def graph_export(
    db: Path = typer.Option(Path("data/mip.db")),
    output: Path = typer.Option(Path("output/graph")),
) -> None:
    """Export the latest knowledge graph as JSON and Mermaid."""
    _json(GraphExporter(_repo(db)).export(output))


@app.command("tenant-create")
def tenant_create(
    tenant_id: str,
    name: str | None = typer.Option(None),
    db: Path = typer.Option(Path("data/mip.db")),
) -> None:
    """Create a tenant namespace for future isolated scans."""
    repository = _repo(db)
    repository.create_tenant(tenant_id, name)
    _json({"tenant_id": tenant_id, "name": name or tenant_id})


@app.command("tenant-list")
def tenant_list(db: Path = typer.Option(Path("data/mip.db"))) -> None:
    """List configured tenants."""
    _json(_repo(db).list_tenants())


@app.command("shard-plan")
def shard_plan(
    source: Path = typer.Argument(..., exists=True, file_okay=False, readable=True),
    shards: int = typer.Option(4, min=1, max=1024),
    db: Path = typer.Option(Path("data/mip.db")),
    output: Path = typer.Option(Path("output/shards.json")),
) -> None:
    """Create a deterministic distributed-analysis shard plan."""
    settings = Settings.from_env().with_overrides(db_path=db, output_dir=output.parent)
    plan = DistributedPlanner(settings).plan(source, shards)
    payload = {
        "source": str(source),
        "shard_count": shards,
        "shards": [
            {"shard_index": shard.shard_index, "file_count": shard.file_count, "files": shard.files}
            for shard in plan
        ],
    }
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    _json(payload)


@app.command("root-chain")
def root_chain(
    name: str,
    max_depth: int = typer.Option(12, min=1, max=50),
    db: Path = typer.Option(Path("data/mip.db")),
) -> None:
    """Discover the linked/chain programs and assets from a root driver program."""
    _json(CapabilityDiscoveryService(_repo(db)).root_driver_chain(name, max_depth=max_depth))


@app.command("capability-files")
def capability_files(
    capability: str,
    db: Path = typer.Option(Path("data/mip.db")),
    max_depth: int = typer.Option(4, min=0, max=12),
) -> None:
    """Find programs, jobs, copybooks, files, tables, rules, and dependencies for a capability."""
    _json(
        CapabilityDiscoveryService(_repo(db)).discover_capability(capability, max_depth=max_depth)
    )


@app.command("brd-root")
def brd_root(
    name: str,
    output: Path = typer.Option(Path("output/brd-root.md")),
    db: Path = typer.Option(Path("data/mip.db")),
) -> None:
    """Generate a BRD from a root driver program chain."""
    _json(BRDGenerator(_repo(db)).from_root(name, output))


@app.command("brd-capability")
def brd_capability(
    capability: str,
    output: Path = typer.Option(Path("output/brd-capability.md")),
    db: Path = typer.Option(Path("data/mip.db")),
) -> None:
    """Generate a BRD from a business capability/functionality name."""
    _json(BRDGenerator(_repo(db)).from_capability(capability, output))


@app.command("rule-catalog")
def rule_catalog(
    capability: str | None = typer.Option(None),
    db: Path = typer.Option(Path("data/mip.db")),
) -> None:
    """List extracted business rules and their implementing programs."""
    _json(BusinessRuleCatalogService(_repo(db)).catalog(capability))


@app.command("test-scenarios")
def test_scenarios(
    capability: str | None = typer.Option(None),
    db: Path = typer.Option(Path("data/mip.db")),
) -> None:
    """Generate functional test scenarios from extracted business rules."""
    _json(TestScenarioGenerator(_repo(db)).generate(capability))


@app.command("app-skeleton")
def app_skeleton(
    capability: str,
    output: Path = typer.Option(Path("output/generated-apps")),
    card_domain: bool = typer.Option(
        False, help="Generate configurable card-domain Python and Java functions."
    ),
    db: Path = typer.Option(Path("data/mip.db")),
) -> None:
    """Generate separated Python and Java function skeletons for a capability."""
    _json(
        ApplicationSkeletonGenerator(_repo(db)).generate_capability_app(
            capability, output, card_domain=card_domain
        )
    )


@app.command("card-app-skeleton")
def card_app_skeleton(
    functionality: str = typer.Argument("authorization"),
    output: Path = typer.Option(Path("output/generated-card-apps")),
    db: Path = typer.Option(Path("data/mip.db")),
) -> None:
    """Generate configurable credit/debit card Python and Java functions for a card functionality."""
    _json(
        ApplicationSkeletonGenerator(_repo(db)).generate_capability_app(
            functionality, output, card_domain=True
        )
    )


@app.command("insights")
def insights(
    insight_type: str | None = typer.Argument(None),
    db: Path = typer.Option(Path("data/mip.db")),
    limit: int = typer.Option(1000, min=1, max=100000),
) -> None:
    """List persisted rules, domain entities, events, services, and simulations."""
    _json(_repo(db).list_insights(insight_type, limit=limit))


@app.command("advanced-analyze")
def advanced_analyze(
    source: Path = typer.Argument(..., exists=True, file_okay=False, readable=True),
    db: Path = typer.Option(Path("data/mip.db")),
    output: Path = typer.Option(Path("output")),
    copybook_dir: list[Path] = typer.Option([], "--copybook-dir", exists=True, file_okay=False),
    proclib: list[Path] = typer.Option([], "--proclib", exists=True, file_okay=False),
    define: list[str] = typer.Option([], "--define"),
    symbol: list[str] = typer.Option([], "--symbol", help="NAME=VALUE"),
) -> None:
    """Run the complete deterministic advanced analysis and intelligence pipeline."""
    settings = Settings.from_env().with_overrides(db_path=db, output_dir=output)
    symbols = dict(item.split("=", 1) for item in symbol if "=" in item)
    result = AdvancedAnalysisPipeline(settings).analyze(
        source, copybook_dir, proclib, set(define), symbols
    )
    _json(result)


@app.command("cobol-understand")
def cobol_understand(
    source: Path = typer.Argument(..., exists=True, dir_okay=False, readable=True),
    copybook_dir: list[Path] = typer.Option([], "--copybook-dir", exists=True, file_okay=False),
    define: list[str] = typer.Option([], "--define"),
    output: Path | None = typer.Option(None),
) -> None:
    """Expand COPYs/directives and build COBOL symbol, call, control-flow, and rule models."""
    result = CobolSemanticAnalyzer(copybook_dir, set(define)).analyze_file(source)
    if output:
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(json.dumps(result, indent=2, default=str), encoding="utf-8")
    _json(result)


@app.command("jcl-expand")
def jcl_expand(
    source: Path = typer.Argument(..., exists=True, dir_okay=False, readable=True),
    proclib: list[Path] = typer.Option([], "--proclib", exists=True, file_okay=False),
    symbol: list[str] = typer.Option([], "--symbol", help="NAME=VALUE"),
    output: Path | None = typer.Option(None),
) -> None:
    """Resolve nested JCL PROCs, INCLUDE members, symbolics, and overrides."""
    symbols = dict(item.split("=", 1) for item in symbol if "=" in item)
    result = EnterpriseJclExpander(proclib).expand_file(source, symbols)
    if output:
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(json.dumps(result, indent=2, default=str), encoding="utf-8")
    _json(result)


@app.command("rules-extract")
def rules_extract(
    capability: str | None = typer.Option(None),
    db: Path = typer.Option(Path("data/mip.db")),
) -> None:
    """Extract structured validation, decision, calculation, and state-transition rules."""
    _json(BusinessRuleExtractionEngine(_repo(db)).extract(capability))


@app.command("domain-discover")
def domain_discover(
    minimum_score: int = typer.Option(2, min=1, max=100),
    db: Path = typer.Option(Path("data/mip.db")),
) -> None:
    """Discover candidate domain entities, attributes, and associations."""
    _json(DomainModelDiscoveryService(_repo(db)).discover(minimum_score))


@app.command("events-discover")
def events_discover(
    capability: str | None = typer.Option(None),
    db: Path = typer.Option(Path("data/mip.db")),
) -> None:
    """Discover candidate business events and consumers."""
    _json(EventDiscoveryService(_repo(db)).discover(capability))


@app.command("services-discover")
def services_discover(
    minimum_programs: int = typer.Option(1, min=1, max=1000),
    db: Path = typer.Option(Path("data/mip.db")),
) -> None:
    """Discover graph-backed service boundaries and coupling scores."""
    _json(ServiceBoundaryDiscoveryService(_repo(db)).discover(minimum_programs))


@app.command("simulate")
def simulate(
    target: str,
    scenario: str = typer.Option("modify", help="modify|retire|extract-service|replatform"),
    max_depth: int = typer.Option(10, min=1, max=50),
    db: Path = typer.Option(Path("data/mip.db")),
) -> None:
    """Simulate modernization impact, breakages, readiness, and mitigations."""
    try:
        _json(ModernizationSimulator(_repo(db)).simulate(target, scenario, max_depth))
    except KeyError as exc:
        raise typer.BadParameter(str(exc)) from exc


@app.command("intelligence-generate")
def intelligence_generate(
    output: Path = typer.Option(Path("output/intelligence")),
    capability: str | None = typer.Option(None),
    db: Path = typer.Option(Path("data/mip.db")),
) -> None:
    """Generate rule, domain, event, and service-boundary intelligence artifacts."""
    _json(IntelligenceSuite(_repo(db)).generate(output, capability))


@app.command()
def serve(
    db: Path = typer.Option(Path("data/mip.db")),
    host: str = typer.Option("127.0.0.1"),
    port: int = typer.Option(8000, min=1, max=65535),
) -> None:
    """Run the MIP FastAPI service."""
    import uvicorn

    uvicorn.run(create_app(db), host=host, port=port)
