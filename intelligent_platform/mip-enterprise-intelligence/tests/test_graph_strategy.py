from __future__ import annotations

import unittest
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from demo_fixture import demo_context


class GraphStrategyTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        context = demo_context()
        cls.db = context["db"]
        cls.api = context["api"]
        cls.run_id = context["run_id"]

    def root_asset_id(self) -> str:
        roots = self.api.roots()["roots"]
        self.assertTrue(roots)
        return roots[0]["asset_id"]

    def test_demo_persists_sqlite_facts_and_summaries(self) -> None:
        stats = self.api.stats()
        self.assertEqual(stats["run"]["status"], "COMPLETED")
        self.assertGreaterEqual(stats["assets"]["PROGRAM"], 3)
        self.assertGreaterEqual(stats["relationships"]["CALLS"], 2)
        roots = self.api.roots()["roots"]
        self.assertEqual(roots[0]["technical_name"], "CRDPOST")
        self.assertGreaterEqual(roots[0]["reachable_assets"], 5)

    def test_graph_slice_is_bounded_and_cached(self) -> None:
        root = self.root_asset_id()
        first = self.api.graph_slice(root, depth=8, limit=3)
        self.assertLessEqual(len(first["nodes"]), 3)
        self.assertTrue(first["truncated"])
        self.assertFalse(first["cached"])
        second = self.api.graph_slice(root, depth=8, limit=3)
        self.assertTrue(second["cached"])

    def test_graph_slice_keeps_needs_review_edges_visible(self) -> None:
        root = self.root_asset_id()
        payload = self.api.graph_slice(root, depth=2, limit=50)
        statuses = {edge["validation_status"] for edge in payload["edges"]}
        self.assertIn("needs_review", statuses)
        self.assertGreaterEqual(payload["stats"]["needs_review_edges"], 1)

    def test_node_and_edge_profiles_include_evidence(self) -> None:
        root = self.root_asset_id()
        node = self.api.node(root)
        self.assertEqual(node["asset"]["technical_name"], "CRDPOST")
        self.assertTrue(node["evidence"])
        edge_id = self.api.graph_slice(root, depth=1, limit=20)["edges"][0]["id"]
        edge = self.api.edge(edge_id)
        self.assertTrue(edge["evidence"])
        self.assertIn("relationship", edge)

    def test_search_and_heatmap_support_non_graph_navigation(self) -> None:
        results = self.api.search("CARD")["results"]
        self.assertTrue(results)
        heatmap = self.api.heatmap("PROGRAM", "COPYBOOK", "USES_COPYBOOK")
        self.assertGreaterEqual(len(heatmap["cells"]), 1)


if __name__ == "__main__":
    unittest.main()
