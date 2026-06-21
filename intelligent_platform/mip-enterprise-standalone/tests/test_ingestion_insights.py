from __future__ import annotations

import sqlite3
import tempfile
import unittest
from pathlib import Path

from mip_intel.graph_service import GraphService
from mip_intel.ingestion import scan_mainframe_tree
from mip_intel.repositories import SQLiteGraphRepository


class IngestionInsightsTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name) / "CardDemo"
        self.db = Path(self.tmp.name) / "mip.db"
        self._write_estate(self.root)

    def tearDown(self) -> None:
        self.tmp.cleanup()

    def _write_estate(self, root: Path) -> None:
        files = {
            "app/cbl/CRDPOST": """
       IDENTIFICATION DIVISION.
       PROGRAM-ID. CRDPOST.
       DATA DIVISION.
       WORKING-STORAGE SECTION.
       01 WS-NEXT-PGM PIC X(8).
       PROCEDURE DIVISION.
           COPY CARDREC.
           CALL 'CRDVAL'.
           CALL WS-NEXT-PGM.
           EXEC SQL SELECT ACCT_ID FROM CARD_MASTER END-EXEC.
           EXEC CICS SEND MAP('CARDMAP') END-EXEC.
           STOP RUN.
""",
            "app/cbl/CRDVAL": """
       IDENTIFICATION DIVISION.
       PROGRAM-ID. CRDVAL.
       PROCEDURE DIVISION.
           STOP RUN.
""",
            "app/cpy/CARDREC": """
       01 CARD-REC.
          05 ACCT-ID PIC X(16).
""",
            "app/jcl/DAILYCRD": """
//DAILYCRD JOB (ACCT),'CARD POST'
//POSTSTEP EXEC PGM=CRDPOST
//INFILE   DD DSN=CARD.INPUT,DISP=SHR
""",
            "app/proc/CARDPROC": """
//CARDPROC PROC
//P1       EXEC PGM=CRDVAL
""",
            "app/bms/CARDMAP": """
CARDMAP  DFHMSD TYPE=&SYSPARM
""",
            "ddl/dcl/CARD_MASTER": """
      EXEC SQL DECLARE TABLE CARD_MASTER
      (ACCT_ID CHAR(16))
      END-EXEC.
""",
            "mq/CARDQ": "DEFINE QLOCAL(CARD.EVENT.Q)\n",
            "scheduler/CARDSCH": "SCHEDULE CARDPOST RUN DAILY JOB DAILYCRD\n",
            "app/csd/CARDCSD": "DEFINE TRANSACTION(CRD1) PROGRAM(CRDPOST)\n",
            "misc/UNKNOWN1": "plain text with no recognizable markers\n",
        }
        for relative, text in files.items():
            path = root / relative
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(text.lstrip(), encoding="utf-8")
        binary = root / "app/cbl/BINMEM"
        binary.parent.mkdir(parents=True, exist_ok=True)
        binary.write_bytes(b"\x00\x01\x02\x03")

    def rows(self, sql: str, params: tuple[object, ...] = ()) -> list[sqlite3.Row]:
        conn = sqlite3.connect(self.db)
        conn.row_factory = sqlite3.Row
        try:
            return conn.execute(sql, params).fetchall()
        finally:
            conn.close()

    def test_extensionless_carddemo_inventory_relationships_and_insights(self) -> None:
        result = scan_mainframe_tree(self.root, self.db, run_id="carddemo")

        self.assertEqual(result["run_id"], "carddemo")
        self.assertGreaterEqual(result["file_count"], 10)
        self.assertGreaterEqual(result["insight_count"], 2)
        self.assertTrue(result["warnings"])

        members = {
            row["relative_path"]: row
            for row in self.rows("SELECT * FROM source_member WHERE run_id = ?", ("carddemo",))
        }
        self.assertEqual(members["app/cbl/CRDPOST"]["artifact_type"], "COBOL")
        self.assertEqual(members["app/jcl/DAILYCRD"]["artifact_type"], "JCL")
        self.assertEqual(members["ddl/dcl/CARD_MASTER"]["artifact_type"], "DCLGEN")
        self.assertEqual(members["app/cbl/BINMEM"]["artifact_type"], "BINARY")
        self.assertEqual(members["misc/UNKNOWN1"]["validation_status"], "needs_review")

        rels = {
            row["relationship_type"]
            for row in self.rows("SELECT relationship_type FROM relationship WHERE run_id = ?", ("carddemo",))
        }
        self.assertIn("EXECUTES", rels)
        self.assertIn("CALLS", rels)
        self.assertIn("DYNAMIC_CALL", rels)
        self.assertIn("USES_COPYBOOK", rels)
        self.assertIn("READS_TABLE", rels)
        self.assertIn("USES_MAP", rels)

        roots = GraphService(SQLiteGraphRepository(self.db)).root_portfolio("carddemo")["roots"]
        self.assertTrue(any(row["technical_name"] == "CRDPOST" for row in roots))

        insights = self.rows("SELECT * FROM insight WHERE run_id = ? ORDER BY insight_type", ("carddemo",))
        insight_types = {row["insight_type"] for row in insights}
        self.assertIn("INVENTORY_SUMMARY", insight_types)
        self.assertIn("ROOT_SUMMARY", insight_types)
        self.assertIn("INGESTION_GAPS", insight_types)
        self.assertTrue(all(row["confidence"] > 0 for row in insights))
        self.assertTrue(all(row["validation_status"] in {"confirmed", "needs_review"} for row in insights))


if __name__ == "__main__":
    unittest.main()
