from __future__ import annotations

import json
import sqlite3
import tempfile
import unittest
from pathlib import Path

from mip_intel.api import IntelligenceApi
from mip_intel.ingestion import scan_mainframe_tree


class EnterpriseDeepParserModelTests(unittest.TestCase):
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

    def test_db2_cursor_package_and_plan_model_are_graph_facts(self) -> None:
        self.write(
            "app/cbl/CARDBILL",
            """
       IDENTIFICATION DIVISION.
       PROGRAM-ID. CARDBILL.
       DATA DIVISION.
       WORKING-STORAGE SECTION.
       01 WS-CARD-NO PIC X(16).
       01 WS-BALANCE PIC S9(9)V99 COMP-3.
       PROCEDURE DIVISION.
           EXEC SQL
              DECLARE C1 CURSOR WITH HOLD FOR
              SELECT CARD_NO, BALANCE
                FROM CARD_ACCT
               WHERE CARD_NO = :WS-CARD-NO
           END-EXEC.
           EXEC SQL OPEN C1 END-EXEC.
           EXEC SQL FETCH C1 INTO :WS-CARD-NO, :WS-BALANCE END-EXEC.
           EXEC SQL CLOSE C1 END-EXEC.
           GOBACK.
""",
        )
        self.write(
            "sql/bind/CARDBIND",
            """
BIND PACKAGE(CARDCOLL.CARDBILL) MEMBER(CARDBILL) QUALIFIER(CARDAPP) OWNER(CARDADM);
BIND PLAN(CARDPLAN) PKLIST(CARDCOLL.CARDBILL) ACTION(REPLACE);
""",
        )

        scan_mainframe_tree(self.root, self.db, run_id="db2-deep")
        rels = self.relationships("db2-deep")

        cursor_key = ("DEFINES_DB2_CURSOR", "PROGRAM", "CARDBILL", "DB2_CURSOR", "CARDBILL::C1")
        self.assertIn(cursor_key, rels)
        self.assertEqual(rels[cursor_key]["tables"], ["CARD_ACCT"])
        self.assertEqual(rels[cursor_key]["host_vars"], ["WS-CARD-NO"])
        self.assertTrue(rels[cursor_key]["query_shape"]["has_where"])
        self.assertIn(
            ("CURSOR_READS_TABLE", "DB2_CURSOR", "CARDBILL::C1", "TABLE", "CARD_ACCT"),
            rels,
        )
        self.assertIn(
            ("CURSOR_READS_COLUMN", "DB2_CURSOR", "CARDBILL::C1", "DB2_COLUMN", "CARD_ACCT.CARD_NO"),
            rels,
        )
        self.assertIn(
            ("CURSOR_FILTERS_BY_COLUMN", "DB2_CURSOR", "CARDBILL::C1", "DB2_COLUMN", "CARD_ACCT.CARD_NO"),
            rels,
        )
        fetch_key = ("FETCHES_DB2_CURSOR", "PROGRAM", "CARDBILL", "DB2_CURSOR", "CARDBILL::C1")
        self.assertIn(fetch_key, rels)
        self.assertEqual(rels[fetch_key]["host_vars"], ["WS-CARD-NO", "WS-BALANCE"])

        self.assertIn(
            ("DEFINES_DB2_PACKAGE", "SQL_SCRIPT", "CARDBIND", "DB2_PACKAGE", "CARDCOLL.CARDBILL"),
            rels,
        )
        self.assertIn(
            ("BINDS_PROGRAM", "DB2_PACKAGE", "CARDCOLL.CARDBILL", "PROGRAM", "CARDBILL"),
            rels,
        )
        self.assertIn(
            ("USES_DB2_PACKAGE", "DB2_PLAN", "CARDPLAN", "DB2_PACKAGE", "CARDCOLL.CARDBILL"),
            rels,
        )

        api = IntelligenceApi(self.db)
        dependency = api.dependency_graph("CARDBILL", "db2-deep", direction="both", depth=3, limit=500)
        self.assertIn("DEFINES_DB2_CURSOR", {edge["type"] for edge in dependency["edges"]})
        self.assertIn("CURSOR_READS_TABLE", {edge["type"] for edge in dependency["edges"]})

    def test_jcl_proc_expansion_conditions_and_symbolic_datasets(self) -> None:
        self.write(
            "app/proc/CARDPROC",
            """
//CARDPROC PROC APP=CARD,
//             FLOW=AUTH
//EXTRACT  EXEC PGM=&APP.AUTH
//IN       DD DSN=&APP..&FLOW..IN,
//            DISP=SHR
//POST     EXEC PGM=CARDPOST
//OUT      DD DSN=&APP..&FLOW..OUT,
//            DISP=(NEW,CATLG,DELETE)
""",
        )
        self.write(
            "app/jcl/CARDRUN",
            """
//CARDRUN  JOB (ACCT),'CARD RUN'
//AUTH     EXEC PROC=CARDPROC,
//            APP=CARD
// IF (AUTH.RC = 0) THEN
//REPORT   EXEC PGM=CARDRPT,COND=(4,LT,AUTH)
// ENDIF
""",
        )

        scan_mainframe_tree(self.root, self.db, run_id="jcl-proc")
        rels = self.relationships("jcl-proc")

        self.assertIn(
            ("INVOKES_PROC", "JOB", "CARDRUN", "PROC", "CARDPROC"),
            rels,
        )
        self.assertIn(
            ("EXPANDS_TO_STEP", "JOB_STEP", "CARDRUN::AUTH", "JOB_STEP", "CARDRUN::AUTH.EXTRACT"),
            rels,
        )
        self.assertIn(
            ("EXPANDED_FROM_PROC_STEP", "JOB_STEP", "CARDRUN::AUTH.EXTRACT", "PROC_STEP", "CARDPROC::EXTRACT"),
            rels,
        )
        exec_key = ("EXECUTES", "JOB_STEP", "CARDRUN::AUTH.EXTRACT", "PROGRAM", "CARD.AUTH")
        self.assertIn(exec_key, rels)
        read_key = ("READS_DATASET", "JOB_STEP", "CARDRUN::AUTH.EXTRACT", "DATASET", "CARD.AUTH.IN")
        write_key = ("WRITES_DATASET", "JOB_STEP", "CARDRUN::AUTH.POST", "DATASET", "CARD.AUTH.OUT")
        self.assertIn(read_key, rels)
        self.assertIn(write_key, rels)
        self.assertEqual(rels[read_key]["unresolved_symbolics"], [])
        self.assertEqual(rels[write_key]["dd_name"], "OUT")
        self.assertIn(
            ("DEFINES_CONDITION", "JOB", "CARDRUN", "JCL_CONDITION", "CARDRUN::COND::4"),
            rels,
        )
        self.assertIn(
            ("CONTROLS_STEP", "JCL_CONDITION", "CARDRUN::COND::4", "JOB_STEP", "CARDRUN::REPORT"),
            rels,
        )
        self.assertIn(
            ("CONTROLS_STEP", "JCL_CONDITION", "CARDRUN::COND::5", "JOB_STEP", "CARDRUN::REPORT"),
            rels,
        )

    def test_copybook_field_ownership_nodes_link_program_fields_to_copybook_fields(self) -> None:
        self.write(
            "app/cpy/CARDCOPY",
            """
       01 CARD-RECORD.
          05 CARD-NO PIC X(16).
          05 CARD-BALANCE PIC S9(9)V99 COMP-3.
          05 CARD-STATUS PIC X.
""",
        )
        self.write(
            "app/cbl/CARDOWN",
            """
       IDENTIFICATION DIVISION.
       PROGRAM-ID. CARDOWN.
       DATA DIVISION.
       WORKING-STORAGE SECTION.
       COPY CARDCOPY.
       PROCEDURE DIVISION.
           DISPLAY CARD-NO.
           GOBACK.
""",
        )

        scan_mainframe_tree(self.root, self.db, run_id="copy-fields")
        rels = self.relationships("copy-fields")

        self.assertIn(
            ("DECLARES_COPYBOOK_FIELD", "COPYBOOK", "CARDCOPY", "COPYBOOK_FIELD", "CARDCOPY::CARD-NO"),
            rels,
        )
        self.assertIn(
            ("FIELD_DERIVED_FROM_COPYBOOK", "FIELD", "CARDOWN::CARD-NO", "COPYBOOK_FIELD", "CARDCOPY::CARD-NO"),
            rels,
        )
        self.assertIn(
            ("USES_COPYBOOK_FIELD", "PROGRAM", "CARDOWN", "COPYBOOK_FIELD", "CARDCOPY::CARD-BALANCE"),
            rels,
        )
        self.assertEqual(
            rels[
                ("DECLARES_COPYBOOK_FIELD", "COPYBOOK", "CARDCOPY", "COPYBOOK_FIELD", "CARDCOPY::CARD-BALANCE")
            ]["pic"],
            "S9(9)V99",
        )

    def test_extensionless_pli_and_assembler_are_classified_and_extracted(self) -> None:
        self.write(
            "sources/pli/CARDAUTH",
            """
CARDAUTH: PROC OPTIONS(MAIN);
   %INCLUDE CARDCOPY;
   EXEC SQL
      SELECT CARD_NO FROM CARD_ACCT WHERE CARD_NO = :CARD_NO
   END-EXEC;
   CALL CARDVAL(CARD_NO);
   READ FILE(INFILE);
   WRITE FILE(OUTFILE);
END CARDAUTH;
""",
        )
        self.write(
            "sources/assembler/CARDASM",
            """
CARDASM  CSECT
CARDDS   DSECT
         COPY CARDAREA
         CALL CARDVAL
         LINK EP=CARDAUTH
         BALR 14,15
         END CARDASM
""",
        )

        scan_mainframe_tree(self.root, self.db, run_id="pli-asm")
        rels = self.relationships("pli-asm")
        members = {
            row["member_name"]: row["artifact_type"]
            for row in self.rows("SELECT member_name, artifact_type FROM source_member WHERE run_id = ?", ("pli-asm",))
        }
        self.assertEqual(members["CARDAUTH"], "PLI")
        self.assertEqual(members["CARDASM"], "ASSEMBLER")
        self.assertIn(("CALLS", "PROGRAM", "CARDAUTH", "PROGRAM", "CARDVAL"), rels)
        self.assertIn(("USES_COPYBOOK", "PROGRAM", "CARDAUTH", "COPYBOOK", "CARDCOPY"), rels)
        self.assertIn(("READS_TABLE", "PROGRAM", "CARDAUTH", "TABLE", "CARD_ACCT"), rels)
        self.assertIn(("READS_FILE", "PROGRAM", "CARDAUTH", "FILE", "INFILE"), rels)
        self.assertIn(("WRITES_FILE", "PROGRAM", "CARDAUTH", "FILE", "OUTFILE"), rels)
        self.assertIn(("DEFINES_ASSEMBLER_DSECT", "PROGRAM", "CARDASM", "ASSEMBLER_DSECT", "CARDDS"), rels)
        self.assertIn(("USES_COPYBOOK", "PROGRAM", "CARDASM", "COPYBOOK", "CARDAREA"), rels)
        self.assertIn(("CALLS", "PROGRAM", "CARDASM", "PROGRAM", "CARDVAL"), rels)
        self.assertIn(("CALLS", "PROGRAM", "CARDASM", "PROGRAM", "CARDAUTH"), rels)
        self.assertIn(("DYNAMIC_CALL", "PROGRAM", "CARDASM", "UNRESOLVED", "DYNAMIC:CARDASM:REGISTER"), rels)


if __name__ == "__main__":
    unittest.main()
