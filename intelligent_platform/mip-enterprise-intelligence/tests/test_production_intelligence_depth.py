from __future__ import annotations

import json
import sqlite3
import tempfile
import unittest
from pathlib import Path

from mip_intel.api import IntelligenceApi
from mip_intel.ingestion import _parse_cobol_hard_timeout_worker, scan_mainframe_tree


class ProductionIntelligenceDepthTests(unittest.TestCase):
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

    def relationships(self, run_id: str = "depth") -> dict[tuple[str, str, str, str, str], dict]:
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

    def test_cobol_data_control_call_and_cics_contracts_are_graph_facts(self) -> None:
        self.write(
            "app/cbl/CARDAUTH",
            """
       IDENTIFICATION DIVISION.
       PROGRAM-ID. CARDAUTH.
       DATA DIVISION.
       WORKING-STORAGE SECTION.
       01 WS-CARD-REC.
          05 WS-CARD-NO PIC X(16).
          05 WS-AUTH-AMT PIC S9(7)V99 COMP-3.
          05 WS-STATUS PIC X VALUE 'N'.
             88 WS-APPROVED VALUE 'A'.
       01 WS-AUTH-TABLE.
          05 WS-AUTH-ENTRY OCCURS 1 TO 10 TIMES DEPENDING ON WS-AUTH-COUNT.
             10 WS-LIMIT PIC S9(7)V99.
       01 WS-OLD-LIMIT REDEFINES WS-LIMIT PIC S9(7)V99.
       LINKAGE SECTION.
       01 LK-REQ.
          05 LK-CARD-NO PIC X(16).
       PROCEDURE DIVISION USING LK-REQ.
       MAIN-PARA.
           MOVE LK-CARD-NO TO WS-CARD-NO.
           PERFORM CHECK-LIMIT.
           CALL 'AUTHSVC' USING WS-CARD-NO WS-AUTH-AMT.
           EXEC CICS LINK PROGRAM('AUTHPGM') COMMAREA(WS-CARD-REC) LENGTH(100) END-EXEC.
           GO TO EXIT-PARA.
       CHECK-LIMIT.
           COMPUTE WS-AUTH-AMT = WS-LIMIT + WS-OLD-LIMIT.
           IF WS-AUTH-AMT > WS-LIMIT DISPLAY 'HIGH'.
       EXIT-PARA.
           GOBACK.
""",
        )

        scan_mainframe_tree(self.root, self.db, run_id="depth")
        rels = self.relationships()

        self.assertIn(
            ("DECLARES_FIELD", "PROGRAM", "CARDAUTH", "FIELD", "CARDAUTH::WS-AUTH-ENTRY"),
            rels,
        )
        occurs_attrs = rels[
            ("DECLARES_FIELD", "PROGRAM", "CARDAUTH", "FIELD", "CARDAUTH::WS-AUTH-ENTRY")
        ]
        self.assertEqual(occurs_attrs["occurs"], 1)
        self.assertEqual(occurs_attrs["occurs_to"], 10)
        self.assertEqual(occurs_attrs["depending_on"], "WS-AUTH-COUNT")

        redefines_attrs = rels[
            ("DECLARES_FIELD", "PROGRAM", "CARDAUTH", "FIELD", "CARDAUTH::WS-OLD-LIMIT")
        ]
        self.assertEqual(redefines_attrs["redefines"], "WS-LIMIT")
        amount_attrs = rels[
            ("DECLARES_FIELD", "PROGRAM", "CARDAUTH", "FIELD", "CARDAUTH::WS-AUTH-AMT")
        ]
        self.assertEqual(amount_attrs["usage"], "COMP-3")

        self.assertIn(
            ("FLOWS_TO", "FIELD", "CARDAUTH::LK-CARD-NO", "FIELD", "CARDAUTH::WS-CARD-NO"),
            rels,
        )
        self.assertIn(
            ("FLOWS_TO", "FIELD", "CARDAUTH::WS-LIMIT", "FIELD", "CARDAUTH::WS-AUTH-AMT"),
            rels,
        )
        self.assertIn(
            ("PERFORMS", "PARAGRAPH", "CARDAUTH::MAIN-PARA", "PARAGRAPH", "CARDAUTH::CHECK-LIMIT"),
            rels,
        )
        self.assertIn(
            ("BRANCHES_TO", "PARAGRAPH", "CARDAUTH::MAIN-PARA", "PARAGRAPH", "CARDAUTH::EXIT-PARA"),
            rels,
        )

        call_attrs = rels[("CALLS", "PROGRAM", "CARDAUTH", "PROGRAM", "AUTHSVC")]
        self.assertEqual(call_attrs["using"], ["WS-CARD-NO", "WS-AUTH-AMT"])
        self.assertEqual(call_attrs["interface_contract"]["contract_status"], "observed")

        cics_attrs = rels[("CALLS", "PROGRAM", "CARDAUTH", "PROGRAM", "AUTHPGM")]
        self.assertEqual(cics_attrs["data_contract"]["commarea"], "WS-CARD-REC")
        self.assertEqual(cics_attrs["data_contract"]["length"], "100")

        program_attrs = json.loads(
            self.rows(
                "SELECT attributes_json FROM asset WHERE run_id = ? AND technical_name = ?",
                ("depth", "CARDAUTH"),
            )[0]["attributes_json"]
        )
        linkage_names = {row["name"] for row in program_attrs["linkage_contract"]}
        self.assertIn("LK-CARD-NO", linkage_names)
        self.assertTrue(program_attrs["business_rules"])
        self.assertTrue(program_attrs["business_rules"][0]["source_evidence"].startswith("app/cbl/CARDAUTH:"))

        api = IntelligenceApi(self.db)
        dependency = api.dependency_graph("CARDAUTH", "depth", direction="both", depth=4, limit=500)
        self.assertIn("FLOWS_TO", {edge["type"] for edge in dependency["edges"]})
        self.assertIn("PERFORMS", {edge["type"] for edge in dependency["edges"]})
        profile = api.node("CARDAUTH", "depth")
        coverage = {check["name"]: check["status"] for check in profile["coverage_report"]["checks"]}
        self.assertEqual(coverage["data_dictionary"], "captured")
        self.assertEqual(coverage["field_lineage"], "captured")
        self.assertEqual(coverage["control_flow"], "captured")
        self.assertEqual(coverage["call_contracts"], "captured")
        coverage_payload = api.coverage("CARDAUTH", "depth")
        self.assertEqual(coverage_payload["asset"]["technical_name"], "CARDAUTH")

    def test_jcl_step_level_execution_and_dataset_edges_are_persisted(self) -> None:
        self.write(
            "app/jcl/CARDAILY",
            """
//CARDAILY JOB (ACCT),'CARD AUTH'
//AUTHSTEP EXEC PGM=CARDAUTH
//INFILE   DD DSN=CARD.AUTH.IN,DISP=SHR
//OUTFILE  DD DSN=CARD.AUTH.OUT,DISP=(NEW,CATLG,DELETE)
""",
        )

        scan_mainframe_tree(self.root, self.db, run_id="jcl-depth")
        rels = self.relationships("jcl-depth")

        self.assertIn(
            ("CONTAINS_STEP", "JOB", "CARDAILY", "JOB_STEP", "CARDAILY::AUTHSTEP"),
            rels,
        )
        self.assertIn(
            ("EXECUTES", "JOB_STEP", "CARDAILY::AUTHSTEP", "PROGRAM", "CARDAUTH"),
            rels,
        )
        read_attrs = rels[
            ("READS_DATASET", "JOB_STEP", "CARDAILY::AUTHSTEP", "DATASET", "CARD.AUTH.IN")
        ]
        self.assertEqual(read_attrs["dd_name"], "INFILE")
        self.assertEqual(read_attrs["disp"], "SHR")
        write_attrs = rels[
            ("WRITES_DATASET", "JOB_STEP", "CARDAILY::AUTHSTEP", "DATASET", "CARD.AUTH.OUT")
        ]
        self.assertEqual(write_attrs["dd_name"], "OUTFILE")
        self.assertTrue(write_attrs["disp"].startswith("NEW"))

    def test_parallel_process_parser_path_and_hard_timeout_are_quarantined(self) -> None:
        self.write(
            "app/cbl/ACCT001",
            """
       IDENTIFICATION DIVISION.
       PROGRAM-ID. ACCT001.
       PROCEDURE DIVISION.
           STOP RUN.
""",
        )
        self.write(
            "app/cbl/ACCT002",
            """
       IDENTIFICATION DIVISION.
       PROGRAM-ID. ACCT002.
       PROCEDURE DIVISION.
           STOP RUN.
""",
        )

        scan_mainframe_tree(self.root, self.db, run_id="process", config={"max_workers": 2})
        parsers = [
            json.loads(row["attributes_json"])["parser"]
            for row in self.rows(
                "SELECT attributes_json FROM asset WHERE run_id = ? AND asset_type = 'PROGRAM'",
                ("process",),
            )
        ]
        self.assertEqual({parser.get("parallel_backend") for parser in parsers}, {"process"})

        payload, issue = _parse_cobol_hard_timeout_worker(
            "       IDENTIFICATION DIVISION.\n       PROGRAM-ID. T.\n       PROCEDURE DIVISION.\n           STOP RUN.\n",
            None,
            0.000001,
        )
        self.assertIsNotNone(issue)
        self.assertEqual(issue["error_type"], "HardParseTimeoutExceeded")
        self.assertTrue(payload["parser"]["hard_timeout_exceeded"])


if __name__ == "__main__":
    unittest.main()
