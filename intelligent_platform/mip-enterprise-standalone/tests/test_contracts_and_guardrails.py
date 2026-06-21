from __future__ import annotations

import contextlib
import io
import json
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from mip_intel.api import IntelligenceApi
from mip_intel.cli import main
from mip_intel.models import Asset, Evidence, GraphSliceRequest, Relationship, SourceMember, stable_id
from mip_intel.repositories import SQLiteGraphRepository
from demo_fixture import demo_context


class GraphSliceGuardrailTests(unittest.TestCase):
    def test_request_normalization_clamps_scale_and_filters(self) -> None:
        request = GraphSliceRequest(
            run_id="run-1",
            root_asset_id="asset-1",
            mode="NEIGHBORHOOD",
            depth=99,
            limit=250_000,
            relationship_types=("calls", "CALLS", "uses_copybook", ""),
            confidence_min=-2.0,
        )

        normalized = request.normalized()

        self.assertEqual(normalized.mode, "neighborhood")
        self.assertEqual(normalized.depth, 8)
        self.assertEqual(normalized.limit, 1500)
        self.assertEqual(normalized.relationship_types, ("CALLS", "USES_COPYBOOK"))
        self.assertEqual(normalized.confidence_min, 0.0)
        self.assertEqual(request.cache_key, normalized.cache_key)

    def test_request_normalization_enforces_minimum_slice_size(self) -> None:
        normalized = GraphSliceRequest(
            run_id="run-1",
            root_asset_id="asset-1",
            depth=-3,
            limit=0,
            confidence_min=4.0,
        ).normalized()

        self.assertEqual(normalized.depth, 0)
        self.assertEqual(normalized.limit, 1)
        self.assertEqual(normalized.confidence_min, 1.0)


class RepositoryEvidenceEnvelopeTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.db = Path(self.tmp.name) / "contracts.db"
        self.repo = SQLiteGraphRepository(self.db)
        self.run_id = self.repo.create_run("test://contracts", run_id="contract-run")

    def tearDown(self) -> None:
        self.tmp.cleanup()

    def test_extensionless_source_members_keep_classification_evidence(self) -> None:
        member = SourceMember(
            run_id=self.run_id,
            relative_path="COBOL/CRDPOST",
            folder_path="COBOL",
            member_name="CRDPOST",
            sha256=stable_id("sha", "COBOL/CRDPOST"),
            size_bytes=128,
            encoding="utf-8",
            is_binary=False,
            text_status="TEXT",
            artifact_type="COBOL",
            classification_basis="content-signature:IDENTIFICATION DIVISION",
            confidence=0.97,
            validation_status="confirmed",
        )

        member_id = self.repo.upsert_member(member)
        asset_id = self.repo.upsert_asset(
            Asset(
                run_id=self.run_id,
                asset_type="PROGRAM",
                technical_name="CRDPOST",
                member_id=member_id,
                folder_path="COBOL",
            )
        )

        asset = self.repo.get_asset(asset_id)

        self.assertIsNotNone(asset)
        self.assertEqual(asset["relative_path"], "COBOL/CRDPOST")
        self.assertEqual(asset["classification_basis"], "content-signature:IDENTIFICATION DIVISION")
        self.assertEqual(asset["text_status"], "TEXT")
        self.assertNotIn(".", asset["relative_path"])

    def test_unknown_extensionless_members_are_counted_without_fabricating_type(self) -> None:
        member = SourceMember(
            run_id=self.run_id,
            relative_path="MISC/NO_HINT",
            folder_path="MISC",
            member_name="NO_HINT",
            sha256=stable_id("sha", "MISC/NO_HINT"),
            size_bytes=64,
            encoding="utf-8",
            is_binary=False,
            text_status="TEXT",
            artifact_type="UNKNOWN_TEXT",
            classification_basis="extensionless-no-signature",
            confidence=0.2,
            validation_status="needs_review",
        )

        self.repo.upsert_member(member)
        self.repo.complete_run(self.run_id)
        stats = self.repo.stats(self.run_id)

        self.assertEqual(stats["run"]["unknown_count"], 1)
        self.assertEqual(stats["run"]["binary_count"], 0)

    def test_relationship_profile_preserves_evidence_envelope(self) -> None:
        source = self.repo.upsert_asset(Asset(self.run_id, "PROGRAM", "CRDPOST"))
        target = self.repo.upsert_asset(Asset(self.run_id, "PROGRAM", "WS-RATE-PGM"))
        relationship = Relationship(
            run_id=self.run_id,
            relationship_type="DYNAMIC_CALL",
            source_asset_id=source,
            target_asset_id=target,
            confidence=0.35,
            validation_status="needs_review",
            discovery_method="static-inference",
        )
        relationship_id = self.repo.insert_relationship(
            relationship,
            [
                Evidence(
                    source_path="COBOL/CRDPOST",
                    line_start=42,
                    line_end=42,
                    evidence_text="CALL WS-RATE-PGM",
                    extractor="test-parser",
                    discovery_method="static-inference",
                    confidence=0.35,
                    validation_status="needs_review",
                )
            ],
        )

        evidence = self.repo.evidence_for(self.run_id, "RELATIONSHIP", relationship_id)

        self.assertEqual(len(evidence), 1)
        self.assertEqual(evidence[0]["entity_kind"], "RELATIONSHIP")
        self.assertEqual(evidence[0]["source_path"], "COBOL/CRDPOST")
        self.assertEqual(evidence[0]["line_start"], 42)
        self.assertEqual(evidence[0]["extractor"], "test-parser")
        self.assertEqual(evidence[0]["discovery_method"], "static-inference")
        self.assertEqual(evidence[0]["confidence"], 0.35)
        self.assertEqual(evidence[0]["validation_status"], "needs_review")


class ApiAndCliContractTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        context = demo_context()
        cls.db = context["db"]
        cls.api = context["api"]
        cls.run_id = context["run_id"]

    def test_api_graph_slice_contract_honors_filters_and_limits(self) -> None:
        root = self.api.roots()["roots"][0]["asset_id"]

        payload = self.api.graph_slice(
            root,
            depth=99,
            limit=250_000,
            relationship_types=("dynamic_call",),
            confidence_min=0.3,
        )

        self.assertEqual(payload["depth"], 8)
        self.assertEqual(payload["limit"], 1500)
        self.assertLessEqual(len(payload["nodes"]), 1500)
        self.assertTrue(payload["edges"])
        self.assertEqual({edge["type"] for edge in payload["edges"]}, {"DYNAMIC_CALL"})
        self.assertTrue(all(edge["confidence"] >= 0.3 for edge in payload["edges"]))

    def test_api_search_caps_limit_and_normalizes_offset(self) -> None:
        result = self.api.search("card", limit=10_000, offset=-7)

        self.assertEqual(result["limit"], 200)
        self.assertEqual(result["offset"], 0)
        self.assertLessEqual(len(result["results"]), 200)
        self.assertTrue(result["results"])

    def test_cli_writes_json_for_demo_and_stats(self) -> None:
        stdout = io.StringIO()
        with contextlib.redirect_stdout(stdout):
            exit_code = main(["--db", str(self.db), "stats"])

        payload = json.loads(stdout.getvalue())

        self.assertEqual(exit_code, 0)
        self.assertEqual(payload["run"]["status"], "COMPLETED")
        self.assertIn("PROGRAM", payload["assets"])

    def test_cli_graph_slice_uses_global_db_before_subcommand(self) -> None:
        root = self.api.roots()["roots"][0]["asset_id"]
        stdout = io.StringIO()

        with contextlib.redirect_stdout(stdout):
            exit_code = main(
                [
                    "--db",
                    str(self.db),
                    "graph-slice",
                    "--root",
                    root,
                    "--depth",
                    "2",
                    "--limit",
                    "3",
                ]
            )

        payload = json.loads(stdout.getvalue())

        self.assertEqual(exit_code, 0)
        self.assertLessEqual(len(payload["nodes"]), 3)
        self.assertTrue(payload["truncated"])


if __name__ == "__main__":
    unittest.main()
