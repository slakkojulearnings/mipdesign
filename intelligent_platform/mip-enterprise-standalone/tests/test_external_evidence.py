from __future__ import annotations

import json
import sqlite3
import sys
import tempfile
import unittest
from contextlib import redirect_stdout
from io import StringIO
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from mip_intel.api import IntelligenceApi
from mip_intel.cli import main as cli_main
from mip_intel.ingestion import scan_mainframe_tree


class ExternalEvidenceTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name) / "estate"
        self.db = Path(self.tmp.name) / "mip.db"
        self.root.mkdir()

    def tearDown(self) -> None:
        self.tmp.cleanup()

    def write_source(self, relative: str, text: str) -> None:
        path = self.root / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text.lstrip(), encoding="utf-8")

    def rows(self, sql: str, params: tuple[object, ...] = ()) -> list[sqlite3.Row]:
        conn = sqlite3.connect(self.db)
        conn.row_factory = sqlite3.Row
        try:
            return conn.execute(sql, params).fetchall()
        finally:
            conn.close()

    def seed_program(self) -> None:
        self.write_source(
            "app/DYN001",
            """
       IDENTIFICATION DIVISION.
       PROGRAM-ID. DYN001.
       DATA DIVISION.
       WORKING-STORAGE SECTION.
       01 WS-PGM PIC X(8) VALUE 'PAYAUTH'.
       PROCEDURE DIVISION.
           CALL WS-PGM.
           GOBACK.
""",
        )
        scan_mainframe_tree(self.root, self.db, run_id="external")

    def test_runtime_import_preserves_baseline_node_and_feeds_call_graph(self) -> None:
        self.seed_program()
        runtime = Path(self.tmp.name) / "runtime.json"
        runtime.write_text(
            json.dumps(
                [
                    {
                        "source_program": "DYN001",
                        "target_program": "PAYAUTH",
                        "count": 7,
                        "environment": "QA",
                        "job": "PAYJOB",
                        "transaction": "PYA1",
                    }
                ]
            ),
            encoding="utf-8",
        )
        api = IntelligenceApi(self.db)

        payload = api.import_runtime(runtime, "external", source_system="smf")

        self.assertEqual(payload["imported"], 1)
        source = self.rows(
            "SELECT origin, member_id FROM asset WHERE run_id = ? AND asset_type = 'PROGRAM' AND technical_name = 'DYN001'",
            ("external",),
        )[0]
        self.assertEqual(source["origin"], "baseline")
        self.assertTrue(source["member_id"])
        rels = self.rows(
            """
            SELECT r.relationship_type, r.validation_status, r.attributes_json
            FROM relationship r
            JOIN asset s ON s.asset_id = r.source_asset_id
            JOIN asset t ON t.asset_id = r.target_asset_id
            WHERE r.run_id = ? AND s.technical_name = 'DYN001' AND t.technical_name = 'PAYAUTH'
            """,
            ("external",),
        )
        observed = [row for row in rels if row["relationship_type"] == "OBSERVED_CALLS"]
        self.assertEqual(len(observed), 1)
        self.assertEqual(observed[0]["validation_status"], "confirmed")
        self.assertEqual(json.loads(observed[0]["attributes_json"])["observation_count"], 7)

        call_graph = api.call_graph("DYN001", "external", direction="downstream", depth=1)
        self.assertTrue(any(edge["type"] == "OBSERVED_CALLS" for edge in call_graph["edges"]))
        coverage = {row["name"]: row["status"] for row in api.coverage("DYN001", "external")["coverage_report"]["checks"]}
        self.assertEqual(coverage["runtime_observations"], "captured")

    def test_catalog_import_persists_reconciliation_and_feeds_coverage(self) -> None:
        self.seed_program()
        catalog = Path(self.tmp.name) / "catalog.csv"
        catalog.write_text(
            "\n".join(
                [
                    "raw_dataset,canonical_dataset,dataset_type,owner,application",
                    "CARD.AUTH.OUT(+1),CARD.AUTH.OUT,GDG,CARDS,CARD-AUTH",
                ]
            ),
            encoding="utf-8",
        )
        api = IntelligenceApi(self.db)

        payload = api.import_catalog(catalog, "external", catalog_source="idcams")

        self.assertEqual(payload["imported"], 1)
        rows = self.rows("SELECT raw_dataset, canonical_dataset FROM catalog_dataset WHERE run_id = ?", ("external",))
        self.assertEqual(rows[0]["raw_dataset"], "CARD.AUTH.OUT(+1)")
        self.assertEqual(rows[0]["canonical_dataset"], "CARD.AUTH.OUT")
        rel_types = {
            row["relationship_type"]
            for row in self.rows("SELECT relationship_type FROM relationship WHERE run_id = ?", ("external",))
        }
        self.assertIn("CATALOG_DESCRIBES_DATASET", rel_types)
        self.assertIn("CATALOG_ALIASES_DATASET", rel_types)
        coverage = {
            row["name"]: row["status"]
            for row in api.coverage("CARD.AUTH.OUT(+1)", "external")["coverage_report"]["checks"]
        }
        self.assertEqual(coverage["dataset_identity"], "captured")
        self.assertEqual(coverage["catalog_reconciliation"], "captured")

    def test_external_evidence_cli_commands(self) -> None:
        self.seed_program()
        runtime = Path(self.tmp.name) / "runtime.json"
        runtime.write_text(json.dumps([{"source_program": "DYN001", "target_program": "PAYAUTH"}]), encoding="utf-8")
        out = StringIO()

        with redirect_stdout(out):
            rc = cli_main(["--db", str(self.db), "import-runtime", str(runtime), "--run-id", "external"])

        self.assertEqual(rc, 0)
        self.assertEqual(json.loads(out.getvalue())["imported"], 1)
        out = StringIO()
        with redirect_stdout(out):
            rc = cli_main(["--db", str(self.db), "external-evidence", "--run-id", "external"])
        self.assertEqual(rc, 0)
        payload = json.loads(out.getvalue())
        self.assertEqual(payload["runtime_observations"][0]["count"], 1)


if __name__ == "__main__":
    unittest.main()
