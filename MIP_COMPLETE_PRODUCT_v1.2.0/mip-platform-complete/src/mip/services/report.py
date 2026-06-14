from __future__ import annotations

import json
from html import escape
from pathlib import Path
from typing import Any

from mip.graph import KnowledgeGraph
from mip.persistence import SQLiteRepository


class ReportGenerator:
    def __init__(self, repository: SQLiteRepository) -> None:
        self.repository = repository

    def generate(self, output_dir: Path, run_id: str | None = None) -> Path:
        output_dir.mkdir(parents=True, exist_ok=True)
        selected = run_id or self.repository.latest_run_id()
        if selected is None:
            raise ValueError("no analysis run available")
        stats = self.repository.stats(selected)
        graph_metrics = KnowledgeGraph(self.repository, selected).metrics()
        issues = self.repository.parse_issues(selected)
        payload = {"statistics": stats, "graph": graph_metrics, "issues": issues}
        (output_dir / "summary.json").write_text(
            json.dumps(payload, indent=2, default=str), encoding="utf-8"
        )
        html_path = output_dir / "report.html"
        html_path.write_text(self._html(payload), encoding="utf-8")
        return html_path

    def _html(self, payload: dict[str, Any]) -> str:
        stats = payload["statistics"]
        run = stats["run"] or {}
        return f"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>MIP Analysis Report</title>
<style>
body{{font-family:system-ui,sans-serif;max-width:1200px;margin:2rem auto;padding:0 1rem;color:#202124}}
h1,h2{{color:#143b63}} .cards{{display:grid;grid-template-columns:repeat(auto-fit,minmax(180px,1fr));gap:1rem}}
.card{{border:1px solid #ddd;border-radius:10px;padding:1rem}} table{{border-collapse:collapse;width:100%;margin-bottom:2rem}}
th,td{{border:1px solid #ddd;text-align:left;padding:.5rem}} th{{background:#f5f7fa}} code{{background:#f1f3f4;padding:.1rem .3rem}}
</style>
</head><body>
<h1>Mainframe Intelligence Platform — Analysis Report</h1>
<p><strong>Run:</strong> <code>{escape(str(run.get("id", "")))}</code><br>
<strong>Source:</strong> {escape(str(run.get("source_root", "")))}<br>
<strong>Status:</strong> {escape(str(run.get("status", "")))}</p>
<div class="cards">
{self._card("Files", run.get("file_count", 0))}
{self._card("Parsed", run.get("parsed_count", 0))}
{self._card("Unknown/Binary", run.get("unknown_count", 0))}
{self._card("Assets", run.get("asset_count", 0))}
{self._card("Relationships", run.get("relationship_count", 0))}
{self._card("Issues", run.get("issue_count", 0))}
</div>
<h2>Assets</h2>{self._mapping_table(stats["assets"])}
<h2>Source Files</h2>{self._mapping_table(stats["files"])}
<h2>Relationships</h2>{self._mapping_table(stats["relationships"])}
<h2>Graph</h2>{self._mapping_table({k: v for k, v in payload["graph"].items() if k != "top_degree"})}
<h2>Top Connected Assets</h2>{self._asset_table(payload["graph"].get("top_degree", []))}
<h2>Parser Issues</h2>{self._issue_table(payload["issues"])}
</body></html>"""

    @staticmethod
    def _card(label: str, value: Any) -> str:
        return f'<div class="card"><strong>{escape(label)}</strong><div style="font-size:2rem">{escape(str(value))}</div></div>'

    @staticmethod
    def _mapping_table(data: dict[str, Any]) -> str:
        rows = "".join(
            f"<tr><td>{escape(str(key))}</td><td>{escape(str(value))}</td></tr>"
            for key, value in data.items()
        )
        return f"<table><thead><tr><th>Type</th><th>Count / Value</th></tr></thead><tbody>{rows}</tbody></table>"

    @staticmethod
    def _asset_table(items: list[dict[str, Any]]) -> str:
        rows = "".join(
            f"<tr><td>{escape(str(item.get('asset_type', '')))}</td><td>{escape(str(item.get('technical_name', '')))}</td><td>{float(item.get('degree_centrality', 0)):.4f}</td></tr>"
            for item in items
        )
        return f"<table><thead><tr><th>Type</th><th>Name</th><th>Degree centrality</th></tr></thead><tbody>{rows}</tbody></table>"

    @staticmethod
    def _issue_table(items: list[dict[str, Any]]) -> str:
        rows = "".join(
            f"<tr><td>{escape(str(item.get('severity', '')))}</td><td>{escape(str(item.get('message', '')))}</td><td>{escape(str(item.get('line_number') or ''))}</td></tr>"
            for item in items
        )
        return f"<table><thead><tr><th>Severity</th><th>Message</th><th>Line</th></tr></thead><tbody>{rows}</tbody></table>"
