from pathlib import Path

from typer.testing import CliRunner

from mip.cli import app
from mip.config import Settings
from mip.persistence import SQLiteRepository
from mip.services.app_generator import ApplicationSkeletonGenerator
from mip.services.brd import BRDGenerator
from mip.services.business_rules import BusinessRuleCatalogService
from mip.services.capability import CapabilityDiscoveryService
from mip.services.pipeline import AnalysisPipeline
from mip.services.scenarios import TestScenarioGenerator

SAMPLE = Path(__file__).resolve().parents[1] / "examples" / "sample-mainframe"


def _repo(tmp_path: Path) -> SQLiteRepository:
    db = tmp_path / "mip.db"
    AnalysisPipeline(Settings(db_path=db, output_dir=tmp_path / "out")).analyze(SAMPLE)
    return SQLiteRepository(db)


def test_root_driver_chain_capability_files_brd_rules_and_scenarios(tmp_path: Path) -> None:
    repo = _repo(tmp_path)
    capability = CapabilityDiscoveryService(repo)

    chain = capability.root_driver_chain("CUST001")
    chain_names = {asset["technical_name"] for asset in chain["assets"]}
    assert "CUST001" in chain_names
    assert "CUSTVAL" in chain_names
    assert any(rel["relationship_type"] == "CALLS" for rel in chain["relationships"])

    discovered = capability.discover_capability("customer validation")
    names = {asset["technical_name"] for asset in discovered["assets"]}
    assert {"CUST001", "CUSTVAL"} & names

    rules = BusinessRuleCatalogService(repo).catalog()
    assert rules["rule_count"] >= 1
    assert any(item["implemented_by"] for item in rules["rules"])

    scenarios = TestScenarioGenerator(repo).generate()
    assert scenarios["scenario_count"] >= 2

    brd_path = tmp_path / "brd.md"
    brd = BRDGenerator(repo).from_root("CUST001", brd_path)
    assert brd_path.exists()
    assert "Business Requirements Document" in brd["markdown"]
    assert brd["asset_count"] >= 2


def test_python_and_java_app_skeleton_are_generated_in_separate_folders(tmp_path: Path) -> None:
    repo = _repo(tmp_path)
    result = ApplicationSkeletonGenerator(repo).generate_capability_app(
        "card authorization", tmp_path / "apps", card_domain=True
    )
    root = Path(result["output_root"])
    assert (root / "python_functions" / "service.py").exists()
    assert (
        root
        / "java_functions"
        / "src"
        / "main"
        / "java"
        / "com"
        / "mip"
        / "generated"
        / "card_authorization"
        / "CardAuthorizationService.java"
    ).exists()
    assert "authorize_card_transaction" in (root / "python_functions" / "service.py").read_text(
        encoding="utf-8"
    )
    assert "authorizeCardTransaction" in (
        root
        / "java_functions"
        / "src"
        / "main"
        / "java"
        / "com"
        / "mip"
        / "generated"
        / "card_authorization"
        / "CardAuthorizationService.java"
    ).read_text(encoding="utf-8")


def test_cli_new_p0_p1_p2_commands(tmp_path: Path) -> None:
    runner = CliRunner()
    db = tmp_path / "mip.db"
    output = tmp_path / "out"
    analyzed = runner.invoke(
        app, ["analyze", str(SAMPLE), "--db", str(db), "--output", str(output)]
    )
    assert analyzed.exit_code == 0, analyzed.output

    for command in [
        ["root-chain", "CUST001", "--db", str(db)],
        ["capability-files", "customer validation", "--db", str(db)],
        ["rule-catalog", "--db", str(db)],
        ["test-scenarios", "--db", str(db)],
    ]:
        result = runner.invoke(app, command)
        assert result.exit_code == 0, result.output

    generated = runner.invoke(
        app,
        [
            "card-app-skeleton",
            "authorization",
            "--db",
            str(db),
            "--output",
            str(tmp_path / "generated"),
        ],
    )
    assert generated.exit_code == 0, generated.output
    assert (tmp_path / "generated" / "authorization" / "python_functions").exists()
    assert (tmp_path / "generated" / "authorization" / "java_functions").exists()
