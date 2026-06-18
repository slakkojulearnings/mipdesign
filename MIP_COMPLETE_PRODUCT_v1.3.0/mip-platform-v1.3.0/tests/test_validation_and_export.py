from pathlib import Path

from mip.config import Settings
from mip.persistence import SQLiteRepository
from mip.services.graph_export import GraphExporter
from mip.services.pipeline import AnalysisPipeline
from mip.services.validation import ValidationService

SAMPLE = Path(__file__).resolve().parents[1] / "examples" / "sample-mainframe"


def test_validation_graph_export_and_run_diff(tmp_path: Path) -> None:
    db = tmp_path / "mip.db"
    output = tmp_path / "output"
    pipeline = AnalysisPipeline(Settings(db_path=db, output_dir=output))
    first = pipeline.analyze(SAMPLE)
    second = pipeline.analyze(SAMPLE)

    repository = SQLiteRepository(db)
    validation = ValidationService(repository).validate(second.run_id)
    assert validation["status"] in {"PASS", "WARN"}
    assert all(check["status"] != "FAIL" for check in validation["checks"])

    diff = repository.diff_runs(second.run_id, first.run_id)
    assert diff["added"] == []
    assert diff["removed"] == []
    assert diff["changed"] == []

    paths = GraphExporter(repository).export(tmp_path / "graph", second.run_id)
    assert Path(paths["json"]).exists()
    assert Path(paths["mermaid"]).exists()
    assert "flowchart LR" in Path(paths["mermaid"]).read_text(encoding="utf-8")
