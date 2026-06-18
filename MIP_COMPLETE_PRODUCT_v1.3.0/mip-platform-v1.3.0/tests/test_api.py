from pathlib import Path

from fastapi.testclient import TestClient

from mip.api import create_app
from mip.config import Settings
from mip.services.pipeline import AnalysisPipeline

SAMPLE = Path(__file__).resolve().parents[1] / "examples" / "sample-mainframe"


def test_api_health_stats_and_queries(tmp_path: Path) -> None:
    db = tmp_path / "mip.db"
    AnalysisPipeline(Settings(db_path=db, output_dir=tmp_path / "out")).analyze(SAMPLE)
    client = TestClient(create_app(db))

    dashboard = client.get("/")
    assert dashboard.status_code == 200
    assert "Mainframe Intelligence Platform" in dashboard.text
    assert client.get("/health").status_code == 200
    stats = client.get("/stats")
    assert stats.status_code == 200
    assert stats.json()["assets"]["PROGRAM"] >= 2

    metrics = client.get("/graph/metrics")
    assert metrics.status_code == 200
    assert metrics.json()["nodes"] > 0

    runs = client.get("/runs")
    assert runs.status_code == 200
    assert len(runs.json()) == 1

    jobs = client.get("/programs/CUST001/jobs")
    assert jobs.status_code == 200
    assert jobs.json()[0]["technical_name"] == "DAILYJOB"

    answer = client.post("/ask", json={"question": "Who calls CUSTVAL?"})
    assert answer.status_code == 200
    assert answer.json()["answer"][0]["technical_name"] == "CUST001"
