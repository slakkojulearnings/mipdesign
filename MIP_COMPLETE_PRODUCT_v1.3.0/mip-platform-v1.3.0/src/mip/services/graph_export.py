from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from mip.graph import KnowledgeGraph
from mip.persistence import SQLiteRepository


class GraphExporter:
    def __init__(self, repository: SQLiteRepository) -> None:
        self.repository = repository

    def export(self, output_dir: Path, run_id: str | None = None) -> dict[str, str]:
        output_dir.mkdir(parents=True, exist_ok=True)
        graph = KnowledgeGraph(self.repository, run_id)
        nodes: list[dict[str, Any]] = []
        for node_id, data in graph.graph.nodes(data=True):
            nodes.append({"id": node_id, **dict(data)})
        edges: list[dict[str, Any]] = []
        for source, target, key, data in graph.graph.edges(keys=True, data=True):
            edges.append({"id": key, "source": source, "target": target, **dict(data)})

        json_path = output_dir / "knowledge-graph.json"
        json_path.write_text(
            json.dumps({"nodes": nodes, "edges": edges}, indent=2, default=str),
            encoding="utf-8",
        )

        mermaid_path = output_dir / "knowledge-graph.mmd"
        mermaid_path.write_text(self._mermaid(nodes, edges), encoding="utf-8")
        return {"json": str(json_path), "mermaid": str(mermaid_path)}

    @staticmethod
    def _mermaid(nodes: list[dict[str, Any]], edges: list[dict[str, Any]]) -> str:
        lines = ["flowchart LR"]
        node_names: dict[str, str] = {}
        for index, node in enumerate(nodes):
            alias = f"N{index}"
            node_names[str(node["id"])] = alias
            label = f"{node.get('asset_type', '')}: {node.get('technical_name', '')}"
            safe = label.replace('"', "'")
            lines.append(f'  {alias}["{safe}"]')
        for edge in edges:
            source = node_names.get(str(edge["source"]))
            target = node_names.get(str(edge["target"]))
            if not source or not target:
                continue
            label = str(edge.get("relationship_type", "")).replace('"', "'")
            lines.append(f'  {source} -->|"{label}"| {target}')
        return "\n".join(lines) + "\n"
