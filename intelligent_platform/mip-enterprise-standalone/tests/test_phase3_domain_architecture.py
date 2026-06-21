from __future__ import annotations

import contextlib
import io
import json
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from demo_fixture import demo_context
from mip_intel.cli import main


class Phase3DomainArchitectureTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        context = demo_context()
        cls.db = context["db"]
        cls.api = context["api"]
        cls.run_id = context["run_id"]

    def test_bounded_contexts_are_graph_derived_and_evidence_backed(self) -> None:
        payload = self.api.domain_contexts(self.run_id)

        self.assertEqual(payload["run_id"], self.run_id)
        self.assertTrue(payload["contexts"])
        context = payload["contexts"][0]
        self.assertEqual(context["membership_method"], "graph_cluster_read_model")
        self.assertFalse(context["llm_membership_used"])
        self.assertTrue(context["confidence"] > 0)
        self.assertIn(context["validation_status"], {"confirmed", "inferred", "needs_review"})
        self.assertTrue(context["aggregate_candidates"])
        self.assertTrue(any(item["source"] == "WRITES_TABLE" for item in context["aggregate_candidates"]))
        self.assertTrue(context["evidence"]["sample_assets"])
        self.assertIn("hypothesis", context["feedback_loop"])
        self.assertIn("quality_gates", context["feedback_loop"])

    def test_service_candidates_include_modernization_contracts(self) -> None:
        payload = self.api.service_candidates(self.run_id)

        self.assertTrue(payload["service_candidates"])
        service = payload["service_candidates"][0]
        self.assertTrue(service["java_service_candidate"].endswith("Service"))
        self.assertTrue(service["api_candidates"])
        self.assertTrue(service["data_contracts"])
        self.assertEqual(service["decision_status"], "candidate")
        self.assertTrue(service["evidence"]["citations"])
        self.assertIn("dual_run_reconciliation", service["feedback_loop"]["quality_gates"])

    def test_modernization_roadmap_sequences_contexts_with_feedback_gates(self) -> None:
        payload = self.api.modernization_roadmap(self.run_id)

        self.assertTrue(payload["work_packages"])
        package = payload["work_packages"][0]
        self.assertEqual(package["sequence"], 1)
        self.assertTrue(package["bounded_context"])
        self.assertTrue(package["steps"])
        self.assertIn("strangler_facade", {step["kind"] for step in package["steps"]})
        self.assertIn("rollback_signal", package["feedback_loop"])
        self.assertTrue(package["evidence"]["citations"])

    def test_cli_domain_architecture_commands_emit_json(self) -> None:
        stdout = io.StringIO()
        with contextlib.redirect_stdout(stdout):
            exit_code = main(["--db", str(self.db), "service-candidates", "--run-id", self.run_id, "--limit", "5"])

        payload = json.loads(stdout.getvalue())

        self.assertEqual(exit_code, 0)
        self.assertEqual(payload["run_id"], self.run_id)
        self.assertTrue(payload["service_candidates"])


if __name__ == "__main__":
    unittest.main()
