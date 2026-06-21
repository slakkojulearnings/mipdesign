from __future__ import annotations

import json
import sqlite3
import tempfile
import unittest
from pathlib import Path

from mip_intel.api import IntelligenceApi
from mip_intel.ingestion import scan_mainframe_tree


class Phase6FeedbackPerformanceQualityTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name) / "estate"
        self.db = Path(self.tmp.name) / "mip.db"

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

    def relationships(self, run_id: str) -> set[tuple[str, str, str, str, str]]:
        rows = self.rows(
            """
            SELECT r.relationship_type, s.asset_type source_type, s.technical_name source_name,
                   t.asset_type target_type, t.technical_name target_name
            FROM relationship r
            JOIN asset s ON s.asset_id = r.source_asset_id
            JOIN asset t ON t.asset_id = r.target_asset_id
            WHERE r.run_id = ?
            """,
            (run_id,),
        )
        return {
            (
                row["relationship_type"],
                row["source_type"],
                row["source_name"],
                row["target_type"],
                row["target_name"],
            )
            for row in rows
        }

    def test_incremental_scan_records_telemetry_and_reuses_inventory_and_parse_cache(self) -> None:
        self.write(
            "app/cbl/CARDINC",
            """
       IDENTIFICATION DIVISION.
       PROGRAM-ID. CARDINC.
       PROCEDURE DIVISION.
           STOP RUN.
""",
        )

        scan_mainframe_tree(self.root, self.db, run_id="inc-1", config={"incremental": True})
        scan_mainframe_tree(self.root, self.db, run_id="inc-2", config={"incremental": True})

        api = IntelligenceApi(self.db)
        perf = api.performance("inc-2")
        self.assertTrue(perf["phases"])
        files = perf["by_artifact_type"]
        self.assertGreaterEqual(sum(int(row["reused_classifications"] or 0) for row in files), 1)
        self.assertGreaterEqual(sum(int(row["parse_cache_hits"] or 0) for row in files), 1)

        telemetry = self.rows(
            "SELECT reused_classification, parse_cache_hit FROM scan_file_telemetry WHERE run_id = ? AND relative_path = ?",
            ("inc-2", "app/cbl/CARDINC"),
        )[0]
        self.assertEqual(telemetry["reused_classification"], 1)
        self.assertEqual(telemetry["parse_cache_hit"], 1)

    def test_discovery_correction_overrides_member_classification(self) -> None:
        self.write("shared/CARDREC", "plain copy payload with no level numbers\n")
        api = IntelligenceApi(self.db)
        api.add_correction(
            entity_kind="MEMBER",
            selector="shared/CARDREC",
            action="CLASSIFY_AS",
            corrected_type="COPYBOOK",
            corrected_status="confirmed",
            corrected_confidence=0.99,
            reason="Known enterprise copybook without extension or level numbers",
        )

        scan_mainframe_tree(self.root, self.db, run_id="corrected")
        member = self.rows(
            "SELECT artifact_type, classification_basis, confidence FROM source_member WHERE run_id = ? AND relative_path = ?",
            ("corrected", "shared/CARDREC"),
        )[0]
        self.assertEqual(member["artifact_type"], "COPYBOOK")
        self.assertTrue(member["classification_basis"].startswith("correction:"))
        self.assertAlmostEqual(member["confidence"], 0.99)
        self.assertEqual(len(api.corrections("corrected")["corrections"]), 1)

    def test_ground_truth_scorecard_persists_precision_and_recall(self) -> None:
        self.write(
            "app/cbl/CARDSRC",
            """
       IDENTIFICATION DIVISION.
       PROGRAM-ID. CARDSRC.
       PROCEDURE DIVISION.
           CALL 'CARDTGT'.
           STOP RUN.
""",
        )
        scan_mainframe_tree(self.root, self.db, run_id="score")
        manifest = Path(self.tmp.name) / "scorecard.json"
        manifest.write_text(
            json.dumps(
                {
                    "name": "card-score",
                    "expected_members": [{"path": "app/cbl/CARDSRC", "artifact_type": "COBOL"}],
                    "expected_nodes": [
                        {"type": "PROGRAM", "name": "CARDSRC"},
                        {"type": "PROGRAM", "name": "CARDTGT"},
                    ],
                    "expected_edges": [{"type": "CALLS", "source": "CARDSRC", "target": "CARDTGT"}],
                    "forbidden_edges": [{"type": "CALLS", "source": "CARDSRC", "target": "WRONG"}],
                }
            ),
            encoding="utf-8",
        )

        api = IntelligenceApi(self.db)
        result = api.run_scorecard(manifest, "score")
        self.assertEqual(result["status"], "passed")
        self.assertEqual(result["precision"], 1.0)
        self.assertEqual(result["recall"], 1.0)
        self.assertEqual(api.scorecards("score")["scorecards"][0]["name"], "card-score")

    def test_copybook_resolver_uses_configured_search_order_and_records_conflicts(self) -> None:
        self.write(
            "app/cbl/CARDADV",
            """
       IDENTIFICATION DIVISION.
       PROGRAM-ID. CARDADV.
       PROCEDURE DIVISION.
           COPY CALLBOOK.
           STOP RUN.
""",
        )
        self.write("copylibA/CALLBOOK", "           CALL 'WRONG'.\n")
        self.write("copylibB/CALLBOOK", "           CALL 'RIGHT'.\n")

        scan_mainframe_tree(
            self.root,
            self.db,
            run_id="copy-order",
            config={"copybook_dirs": ["copylibB", "copylibA"]},
        )
        rels = self.relationships("copy-order")
        self.assertIn(("CALLS", "PROGRAM", "CARDADV", "PROGRAM", "RIGHT"), rels)
        self.assertNotIn(("CALLS", "PROGRAM", "CARDADV", "PROGRAM", "WRONG"), rels)
        attrs = json.loads(
            self.rows(
                "SELECT attributes_json FROM asset WHERE run_id = ? AND technical_name = ?",
                ("copy-order", "CARDADV"),
            )[0]["attributes_json"]
        )
        copy_resolution = attrs["copy_resolution"][0]
        self.assertEqual(copy_resolution["source_path"], "copylibB/CALLBOOK")
        self.assertTrue(copy_resolution["conflict"])
        self.assertEqual(copy_resolution["candidate_count"], 2)

    def test_db2_statement_nodes_host_variables_and_column_bindings_are_captured(self) -> None:
        self.write(
            "app/cbl/SQLDEEP",
            """
       IDENTIFICATION DIVISION.
       PROGRAM-ID. SQLDEEP.
       DATA DIVISION.
       WORKING-STORAGE SECTION.
       01 WS-CARD-NO PIC X(16).
       01 WS-BALANCE PIC S9(9)V99 COMP-3.
       PROCEDURE DIVISION.
           EXEC SQL
              SELECT CARD_NO, BALANCE
                INTO :WS-CARD-NO, :WS-BALANCE
                FROM CARD_ACCT
               WHERE CARD_NO = :WS-CARD-NO
           END-EXEC.
           GOBACK.
""",
        )

        scan_mainframe_tree(self.root, self.db, run_id="sql-deep")
        rels = self.relationships("sql-deep")
        self.assertTrue(any(edge[0] == "DEFINES_DB2_STATEMENT" and edge[2] == "SQLDEEP" for edge in rels))
        self.assertTrue(any(edge[0] == "STATEMENT_READS_TABLE" and edge[4] == "CARD_ACCT" for edge in rels))
        self.assertTrue(any(edge[0] == "STATEMENT_READS_COLUMN" and edge[4] == "CARD_ACCT.CARD_NO" for edge in rels))
        self.assertTrue(any(edge[0] == "STATEMENT_OUTPUTS_TO_HOST_VARIABLE" and edge[4] == "SQLDEEP::WS-CARD-NO" for edge in rels))
        self.assertTrue(any(edge[0] == "HOST_VARIABLE_BINDS_COLUMN" and edge[2] == "SQLDEEP::WS-CARD-NO" and edge[4] == "CARD_ACCT.CARD_NO" for edge in rels))

        api = IntelligenceApi(self.db)
        graph = api.dependency_graph("SQLDEEP", "sql-deep", direction="both", depth=3, limit=500)
        self.assertIn("DEFINES_DB2_STATEMENT", {edge["type"] for edge in graph["edges"]})
        coverage = {check["name"]: check["status"] for check in api.coverage("SQLDEEP", "sql-deep")["coverage_report"]["checks"]}
        self.assertEqual(coverage["db2_statement_model"], "captured")


if __name__ == "__main__":
    unittest.main()
