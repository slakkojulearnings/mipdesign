from __future__ import annotations

import json
import sqlite3
import tempfile
import unittest
from pathlib import Path

from mip_intel.api import IntelligenceApi
from mip_intel.ingestion import scan_mainframe_tree


class Phase7To10CompleteIntelligenceTests(unittest.TestCase):
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

    def relationships(self, run_id: str) -> dict[tuple[str, str, str, str, str], dict]:
        rows = self.rows(
            """
            SELECT r.relationship_type, s.asset_type source_type, s.technical_name source_name,
                   t.asset_type target_type, t.technical_name target_name, r.attributes_json
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
            ): json.loads(row["attributes_json"])
            for row in rows
        }

    def test_db2_dclgen_join_columns_and_host_bindings_are_graph_facts(self) -> None:
        self.write(
            "app/cbl/CARDDB2",
            """
       IDENTIFICATION DIVISION.
       PROGRAM-ID. CARDDB2.
       DATA DIVISION.
       WORKING-STORAGE SECTION.
       01 WS-CARD-NO PIC X(16).
       01 WS-NAME PIC X(30).
       PROCEDURE DIVISION.
           EXEC SQL INCLUDE CARDACCT END-EXEC.
           EXEC SQL
              SELECT A.CARD_NO, C.CUST_NAME
                INTO :WS-CARD-NO, :WS-NAME
                FROM CARD_ACCT A
                JOIN CUSTOMER C
                  ON C.CUST_ID = A.CUST_ID
               WHERE A.CARD_NO = :WS-CARD-NO
           END-EXEC.
           GOBACK.
""",
        )
        self.write(
            "ddl/dcl/CARDACCT",
            """
       EXEC SQL DECLARE CARD_ACCT TABLE
       ( CARD_NO CHAR(16) NOT NULL,
         CUST_ID CHAR(9) )
       END-EXEC.
""",
        )

        scan_mainframe_tree(self.root, self.db, run_id="db2-7")
        rels = self.relationships("db2-7")

        self.assertIn(("USES_DCLGEN", "PROGRAM", "CARDDB2", "DCLGEN", "CARDACCT"), rels)
        self.assertIn(("DECLARES_TABLE", "DCLGEN", "CARDACCT", "TABLE", "CARD_ACCT"), rels)
        self.assertIn(("DCLGEN_DECLARES_TABLE", "DCLGEN", "CARDACCT", "TABLE", "CARD_ACCT"), rels)
        self.assertIn(
            ("STATEMENT_JOINS_ON_COLUMN", "DB2_STATEMENT", next(k[2] for k in rels if k[0] == "STATEMENT_JOINS_ON_COLUMN"), "DB2_COLUMN", "CUSTOMER.CUST_ID"),
            rels,
        )
        self.assertTrue(any(edge[0] == "STATEMENT_READS_COLUMN" and edge[4] == "CARD_ACCT.CARD_NO" for edge in rels))
        self.assertTrue(any(edge[0] == "HOST_VARIABLE_BINDS_COLUMN" and edge[2] == "CARDDB2::WS-CARD-NO" and edge[4] == "CARD_ACCT.CARD_NO" for edge in rels))

        api = IntelligenceApi(self.db)
        graph = api.dependency_graph("CARDDB2", "db2-7", direction="both", depth=4, limit=500)
        self.assertIn("USES_DCLGEN", {edge["type"] for edge in graph["edges"]})
        coverage = {check["name"]: check["status"] for check in api.coverage("CARDDB2", "db2-7")["coverage_report"]["checks"]}
        self.assertEqual(coverage["db2_dclgen"], "captured")

    def test_cics_contract_and_handle_condition_nodes_are_graph_facts(self) -> None:
        self.write(
            "app/cbl/CARDCICS",
            """
       IDENTIFICATION DIVISION.
       PROGRAM-ID. CARDCICS.
       DATA DIVISION.
       WORKING-STORAGE SECTION.
       01 WS-COMMAREA PIC X(100).
       01 WS-RESP PIC S9(8) COMP.
       PROCEDURE DIVISION.
       MAIN-PARA.
           EXEC CICS HANDLE CONDITION NOTFND(NOT-FOUND) ERROR(CICS-ERR) END-EXEC.
           EXEC CICS LINK PROGRAM('AUTHPGM')
                COMMAREA(WS-COMMAREA)
                CHANNEL(CH-AUTH)
                CONTAINER(CONT-AUTH)
                LENGTH(100)
                RESP(WS-RESP)
           END-EXEC.
           GOBACK.
       NOT-FOUND.
           GOBACK.
       CICS-ERR.
           GOBACK.
""",
        )

        scan_mainframe_tree(self.root, self.db, run_id="cics-7")
        rels = self.relationships("cics-7")

        self.assertTrue(any(edge[0] == "DEFINES_CICS_CONTRACT" and edge[1:3] == ("PROGRAM", "CARDCICS") for edge in rels))
        self.assertIn(("CONTRACT_USES_FIELD", "CICS_CONTRACT", "CARDCICS::CICS::10::LINK", "FIELD", "CARDCICS::WS-COMMAREA"), rels)
        self.assertIn(("CONTRACT_USES_FIELD", "CICS_CONTRACT", "CARDCICS::CICS::10::LINK", "FIELD", "CARDCICS::WS-RESP"), rels)
        self.assertIn(("HANDLES_CICS_CONDITION", "PROGRAM", "CARDCICS", "CICS_CONDITION", "CARDCICS::CICSCOND::NOTFND::9"), rels)
        self.assertIn(("BRANCHES_TO", "CICS_CONDITION", "CARDCICS::CICSCOND::NOTFND::9", "PARAGRAPH", "CARDCICS::NOT-FOUND"), rels)

    def test_file_io_business_rules_statement_order_and_sort_merge_are_graph_facts(self) -> None:
        self.write(
            "app/cbl/CARDFILE",
            """
       IDENTIFICATION DIVISION.
       PROGRAM-ID. CARDFILE.
       ENVIRONMENT DIVISION.
       INPUT-OUTPUT SECTION.
       FILE-CONTROL.
           SELECT CARDIN ASSIGN TO CARD.IN
              ORGANIZATION IS INDEXED
              ACCESS MODE IS DYNAMIC
              RECORD KEY IS CARD-KEY.
           SELECT CARDOUT ASSIGN TO CARD.OUT.
       DATA DIVISION.
       FILE SECTION.
       FD CARDIN.
       01 CARDIN-REC.
          05 CARD-KEY PIC X(16).
          05 CARD-AMT PIC S9(7)V99.
       FD CARDOUT.
       01 CARDOUT-REC.
          05 OUT-KEY PIC X(16).
       WORKING-STORAGE SECTION.
       01 WS-LIMIT PIC S9(7)V99.
       01 WS-FEE PIC S9(7)V99.
       01 WS-STATUS PIC X.
       PROCEDURE DIVISION.
       MAIN-SECTION SECTION.
       MAIN-PARA.
           OPEN INPUT CARDIN OUTPUT CARDOUT.
           READ CARDIN INTO CARDIN-REC KEY IS CARD-KEY INVALID KEY MOVE 'N' TO WS-STATUS END-READ.
           IF CARD-AMT > WS-LIMIT
              COMPUTE WS-FEE = CARD-AMT - WS-LIMIT
           END-IF.
           EVALUATE WS-STATUS
              WHEN 'A' MOVE 'APPROVED' TO OUT-KEY
              WHEN OTHER MOVE 'REVIEW' TO OUT-KEY
           END-EVALUATE.
           SORT SORTWK ON ASCENDING KEY CARD-KEY USING CARDIN GIVING CARDOUT.
           MERGE MERGEWK ON ASCENDING KEY CARD-KEY USING CARDIN GIVING CARDOUT.
           WRITE CARDOUT-REC INVALID KEY MOVE 'E' TO WS-STATUS END-WRITE.
           REWRITE CARDOUT-REC.
           DELETE CARDIN.
           START CARDIN KEY >= CARD-KEY.
           CLOSE CARDIN CARDOUT.
           GOBACK.
""",
        )

        scan_mainframe_tree(self.root, self.db, run_id="file-7")
        rels = self.relationships("file-7")

        self.assertIn(("CONTAINS_SECTION", "PROGRAM", "CARDFILE", "SECTION", "CARDFILE::MAIN-SECTION"), rels)
        self.assertIn(("SECTION_CONTAINS_PARAGRAPH", "SECTION", "CARDFILE::MAIN-SECTION", "PARAGRAPH", "CARDFILE::MAIN-PARA"), rels)
        self.assertIn(("HAS_RECORD_LAYOUT", "FILE", "CARDIN", "FILE_RECORD", "CARDFILE::CARDIN::CARDIN-REC"), rels)
        self.assertIn(("RECORD_DECLARES_FIELD", "FILE_RECORD", "CARDFILE::CARDIN::CARDIN-REC", "FIELD", "CARDFILE::CARD-KEY"), rels)

        read_ops = [key for key in rels if key[0] == "DEFINES_FILE_IO" and key[4].startswith("CARDFILE::FILEIO::READ")]
        self.assertTrue(read_ops)
        read_attrs = rels[read_ops[0]]
        self.assertEqual(read_attrs["verb"], "READ")
        self.assertEqual(read_attrs["file"], "CARDIN")
        self.assertEqual(read_attrs["key"], "CARD-KEY")
        self.assertTrue(read_attrs["exception_handlers"]["invalid_key"])

        self.assertTrue(any(edge[0] == "DEFINES_BUSINESS_RULE" and edge[3] == "BUSINESS_RULE" for edge in rels))
        self.assertTrue(any(edge[0] == "DEFINES_TRANSFORMATION" and edge[3] == "TRANSFORMATION" for edge in rels))
        self.assertTrue(any(edge[0] == "TRANSFORMATION_INPUT_FIELD" and edge[4] == "CARDFILE::CARD-AMT" for edge in rels))
        self.assertTrue(any(edge[0] == "TRANSFORMATION_OUTPUT_FIELD" and edge[4] == "CARDFILE::WS-FEE" for edge in rels))
        self.assertTrue(any(edge[0] == "CONTAINS_STATEMENT" and edge[3] == "STATEMENT" for edge in rels))
        self.assertTrue(any(edge[0] == "EXECUTES_BEFORE" and edge[1] == "STATEMENT" and edge[3] == "STATEMENT" for edge in rels))
        self.assertTrue(any(edge[0] == "DEFINES_SORT_MERGE" and edge[4].startswith("CARDFILE::SORTMERGE::SORT") for edge in rels))
        self.assertTrue(any(edge[0] == "DEFINES_SORT_MERGE" and edge[4].startswith("CARDFILE::SORTMERGE::MERGE") for edge in rels))

        api = IntelligenceApi(self.db)
        coverage = {check["name"]: check["status"] for check in api.coverage("CARDFILE", "file-7")["coverage_report"]["checks"]}
        self.assertEqual(coverage["file_io_semantics"], "captured")
        self.assertEqual(coverage["business_rule_graph"], "captured")
        self.assertEqual(coverage["statement_ordering"], "captured")
        self.assertEqual(coverage["sort_merge"], "captured")

    def test_jcl_dd_binding_gdg_and_return_code_flow_are_graph_facts(self) -> None:
        self.write(
            "app/jcl/CARDJOB",
            """
//CARDJOB JOB (ACCT),'CARD JOB'
//LOAD    EXEC PGM=IDCAMS
//IN      DD DSN=CARD.AUTH.IN(0),DISP=SHR
//OUT     DD DSN=CARD.AUTH.OUT(+1),DISP=(NEW,CATLG,DELETE)
// IF (LOAD.RC = 0) THEN
//POST    EXEC PGM=CARDPOST,COND=(4,LT,LOAD)
//POSTIN  DD DSN=CARD.AUTH.OUT(+1),DISP=SHR
// ENDIF
""",
        )

        scan_mainframe_tree(self.root, self.db, run_id="jcl-7")
        rels = self.relationships("jcl-7")

        self.assertIn(("DECLARES_DD", "JOB_STEP", "CARDJOB::LOAD", "JCL_DD", "CARDJOB::LOAD::IN"), rels)
        self.assertIn(("BINDS_DATASET", "JCL_DD", "CARDJOB::LOAD::OUT", "DATASET", "CARD.AUTH.OUT(+1)"), rels)
        self.assertTrue(rels[("BINDS_DATASET", "JCL_DD", "CARDJOB::LOAD::OUT", "DATASET", "CARD.AUTH.OUT(+1)")]["gdg"]["is_gdg"])
        self.assertIn(("CONDITION_REFERENCES_STEP", "JCL_CONDITION", "CARDJOB::COND::5", "JOB_STEP", "CARDJOB::LOAD"), rels)
        self.assertIn(("CONDITION_CHECKS_RETURN_CODE", "JCL_CONDITION", "CARDJOB::COND::5", "RETURN_CODE", "CARDJOB::LOAD::RC"), rels)
        self.assertIn(("CONDITION_REFERENCES_STEP", "JCL_CONDITION", "CARDJOB::COND::6", "JOB_STEP", "CARDJOB::LOAD"), rels)

        api = IntelligenceApi(self.db)
        coverage = {check["name"]: check["status"] for check in api.coverage("CARDJOB", "jcl-7")["coverage_report"]["checks"]}
        self.assertEqual(coverage["jcl_dd_binding"], "captured")
        self.assertEqual(coverage["jcl_proc_conditions"], "captured")


if __name__ == "__main__":
    unittest.main()
