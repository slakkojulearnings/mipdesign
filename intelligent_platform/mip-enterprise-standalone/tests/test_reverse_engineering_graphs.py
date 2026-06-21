from __future__ import annotations

import json
import sqlite3
import tempfile
import unittest
from pathlib import Path

from mip_intel.api import IntelligenceApi
from mip_intel.ingestion import scan_mainframe_tree


class ReverseEngineeringGraphTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name) / "estate"
        self.db = Path(self.tmp.name) / "mip.db"
        self._write_estate()
        scan_mainframe_tree(self.root, self.db, run_id="reverse")
        self.api = IntelligenceApi(self.db)

    def tearDown(self) -> None:
        self.tmp.cleanup()

    def _write_estate(self) -> None:
        files = {
            "app/cbl/CARDADV": """
       IDENTIFICATION DIVISION.
       PROGRAM-ID. CARDADV.
       DATA DIVISION.
       WORKING-STORAGE SECTION.
       01 WS-PARM PIC X(10).
       01 CARD-BALANCE PIC S9(9)V99.
       PROCEDURE DIVISION.
           COPY CALLBOOK REPLACING ==:SUBPGM:== BY ==REALSUB==.
           EXEC SQL UPDATE CARD_MASTER
              SET BALANCE = :CARD-BALANCE
           END-EXEC.
           STOP RUN.
""",
            "app/cpy/CALLBOOK": """
           CALL ':SUBPGM:'.
""",
            "app/jcl/DAILYCARD": """
//DAILYCARD JOB (ACCT),'CARD ADV'
//STEP1    EXEC PGM=CARDADV
""",
        }
        for relative, text in files.items():
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

    def test_copy_replacing_recovers_hidden_call_and_ast(self) -> None:
        rows = self.rows(
            """
            SELECT r.relationship_type, s.technical_name source_name, t.technical_name target_name
            FROM relationship r
            JOIN asset s ON s.asset_id = r.source_asset_id
            JOIN asset t ON t.asset_id = r.target_asset_id
            WHERE r.run_id = ?
            """,
            ("reverse",),
        )
        edges = {(row["relationship_type"], row["source_name"], row["target_name"]) for row in rows}
        self.assertIn(("CALLS", "CARDADV", "REALSUB"), edges)
        self.assertIn(("USES_COPYBOOK", "CARDADV", "CALLBOOK"), edges)
        self.assertNotIn(("DYNAMIC_CALL", "CARDADV", "DYNAMIC:TO"), edges)

        ast = self.api.ast_tree("CARDADV", "reverse")
        summary = ast["asset"]["attributes"]["ast_summary"]
        self.assertEqual(summary["program_id"], "CARDADV")
        self.assertTrue(summary["copy_replacing"])
        dependency_labels = {
            child["label"]
            for section in ast["ast_tree"]["children"]
            if section["type"] == "dependencies"
            for child in section["children"]
        }
        self.assertIn("REALSUB", dependency_labels)

    def test_360_call_graph_dependency_graph_and_required_files(self) -> None:
        downstream = self.api.call_graph("CARDADV", "reverse", direction="downstream", depth=4)
        self.assertIn("REALSUB", {node["technical_name"] for node in downstream["nodes"]})

        upstream = self.api.call_graph("CARDADV", "reverse", direction="upstream", depth=4)
        self.assertIn("DAILYCARD", {node["technical_name"] for node in upstream["nodes"]})

        dependency = self.api.dependency_graph("CARDADV", "reverse", direction="both", depth=4)
        self.assertIn("CALLBOOK", {node["technical_name"] for node in dependency["nodes"]})

        files = self.api.required_files("CARDADV", "reverse")
        relative_paths = {item["relative_path"] for item in files["files"]}
        self.assertIn("app/cbl/CARDADV", relative_paths)
        self.assertIn("app/cpy/CALLBOOK", relative_paths)
        self.assertIn("CARDADV", files["minimal_context"]["programs"])
        self.assertTrue(files["ast_summaries"])

    def test_bundle_export_writes_json_and_source_files(self) -> None:
        output = Path(self.tmp.name) / "bundle"
        summary = self.api.export_bundle("CARDADV", output, "reverse")
        self.assertTrue((output / "manifest.json").is_file())
        self.assertTrue((output / "minimal_context.json").is_file())
        self.assertTrue((output / "source" / "app" / "cbl" / "CARDADV").is_file())
        manifest = json.loads((output / "manifest.json").read_text(encoding="utf-8"))
        self.assertGreaterEqual(manifest["file_count"], 2)
        self.assertGreaterEqual(len(summary["copied_sources"]), 2)

    def test_clusters_are_graph_derived_not_llm_membership(self) -> None:
        clusters = self.api.clusters("reverse")["clusters"]
        self.assertTrue(clusters)
        methods = {cluster["attributes"]["method"] for cluster in clusters}
        self.assertIn("evidence_graph_components", methods)
        self.assertTrue(all(not cluster["attributes"]["signals"]["llm_membership_used"] for cluster in clusters))
        first = clusters[0]["attributes"]
        self.assertEqual(first["naming"]["naming_method"], "codebase_profile_plus_card_domain_ontology")
        self.assertIn("Card", clusters[0]["name"])
        self.assertTrue(first["java_service_candidate"].endswith("Service"))
        self.assertIn("drivers", first["naming"]["codebase_profile"])
        self.assertTrue(first["naming"]["matched_signals"])


if __name__ == "__main__":
    unittest.main()
