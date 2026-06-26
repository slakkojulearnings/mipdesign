from __future__ import annotations

import sqlite3
import sys
import tempfile
import unittest
from contextlib import closing
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from demo_fixture import demo_context
from mip_intel.api import IntelligenceApi
from mip_intel.models import Asset
from mip_intel.repositories import SQLiteGraphRepository
from mip_intel.storage import StorageConfig, create_repository


class Phase5ProductionReadinessTests(unittest.TestCase):
    def test_storage_factory_tracks_sqlite_schema_version_and_rejects_unknown_backend(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            db = Path(tmp) / "factory.db"
            repo = create_repository(StorageConfig(backend="sqlite", dsn=str(db)))
            self.assertIsInstance(repo, SQLiteGraphRepository)
            repo.initialize()

            with closing(sqlite3.connect(db)) as conn:
                row = conn.execute("SELECT version, backend FROM schema_version").fetchone()
            self.assertEqual(row, (2, "sqlite"))

            with self.assertRaises(NotImplementedError):
                create_repository(StorageConfig(backend="postgresql", dsn="postgresql://example"))

    def test_validation_persists_governance_results_and_flags_invalid_confidence(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            api = IntelligenceApi(Path(tmp) / "governance.db")
            run_id = api.repository.create_run("test://governance", run_id="governance")
            api.repository.upsert_asset(Asset(run_id, "PROGRAM", "BADCONF", confidence=1.7))
            api.repository.complete_run(run_id)

            payload = api.validate(run_id)

            self.assertEqual(payload["status"], "failed")
            checks = {check["check_name"]: check for check in payload["checks"]}
            self.assertEqual(checks["confidence_values_in_range"]["status"], "failed")

            with api.repository.connect() as conn:
                count = conn.execute(
                    "SELECT COUNT(*) FROM validation_result WHERE run_id = ?",
                    (run_id,),
                ).fetchone()[0]
            self.assertGreaterEqual(count, len(payload["checks"]))

    def test_export_manifest_reports_limits_and_checksums(self) -> None:
        context = demo_context()
        api: IntelligenceApi = context["api"]

        payload = api.export(context["run_id"], limit=1)

        self.assertTrue(payload["truncated"])
        self.assertEqual(payload["manifest"]["row_limit"], 1)
        self.assertGreater(payload["manifest"]["total_assets"], payload["manifest"]["exported_assets"])
        self.assertIn("checksum_sha256", payload["manifest"])
        self.assertEqual(payload["manifest"]["storage_backend"], "sqlite")
        self.assertEqual(payload["nodes"], payload["assets"])
        self.assertEqual(payload["edges"], payload["relationships"])
        self.assertIn("terminology", payload["manifest"])

    def test_graph_slice_exposes_query_limit_transparency(self) -> None:
        context = demo_context()
        api: IntelligenceApi = context["api"]
        root = api.roots(context["run_id"])["roots"][0]["asset_id"]

        payload = api.graph_slice(root, context["run_id"], depth=8, limit=2)

        self.assertTrue(payload["truncated"])
        self.assertEqual(payload["query_limits"]["requested_limit"], 2)
        self.assertEqual(payload["query_limits"]["effective_limit"], 2)
        self.assertTrue(payload["query_limits"]["truncated"])


if __name__ == "__main__":
    unittest.main()
