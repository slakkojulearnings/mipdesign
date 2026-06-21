from __future__ import annotations

import json
import sqlite3
import tempfile
import unittest
import contextlib
import io
from pathlib import Path
from unittest.mock import patch

from mip_intel.api import IntelligenceApi
from mip_intel.cli import main
from mip_intel.ingestion import scan_mainframe_tree


class Phase1ScanReliabilityTests(unittest.TestCase):
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

    def test_progress_config_and_parse_cache_metrics_are_persisted(self) -> None:
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

        first = scan_mainframe_tree(
            self.root,
            self.db,
            run_id="phase1",
            config={"batch_size": 1, "max_workers": 2, "parse_timeout_seconds": 60},
        )
        second = scan_mainframe_tree(
            self.root,
            self.db,
            run_id="phase1",
            config={"batch_size": 1, "max_workers": 2, "parse_timeout_seconds": 60},
        )

        self.assertEqual(first["parse_metrics"]["parsed_files"], 2)
        self.assertEqual(second["parse_metrics"]["cached_parse_hits"], 2)

        progress = {
            row["phase"]: row
            for row in self.rows("SELECT * FROM scan_progress WHERE run_id = ?", ("phase1",))
        }
        self.assertIn("DISCOVERING", progress)
        self.assertIn("PARSING", progress)
        self.assertIn("VALIDATING", progress)
        self.assertIn("COMPLETED", progress)
        self.assertEqual(progress["COMPLETED"]["parsed_files"], 2)
        self.assertEqual(progress["COMPLETED"]["cached_parse_hits"], 2)
        self.assertEqual(json.loads(progress["PARSING"]["details_json"])["max_workers"], 2)
        self.assertEqual(json.loads(progress["VALIDATING"]["details_json"])["status"], "passed")

        run = self.rows("SELECT * FROM run_manifest WHERE run_id = ?", ("phase1",))[0]
        self.assertEqual(run["status"], "COMPLETED")
        self.assertEqual(json.loads(run["config_json"])["batch_size"], 1)

    def test_parse_failure_is_quarantined_and_scan_completes(self) -> None:
        self.write(
            "app/cbl/BADPARSE",
            """
       IDENTIFICATION DIVISION.
       PROGRAM-ID. BADPARSE.
       PROCEDURE DIVISION.
           STOP RUN.
""",
        )

        with patch("mip_intel.ingestion.parse_cobol", side_effect=RuntimeError("boom")):
            result = scan_mainframe_tree(self.root, self.db, run_id="badparse")

        self.assertEqual(result["run_id"], "badparse")
        self.assertEqual(result["parse_metrics"]["failed_files"], 1)
        self.assertEqual(result["issue_count"], 1)

        issue = self.rows("SELECT * FROM scan_issue WHERE run_id = ?", ("badparse",))[0]
        self.assertEqual(issue["stage"], "PARSE")
        self.assertEqual(issue["severity"], "ERROR")
        self.assertEqual(issue["error_type"], "RuntimeError")

        attrs = json.loads(
            self.rows(
                "SELECT attributes_json FROM asset WHERE run_id = ? AND technical_name = ?",
                ("badparse", "BADPARSE"),
            )[0]["attributes_json"]
        )
        self.assertEqual(attrs["parser"]["effective"], "parse-error")
        self.assertEqual(attrs["parser"]["validation_status"], "needs_review")

        validation = IntelligenceApi(self.db).validate("badparse")
        self.assertEqual(validation["status"], "passed")
        self.assertGreaterEqual(validation["stats"]["run"]["warning_count"], 1)

    def test_api_analyze_passes_config_to_scanner(self) -> None:
        self.write(
            "app/cbl/API001",
            """
       IDENTIFICATION DIVISION.
       PROGRAM-ID. API001.
       PROCEDURE DIVISION.
           STOP RUN.
""",
        )

        api = IntelligenceApi(self.db)
        result = api.analyze(
            self.root,
            config={"run_id": "api-config", "batch_size": 2, "resume": True},
        )

        self.assertEqual(result["run_id"], "api-config")
        run = self.rows("SELECT config_json FROM run_manifest WHERE run_id = ?", ("api-config",))[0]
        config = json.loads(run["config_json"])
        self.assertEqual(config["batch_size"], 2)
        self.assertTrue(config["resume"])
        self.assertIn(".git", config["exclude_dirs"])

    def test_git_directory_is_excluded_from_discovery(self) -> None:
        self.write(
            "app/cbl/REAL001",
            """
       IDENTIFICATION DIVISION.
       PROGRAM-ID. REAL001.
       PROCEDURE DIVISION.
           STOP RUN.
""",
        )
        self.write(
            ".git/objects/FAKE001",
            """
       IDENTIFICATION DIVISION.
       PROGRAM-ID. FAKE001.
       PROCEDURE DIVISION.
           STOP RUN.
""",
        )

        result = scan_mainframe_tree(self.root, self.db, run_id="exclude-git")

        self.assertEqual(result["file_count"], 1)
        self.assertEqual(self.rows("SELECT COUNT(*) c FROM source_member WHERE run_id = ?", ("exclude-git",))[0]["c"], 1)
        self.assertFalse(IntelligenceApi(self.db).search("FAKE001", "exclude-git")["results"])
        progress = {
            row["phase"]: json.loads(row["details_json"])
            for row in self.rows("SELECT phase, details_json FROM scan_progress WHERE run_id = ?", ("exclude-git",))
        }
        self.assertGreaterEqual(progress["DISCOVERING"]["skipped_directory_count"], 1)
        self.assertIn(".git", progress["DISCOVERING"]["excluded_dirs"])

    def test_cli_accepts_relaxed_config_for_powershell_usage(self) -> None:
        self.write(
            "app/cbl/CLI001",
            """
       IDENTIFICATION DIVISION.
       PROGRAM-ID. CLI001.
       PROCEDURE DIVISION.
           STOP RUN.
""",
        )

        stdout = io.StringIO()
        with contextlib.redirect_stdout(stdout):
            exit_code = main(
                [
                    "--db",
                    str(self.db),
                    "analyze",
                    str(self.root),
                    "--config",
                    "{run_id:cli-relaxed,batch_size:1,max_workers:2}",
                ]
            )

        payload = json.loads(stdout.getvalue())
        self.assertEqual(exit_code, 0)
        self.assertEqual(payload["run_id"], "cli-relaxed")
        run = self.rows("SELECT config_json FROM run_manifest WHERE run_id = ?", ("cli-relaxed",))[0]
        config = json.loads(run["config_json"])
        self.assertEqual(config["batch_size"], 1)
        self.assertEqual(config["max_workers"], 2)


if __name__ == "__main__":
    unittest.main()
