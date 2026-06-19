from __future__ import annotations

import json
import sqlite3
import tempfile
import unittest
from pathlib import Path

from mip_intel.ingestion import scan_mainframe_tree


class Phase2ParserCoverageTests(unittest.TestCase):
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

    def test_db2_ddl_defines_tables_indexes_and_columns(self) -> None:
        self.write(
            "sources/sql/DB2_DDL/BNKCUST",
            """
DROP TABLE BNKCUST;
COMMIT;

CREATE TABLE BNKCUST
(
    BCS_PID                   CHAR(5) NOT NULL,
    BCS_NAME                  CHAR(25) NOT NULL,
    BCS_EMAIL                 CHAR(30) NOT NULL WITH DEFAULT,
    PRIMARY KEY (BCS_PID)
);

CREATE UNIQUE INDEX BNKCUST_IDX1 ON BNKCUST
(
     BCS_PID
);

CREATE DATABASE DBNASE;
CREATE BUFFERPOOL BP32K IMMEDIATE SIZE 250 PAGESIZE 32 K;
CREATE REGULAR TABLESPACE TS32K PAGESIZE 32 K BUFFERPOOL BP32K;
CREATE LOCATION DEMO2BNK IN "C:\\DEMO2BNK\\XDB";
""",
        )

        scan_mainframe_tree(self.root, self.db, run_id="db2")

        member = self.rows(
            "SELECT artifact_type, classification_basis FROM source_member WHERE run_id = ?",
            ("db2",),
        )[0]
        self.assertEqual(member["artifact_type"], "SQL_DDL")
        self.assertIn(member["classification_basis"], {"folder:sql", "content:SQL DDL"})

        rels = {
            (row["relationship_type"], row["source_type"], row["target_type"], row["target_name"]): json.loads(
                row["attributes_json"]
            )
            for row in self.rows(
                """
                SELECT r.relationship_type, s.asset_type source_type, t.asset_type target_type,
                       t.technical_name target_name, r.attributes_json
                FROM relationship r
                JOIN asset s ON s.asset_id = r.source_asset_id
                JOIN asset t ON t.asset_id = r.target_asset_id
                WHERE r.run_id = ?
                """,
                ("db2",),
            )
        }
        define_attrs = rels[("DEFINES_TABLE", "SQL_SCRIPT", "TABLE", "BNKCUST")]
        self.assertEqual(define_attrs["dialect"], "DB2")
        self.assertEqual(define_attrs["primary_key"], ["BCS_PID"])
        self.assertIn({"name": "BCS_EMAIL", "definition": "CHAR(30) NOT NULL WITH DEFAULT"}, define_attrs["columns"])

        index_attrs = rels[("INDEXES_TABLE", "SQL_SCRIPT", "TABLE", "BNKCUST")]
        self.assertEqual(index_attrs["index_name"], "BNKCUST_IDX1")
        self.assertTrue(index_attrs["unique"])
        self.assertEqual(index_attrs["columns"], ["BCS_PID"])

        self.assertIn(("DEFINES_DB2_DATABASE", "SQL_SCRIPT", "DB2_DATABASE", "DBNASE"), rels)
        self.assertIn(("DEFINES_DB2_BUFFERPOOL", "SQL_SCRIPT", "DB2_BUFFERPOOL", "BP32K"), rels)
        self.assertIn(("DEFINES_DB2_TABLESPACE", "SQL_SCRIPT", "DB2_TABLESPACE", "TS32K"), rels)
        self.assertIn(("DEFINES_DB2_LOCATION", "SQL_SCRIPT", "DB2_LOCATION", "DEMO2BNK"), rels)

    def test_ims_dbd_and_psb_relationships_are_extracted(self) -> None:
        self.write(
            "sources/ims/CRDDBD",
            """
DBDGEN NAME=CRDDBD,ACCESS=HDAM
DATASET DD1=CRDVSAM,DEVICE=3390
SEGM NAME=CARDSEG,PARENT=0,BYTES=128
FIELD NAME=CARD-NO,BYTES=16,START=1,TYPE=C
FINISH
END
""",
        )
        self.write(
            "sources/ims/CRDPSB",
            """
PSBGEN PSBNAME=CRDPSB,LANG=COBOL
PCB TYPE=DB,DBDNAME=CRDDBD,PROCOPT=A,KEYLEN=16
SENSEG NAME=CARDSEG,PARENT=0
END
""",
        )

        scan_mainframe_tree(self.root, self.db, run_id="ims")

        rels = {
            (row["relationship_type"], row["source_name"], row["target_type"], row["target_name"])
            for row in self.rows(
                """
                SELECT r.relationship_type, s.technical_name source_name, t.asset_type target_type,
                       t.technical_name target_name
                FROM relationship r
                JOIN asset s ON s.asset_id = r.source_asset_id
                JOIN asset t ON t.asset_id = r.target_asset_id
                WHERE r.run_id = ?
                """,
                ("ims",),
            )
        }
        self.assertIn(("DEFINES_IMS_DATABASE", "CRDDBD", "IMS_DATABASE", "CRDDBD"), rels)
        self.assertIn(("CONTAINS_IMS_SEGMENT", "CRDDBD", "IMS_SEGMENT", "CARDSEG"), rels)
        self.assertIn(("USES_DATASET", "CRDDBD", "DATASET", "CRDVSAM"), rels)
        self.assertIn(("USES_IMS_DATABASE", "CRDPSB", "IMS_DATABASE", "CRDDBD"), rels)
        self.assertIn(("USES_IMS_SEGMENT", "CRDPSB", "IMS_SEGMENT", "CARDSEG"), rels)

    def test_vsam_file_control_metadata_is_captured_from_cobol(self) -> None:
        self.write(
            "sources/cobol/CARDVSAM",
            """
       IDENTIFICATION DIVISION.
       PROGRAM-ID. CARDVSAM.
       ENVIRONMENT DIVISION.
       INPUT-OUTPUT SECTION.
       FILE-CONTROL.
           SELECT CARD-FILE ASSIGN TO CARDVSAM ORGANIZATION IS INDEXED
              ACCESS MODE IS DYNAMIC RECORD KEY IS CARD-NO.
       DATA DIVISION.
       FILE SECTION.
       FD CARD-FILE.
       01 CARD-REC.
          05 CARD-NO PIC X(16).
       PROCEDURE DIVISION.
           READ CARD-FILE.
           WRITE CARD-REC.
           STOP RUN.
""",
        )

        scan_mainframe_tree(self.root, self.db, run_id="vsam")

        rels = {
            (row["relationship_type"], row["target_type"], row["target_name"]): json.loads(row["attributes_json"])
            for row in self.rows(
                """
                SELECT r.relationship_type, t.asset_type target_type, t.technical_name target_name,
                       r.attributes_json
                FROM relationship r
                JOIN asset t ON t.asset_id = r.target_asset_id
                WHERE r.run_id = ?
                """,
                ("vsam",),
            )
        }
        self.assertEqual(rels[("USES_DATASET", "DATASET", "CARDVSAM")]["logical_file"], "CARD-FILE")
        self.assertEqual(rels[("USES_DATASET", "DATASET", "CARDVSAM")]["organization"], "INDEXED")
        self.assertEqual(rels[("USES_DATASET", "DATASET", "CARDVSAM")]["record_key"], "CARD-NO")
        self.assertIn(("DEFINES_FILE", "FILE", "CARD-FILE"), rels)
        self.assertIn(("READS_FILE", "FILE", "CARD-FILE"), rels)


if __name__ == "__main__":
    unittest.main()
