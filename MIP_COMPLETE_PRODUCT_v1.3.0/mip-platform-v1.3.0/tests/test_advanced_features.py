from pathlib import Path

from mip.config import Settings
from mip.graph import KnowledgeGraph
from mip.persistence import SQLiteRepository
from mip.services.distributed import DistributedPlanner
from mip.services.pipeline import AnalysisPipeline

ROOT = Path(__file__).resolve().parents[1]


def test_advanced_analyzers_and_relationships(tmp_path: Path) -> None:
    db = tmp_path / "advanced.db"
    settings = Settings.from_env().with_overrides(db_path=db, output_dir=tmp_path / "out")
    summary = AnalysisPipeline(settings).analyze(ROOT / "examples" / "advanced-mainframe")
    repo = SQLiteRepository(db)
    stats = repo.stats(summary.run_id)

    assert stats["files"]["IMS"] == 1
    assert stats["files"]["MQ"] == 1
    assert stats["files"]["ASSEMBLER"] == 1
    assert stats["files"]["PL1"] == 1
    assert stats["files"]["SCHEDULER"] == 1
    assert stats["relationships"]["EXPANDS_TO"] >= 1
    assert stats["relationships"]["PUTS_MESSAGE"] >= 1
    assert stats["relationships"]["CONTAINS_SEGMENT"] >= 1
    assert stats["relationships"]["TRIGGERS"] >= 1

    graph = KnowledgeGraph(repo, summary.run_id)
    callees = {item["technical_name"] for item in graph.callees("ADVPLI")}
    assert "ADVPROG" in callees
    jobs = {item["technical_name"] for item in graph.jobs_executing("ADVPROG")}
    assert "ADVJOB" in jobs


def test_distributed_shard_plan_balances_files(tmp_path: Path) -> None:
    settings = Settings.from_env().with_overrides(
        db_path=tmp_path / "shards.db", output_dir=tmp_path
    )
    plan = DistributedPlanner(settings).plan(ROOT / "examples" / "advanced-mainframe", 3)
    assert len(plan) == 3
    assert sum(shard.file_count for shard in plan) >= 8
    assert all(shard.shard_count == 3 for shard in plan)
