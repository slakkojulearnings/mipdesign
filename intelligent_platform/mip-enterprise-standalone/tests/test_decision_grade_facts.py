from __future__ import annotations

import json
import sqlite3
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from mip_intel.api import IntelligenceApi
from mip_intel.ingestion import COPYBOOK_SITE_FIELD_LIMIT, DATA_DICTIONARY_GRAPH_LIMIT, scan_mainframe_tree


class DecisionGradeFactTests(unittest.TestCase):
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

    def relationships(self, run_id: str) -> dict[tuple[str, str, str, str, str], list[dict]]:
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
        rels: dict[tuple[str, str, str, str, str], list[dict]] = {}
        for row in rows:
            key = (
                row["relationship_type"],
                row["source_type"],
                row["source_name"],
                row["target_type"],
                row["target_name"],
            )
            rels.setdefault(key, []).append(json.loads(row["attributes_json"]))
        return rels

    def seed_estate(self) -> None:
        self.write(
            "copylib/CARDCPY",
            """
       01 CARD-REC.
          05 CARD-NO PIC X(16).
          05 CARD-AMT PIC S9(7)V99 COMP-3.
""",
        )
        self.write(
            "app/cbl/AUTHSVC",
            """
       IDENTIFICATION DIVISION.
       PROGRAM-ID. AUTHSVC.
       DATA DIVISION.
       LINKAGE SECTION.
       01 LK-REQ.
          05 LK-CARD-NO PIC X(16).
          05 LK-AMT PIC S9(7)V99 COMP-3.
       PROCEDURE DIVISION USING LK-REQ.
           GOBACK.
""",
        )
        self.write(
            "app/cbl/CALLER",
            """
       IDENTIFICATION DIVISION.
       PROGRAM-ID. CALLER.
       DATA DIVISION.
       WORKING-STORAGE SECTION.
           COPY CARDCPY REPLACING ==CARD== BY ==AUTH==.
       01 WS-RESP PIC S9(8) COMP.
       PROCEDURE DIVISION.
       MAIN-PARA.
           CALL 'AUTHSVC'
                USING AUTH-REC WS-RESP.
           EXEC CICS LINK PROGRAM('AUTHPGM')
                COMMAREA(AUTH-REC)
                LENGTH(100)
                RESP(WS-RESP)
           END-EXEC.
           GOBACK.
""",
        )
        self.write(
            "app/jcl/AUTHJOB",
            """
//AUTHJOB JOB (ACCT),'AUTH JOB'
//STEP1   EXEC PGM=CALLER
//OUT     DD DSN=CARD.AUTH.OUT(+1),DISP=(NEW,CATLG,DELETE)
//IN      DD DSN=CARD.AUTH.OUT(0),DISP=SHR
""",
        )

    def test_contract_layout_commarea_and_dataset_identity_are_persisted(self) -> None:
        self.seed_estate()
        scan_mainframe_tree(self.root, self.db, run_id="decision")
        rels = self.relationships("decision")

        self.assertTrue(any(key[0] == "HAS_COPY_SITE" and key[2] == "CALLER" for key in rels))
        self.assertTrue(any(key[0] == "COPY_SITE_DECLARES_FIELD" and key[4] == "CALLER::AUTH-NO" for key in rels))
        self.assertTrue(
            any(
                key[0] == "MATERIALIZES_COPYBOOK_FIELD"
                and key[2] == "CALLER::AUTH-NO"
                and key[4] == "CARDCPY::CARD-NO"
                for key in rels
            )
        )

        self.assertTrue(any(key[0] == "DECLARES_ENTRY_CONTRACT" and key[2] == "AUTHSVC" for key in rels))
        self.assertTrue(any(key[0] == "DEFINES_CALL_CONTRACT" and key[2] == "CALLER" for key in rels))
        self.assertTrue(any(key[0] == "CALL_PASSES_FIELD" and key[4] == "CALLER::AUTH-REC" for key in rels))
        self.assertTrue(
            any(
                key[0] == "CALL_ARGUMENT_MAPS_TO_LINKAGE"
                and key[2] == "CALLER::AUTH-REC"
                and key[4] == "AUTHSVC::LK-REQ"
                for key in rels
            )
        )

        self.assertTrue(any(key[0] == "DEFINES_COMMAREA_CONTRACT" and key[2] == "CALLER" for key in rels))
        self.assertTrue(any(key[0] == "COMMAREA_CONTAINS_FIELD" and key[4] == "CALLER::AUTH-NO" for key in rels))

        self.assertTrue(
            any(
                key[0] == "NORMALIZES_TO_DATASET_IDENTITY"
                and key[3] == "DATASET_IDENTITY"
                and key[4] == "CARD.AUTH.OUT"
                for key in rels
            )
        )
        self.assertTrue(any(key[0] == "WRITES_DATASET_IDENTITY" and key[4] == "CARD.AUTH.OUT" for key in rels))
        self.assertTrue(any(key[0] == "READS_DATASET_IDENTITY" and key[4] == "CARD.AUTH.OUT" for key in rels))

        api = IntelligenceApi(self.db)
        coverage = {row["name"]: row["status"] for row in api.coverage("CALLER", "decision")["coverage_report"]["checks"]}
        self.assertEqual(coverage["bounded_copybook_layout"], "captured")
        self.assertEqual(coverage["interface_contract_model"], "captured")
        self.assertEqual(coverage["commarea_contracts"], "captured")
        job_coverage = {row["name"]: row["status"] for row in api.coverage("AUTHJOB", "decision")["coverage_report"]["checks"]}
        self.assertEqual(job_coverage["dataset_identity"], "captured")

    def test_copybook_site_and_data_dictionary_projection_are_bounded(self) -> None:
        fields = "\n".join(f"          05 BIG-F{index:03d} PIC X(10)." for index in range(1, 401))
        self.write(
            "copylib/BIGCPY",
            f"""
       01 BIG-REC.
{fields}
""",
        )
        self.write(
            "app/cbl/BOUND",
            """
       IDENTIFICATION DIVISION.
       PROGRAM-ID. BOUND.
       DATA DIVISION.
       WORKING-STORAGE SECTION.
           COPY BIGCPY.
       01 WS-OUT PIC X(10).
       PROCEDURE DIVISION.
           MOVE BIG-F150 TO WS-OUT.
           GOBACK.
""",
        )

        scan_mainframe_tree(self.root, self.db, run_id="bounded")

        copy_site_count = self.rows(
            "SELECT COUNT(*) AS count FROM relationship WHERE run_id = ? AND relationship_type = 'COPY_SITE_DECLARES_FIELD'",
            ("bounded",),
        )[0]["count"]
        field_count = self.rows(
            "SELECT COUNT(*) AS count FROM relationship WHERE run_id = ? AND relationship_type = 'DECLARES_FIELD'",
            ("bounded",),
        )[0]["count"]
        self.assertLessEqual(copy_site_count, COPYBOOK_SITE_FIELD_LIMIT)
        self.assertLessEqual(field_count, DATA_DICTIONARY_GRAPH_LIMIT)
        used_field = self.rows(
            """
            SELECT 1
            FROM relationship r
            JOIN asset t ON t.asset_id = r.target_asset_id
            WHERE r.run_id = ?
              AND r.relationship_type IN ('COPY_SITE_DECLARES_FIELD', 'DECLARES_FIELD')
              AND t.technical_name = 'BOUND::BIG-F150'
            LIMIT 1
            """,
            ("bounded",),
        )
        self.assertTrue(used_field)


if __name__ == "__main__":
    unittest.main()
