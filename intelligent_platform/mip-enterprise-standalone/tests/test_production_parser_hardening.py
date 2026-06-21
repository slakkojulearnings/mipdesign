from __future__ import annotations

import json
import sqlite3
import tempfile
import unittest
from pathlib import Path

from mip_intel.ingestion import scan_mainframe_tree


class ProductionParserHardeningTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name) / "estate"
        self.db = Path(self.tmp.name) / "mip.db"

    def tearDown(self) -> None:
        self.tmp.cleanup()

    def rows(self, sql: str, params: tuple[object, ...] = ()) -> list[sqlite3.Row]:
        conn = sqlite3.connect(self.db)
        conn.row_factory = sqlite3.Row
        try:
            return conn.execute(sql, params).fetchall()
        finally:
            conn.close()

    def write(self, relative: str, text: str) -> None:
        path = self.root / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text.lstrip(), encoding="utf-8")

    def test_extensionless_unknown_member_is_resolved_as_copybook_and_cached(self) -> None:
        self.write(
            "src/CARDADV",
            """
       IDENTIFICATION DIVISION.
       PROGRAM-ID. CARDADV.
       PROCEDURE DIVISION.
           COPY CALLBOOK REPLACING ==:SUBPGM:== BY ==REALSUB==.
           STOP RUN.
""",
        )
        self.write(
            "shared/CALLBOOK",
            """
           CALL ':SUBPGM:'.
""",
        )

        scan_mainframe_tree(self.root, self.db, run_id="first")
        scan_mainframe_tree(self.root, self.db, run_id="second")

        promoted = self.rows(
            "SELECT * FROM source_member WHERE run_id = ? AND relative_path = ?",
            ("first", "shared/CALLBOOK"),
        )[0]
        self.assertEqual(promoted["artifact_type"], "COPYBOOK")
        self.assertEqual(promoted["validation_status"], "inferred")

        rels = {
            (row["relationship_type"], row["source_name"], row["target_name"])
            for row in self.rows(
                """
                SELECT r.relationship_type, s.technical_name source_name, t.technical_name target_name
                FROM relationship r
                JOIN asset s ON s.asset_id = r.source_asset_id
                JOIN asset t ON t.asset_id = r.target_asset_id
                WHERE r.run_id = ?
                """,
                ("first",),
            )
        }
        self.assertIn(("CALLS", "CARDADV", "REALSUB"), rels)

        attrs = json.loads(
            self.rows(
                "SELECT attributes_json FROM asset WHERE run_id = ? AND technical_name = ?",
                ("second", "CARDADV"),
            )[0]["attributes_json"]
        )
        self.assertEqual(attrs["parser"]["effective"], "local-antlr4-full-grammar")
        self.assertTrue(attrs["parser"]["cache_hit"])
        self.assertTrue(attrs["copy_resolution"][0]["resolved"])
        self.assertEqual(attrs["copy_resolution"][0]["source_path"], "shared/CALLBOOK")

        cache_count = self.rows("SELECT COUNT(*) c FROM parser_result_cache")[0]["c"]
        self.assertGreaterEqual(cache_count, 1)

    def test_unresolved_copybook_is_kept_as_needs_review_edge(self) -> None:
        self.write(
            "app/cbl/CARDMISS",
            """
       IDENTIFICATION DIVISION.
       PROGRAM-ID. CARDMISS.
       PROCEDURE DIVISION.
           COPY MISSINGCPY.
           STOP RUN.
""",
        )

        scan_mainframe_tree(self.root, self.db, run_id="missing")

        row = self.rows(
            """
            SELECT r.validation_status, r.confidence, t.technical_name target_name
            FROM relationship r
            JOIN asset t ON t.asset_id = r.target_asset_id
            WHERE r.run_id = ? AND r.relationship_type = 'USES_COPYBOOK'
            """,
            ("missing",),
        )[0]
        self.assertEqual(row["target_name"], "MISSINGCPY")
        self.assertEqual(row["validation_status"], "needs_review")
        self.assertLessEqual(row["confidence"], 0.35)

    def test_db2_schema_names_and_cics_queues_are_extracted(self) -> None:
        self.write(
            "app/cbl/CARDSQL",
            """
       IDENTIFICATION DIVISION.
       PROGRAM-ID. CARDSQL.
       PROCEDURE DIVISION.
           EXEC SQL
              SELECT A.ACCT_ID
                FROM BANK.CARD_ACCT A
                JOIN CUST.CUSTOMER C
                  ON C.CUST_ID = A.CUST_ID
           END-EXEC.
           EXEC SQL
              MERGE INTO AUTH.EVENTS E
              USING SYSIBM.SYSDUMMY1 S
                 ON E.ID = S.IBMREQD
           END-EXEC.
           EXEC CICS READQ TS QUEUE('CARD.EVENT.Q') END-EXEC.
           EXEC CICS WRITE FILE('CARD.VSAM.FILE') END-EXEC.
           STOP RUN.
""",
        )

        scan_mainframe_tree(self.root, self.db, run_id="sqlcics")

        rels = {
            (row["relationship_type"], row["target_type"], row["target_name"])
            for row in self.rows(
                """
                SELECT r.relationship_type, t.asset_type target_type, t.technical_name target_name
                FROM relationship r
                JOIN asset t ON t.asset_id = r.target_asset_id
                WHERE r.run_id = ?
                """,
                ("sqlcics",),
            )
        }
        self.assertIn(("READS_TABLE", "TABLE", "BANK.CARD_ACCT"), rels)
        self.assertIn(("READS_TABLE", "TABLE", "CUST.CUSTOMER"), rels)
        self.assertIn(("WRITES_TABLE", "TABLE", "AUTH.EVENTS"), rels)
        self.assertIn(("READS_QUEUE", "MQ_QUEUE", "CARD.EVENT.Q"), rels)
        self.assertIn(("WRITES_DATASET", "DATASET", "CARD.VSAM.FILE"), rels)


if __name__ == "__main__":
    unittest.main()
