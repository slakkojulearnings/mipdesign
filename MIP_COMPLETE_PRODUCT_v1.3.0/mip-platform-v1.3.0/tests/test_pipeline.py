from pathlib import Path

from mip.config import Settings
from mip.graph import KnowledgeGraph
from mip.persistence import SQLiteRepository
from mip.services.pipeline import AnalysisPipeline
from mip.services.query import QueryService

SAMPLE = Path(__file__).resolve().parents[1] / "examples" / "sample-mainframe"


def test_end_to_end_pipeline(tmp_path: Path) -> None:
    db = tmp_path / "mip.db"
    output = tmp_path / "output"
    settings = Settings(db_path=db, output_dir=output)
    summary = AnalysisPipeline(settings).analyze(SAMPLE)

    assert summary.files_discovered >= 5
    assert summary.files_parsed >= 5
    assert summary.assets > 5
    assert summary.relationships > 5
    assert Path(summary.report_path or "").exists()

    repository = SQLiteRepository(db)
    stats = repository.stats()
    assert stats["assets"]["PROGRAM"] >= 2
    assert stats["assets"]["JOB"] >= 1

    graph = KnowledgeGraph(repository)
    assert [item["technical_name"] for item in graph.callers("CUSTVAL")] == ["CUST001"]
    assert [item["technical_name"] for item in graph.jobs_executing("CUST001")] == ["DAILYJOB"]
    assert "CUST001" in [item["technical_name"] for item in graph.root_programs()]

    impact = graph.impact("CUSTVAL", "PROGRAM")
    assert impact["blast_radius"] >= 2
    assert any(item["technical_name"] == "CUST001" for item in impact["affected_assets"])

    answer = QueryService(repository).ask("Which jobs execute CUST001?")
    assert answer["answer"][0]["technical_name"] == "DAILYJOB"
