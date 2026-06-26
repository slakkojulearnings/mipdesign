from __future__ import annotations

import sqlite3
import tempfile
import unittest
from pathlib import Path

from mip_intel.api import IntelligenceApi
from mip_intel.ingestion import scan_mainframe_tree
from mip_intel.models import Relationship


class EnrichmentPipelineTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name) / "estate"
        self.db = Path(self.tmp.name) / "mip.db"
        self.root.mkdir()

    def tearDown(self) -> None:
        self.tmp.cleanup()

    def write(self, relative: str, text: str) -> None:
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

    def test_relationship_identity_excludes_attributes_for_supersession(self) -> None:
        base = Relationship(
            run_id="r1",
            relationship_type="CALLS",
            source_asset_id="a",
            target_asset_id="b",
            attributes={"line": 10},
        )
        enriched = Relationship(
            run_id="r1",
            relationship_type="CALLS",
            source_asset_id="a",
            target_asset_id="b",
            attributes={"line": 10, "using": ["LK-COMMAREA"]},
        )
        flow1 = Relationship(
            run_id="r1",
            relationship_type="FLOWS_TO",
            source_asset_id="f1",
            target_asset_id="f2",
            attributes={"flow_kind": "MOVE", "line": 10, "source_field": "A", "target_field": "B"},
        )
        flow2 = Relationship(
            run_id="r1",
            relationship_type="FLOWS_TO",
            source_asset_id="f1",
            target_asset_id="f2",
            attributes={"flow_kind": "MOVE", "line": 11, "source_field": "A", "target_field": "B"},
        )

        self.assertEqual(base.relationship_id, enriched.relationship_id)
        self.assertNotEqual(flow1.relationship_id, flow2.relationship_id)

    def test_enrichment_status_and_artifacts_are_persistent(self) -> None:
        self.write(
            "app/CARD001",
            """
       IDENTIFICATION DIVISION.
       PROGRAM-ID. CARD001.
       PROCEDURE DIVISION.
           CALL 'CARD002'.
           STOP RUN.
""",
        )

        scan_mainframe_tree(self.root, self.db, run_id="run1")
        api = IntelligenceApi(self.db)

        before = api.parse_status("CARD001", "run1")["parser_status"]
        self.assertIn("cobol_ast", before["baseline_parser"])
        self.assertEqual(before["deep_parse_status"], "not_requested")

        result = api.enrich("run1", top_n=1, timeout=10, max_workers=1)
        self.assertEqual(result["selected"], 1)

        status_rows = self.rows("SELECT * FROM enrichment_member_status WHERE run_id = ?", ("run1",))
        artifact_rows = self.rows("SELECT * FROM enrichment_artifact_cache")
        job_rows = self.rows("SELECT * FROM enrichment_job WHERE run_id = ?", ("run1",))

        self.assertEqual(len(status_rows), 1)
        self.assertGreaterEqual(len(artifact_rows), 1)
        self.assertEqual(len(job_rows), 1)
        self.assertIn(status_rows[0]["state"], {"materialized", "failed", "unsupported"})

        after = api.parse_status("CARD001", "run1")["parser_status"]
        self.assertIn(after["deep_parse_status"], {"materialized", "completed", "failed", "unsupported"})
        coverage = api.enrichment_coverage("run1")["coverage"]
        self.assertEqual(coverage["members"], 1)


if __name__ == "__main__":
    unittest.main()
