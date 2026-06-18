from pathlib import Path

from fastapi.testclient import TestClient
from typer.testing import CliRunner

from mip.api import create_app
from mip.cli import app
from mip.config import Settings
from mip.persistence import SQLiteRepository
from mip.semantics import CobolSemanticAnalyzer
from mip.services.business_rule_engine import BusinessRuleExtractionEngine
from mip.services.domain_discovery import DomainModelDiscoveryService
from mip.services.event_discovery import EventDiscoveryService
from mip.services.jcl_expansion import EnterpriseJclExpander
from mip.services.modernization_simulator import ModernizationSimulator
from mip.services.pipeline import AnalysisPipeline
from mip.services.service_boundary import ServiceBoundaryDiscoveryService

ROOT = Path(__file__).resolve().parents[1]
FIXTURE = ROOT / "tests" / "fixtures" / "compiler"
SAMPLE = ROOT / "examples" / "sample-mainframe"


def _repository(tmp_path: Path) -> SQLiteRepository:
    db = tmp_path / "mip.db"
    AnalysisPipeline(Settings(db_path=db, output_dir=tmp_path / "out")).analyze(SAMPLE)
    return SQLiteRepository(db)


def test_compiler_oriented_cobol_understanding() -> None:
    result = CobolSemanticAnalyzer([FIXTURE / "copybooks"], defines={"TESTMODE"}).analyze_file(
        FIXTURE / "COMPLEXCBL"
    )

    assert result["program"] == "COMPLEX01"
    assert {"NESTCPY", "BASECPY"}.issubset(set(result["copybooks"]))
    symbol_names = {item["name"] for item in result["symbols"]}
    assert "CARD-AMOUNT" in symbol_names
    assert "TEST-FLAG" in symbol_names
    dynamic = next(item for item in result["calls"] if item["kind"] == "DYNAMIC_RESOLVED")
    assert set(dynamic["targets"]) == {"SUBPGM1", "SUBPGM2"}
    assert any(edge["kind"] == "PERFORM" for edge in result["control_flow"]["edges"])
    assert any(rule["kind"] == "CALCULATION" for rule in result["business_rules"])
    assert not result["issues"]


def test_enterprise_jcl_expansion() -> None:
    result = EnterpriseJclExpander([FIXTURE / "proclib"]).expand_file(FIXTURE / "COMPLEXJCL")
    programs = {item["program"] for item in result["resolved_programs"]}
    assert "PAYPGM" in programs
    expanded = "\n".join(item["text"] for item in result["expanded_lines"])
    assert "APP1.INPUT" in expanded
    assert "APP.PAYPGM.OUTPUT" in expanded
    assert not result["issues"]
    assert any(item["kind"] == "PROC" and item["member"] == "OUTERPROC" for item in result["trace"])
    assert any(item["kind"] == "PROC" and item["member"] == "INNERPROC" for item in result["trace"])


def test_reasoning_engines_and_simulator(tmp_path: Path) -> None:
    repo = _repository(tmp_path)
    rules = BusinessRuleExtractionEngine(repo).extract()
    assert rules["rule_count"] >= 1
    assert rules["coverage"]["programs_examined"] >= 2

    domain = DomainModelDiscoveryService(repo).discover(minimum_score=1)
    assert domain["entity_count"] >= 1

    events = EventDiscoveryService(repo).discover()
    assert events["event_count"] >= 1

    services = ServiceBoundaryDiscoveryService(repo).discover()
    assert services["service_count"] >= 1
    assert all("fitness_score" in item for item in services["services"])

    simulation = ModernizationSimulator(repo).simulate("CUSTVAL", "retire")
    assert simulation["blast_radius"] >= 1
    assert simulation["predicted_breakages"]
    assert simulation["mitigations"]


def test_v13_cli_and_api(tmp_path: Path) -> None:
    runner = CliRunner()
    cobol = runner.invoke(
        app,
        [
            "cobol-understand",
            str(FIXTURE / "COMPLEXCBL"),
            "--copybook-dir",
            str(FIXTURE / "copybooks"),
            "--define",
            "TESTMODE",
        ],
    )
    assert cobol.exit_code == 0, cobol.output
    assert '"program": "COMPLEX01"' in cobol.output

    jcl = runner.invoke(
        app,
        [
            "jcl-expand",
            str(FIXTURE / "COMPLEXJCL"),
            "--proclib",
            str(FIXTURE / "proclib"),
        ],
    )
    assert jcl.exit_code == 0, jcl.output
    assert '"program": "PAYPGM"' in jcl.output

    repo = _repository(tmp_path)
    db = repo.db_path
    client = TestClient(create_app(db))
    assert client.get("/intelligence/business-rules").status_code == 200
    assert client.get("/intelligence/domain-model?minimum_score=1").status_code == 200
    assert client.get("/intelligence/events").status_code == 200
    assert client.get("/intelligence/service-boundaries").status_code == 200
    response = client.get("/modernization/simulate/CUSTVAL?scenario=retire")
    assert response.status_code == 200
    assert response.json()["scenario"] == "RETIRE"


def test_integrated_advanced_pipeline_and_persisted_insights(tmp_path: Path) -> None:
    from mip.services.advanced_pipeline import AdvancedAnalysisPipeline

    db = tmp_path / "advanced.db"
    output = tmp_path / "output"
    result = AdvancedAnalysisPipeline(Settings(db_path=db, output_dir=output)).analyze(
        FIXTURE,
        copybook_dirs=[FIXTURE / "copybooks"],
        proclib_dirs=[FIXTURE / "proclib"],
        defines={"TESTMODE"},
    )
    assert Path(result["manifest_path"]).exists()
    assert result["advanced"]["cobol_files"] >= 1
    assert result["advanced"]["jcl_files"] >= 1

    repo = SQLiteRepository(db)
    # Intelligence generation persists reusable derived knowledge.
    insights = repo.list_insights(limit=10000)
    assert any(item["insight_type"] == "BUSINESS_RULE" for item in insights)
    assert any(item["insight_type"] == "SERVICE_CANDIDATE" for item in insights)
