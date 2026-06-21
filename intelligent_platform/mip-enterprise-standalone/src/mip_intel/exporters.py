from __future__ import annotations

import csv
import io
import json
from typing import Any
from xml.sax.saxutils import escape

from .repositories import SQLiteGraphRepository


class GraphExporter:
    def __init__(self, repository: SQLiteGraphRepository) -> None:
        self.repository = repository

    def json_bundle(self, run_id: str) -> dict[str, Any]:
        with self.repository.connect() as conn:
            assets = [dict(row) for row in conn.execute("SELECT * FROM asset WHERE run_id = ?", (run_id,))]
            relationships = [
                dict(row)
                for row in conn.execute("SELECT * FROM relationship WHERE run_id = ?", (run_id,))
            ]
            evidence = [
                dict(row) for row in conn.execute("SELECT * FROM evidence WHERE run_id = ?", (run_id,))
            ]
        return {"run_id": run_id, "assets": assets, "relationships": relationships, "evidence": evidence}

    def csv_assets(self, run_id: str) -> str:
        return self._csv(
            "SELECT asset_id, asset_type, technical_name, confidence, validation_status FROM asset WHERE run_id = ?",
            run_id,
        )

    def csv_relationships(self, run_id: str) -> str:
        return self._csv(
            """
            SELECT relationship_id, relationship_type, source_asset_id, target_asset_id,
                   confidence, validation_status, discovery_method
            FROM relationship WHERE run_id = ?
            """,
            run_id,
        )

    def graphml(self, run_id: str) -> str:
        bundle = self.json_bundle(run_id)
        lines = [
            '<?xml version="1.0" encoding="UTF-8"?>',
            '<graphml xmlns="http://graphml.graphdrawing.org/xmlns">',
            '<graph edgedefault="directed">',
        ]
        for asset in bundle["assets"]:
            lines.append(f'<node id="{escape(asset["asset_id"])}">')
            lines.append(f'<data key="label">{escape(asset["technical_name"])}</data>')
            lines.append(f'<data key="type">{escape(asset["asset_type"])}</data>')
            lines.append("</node>")
        for rel in bundle["relationships"]:
            lines.append(
                f'<edge id="{escape(rel["relationship_id"])}" '
                f'source="{escape(rel["source_asset_id"])}" '
                f'target="{escape(rel["target_asset_id"])}">'
            )
            lines.append(f'<data key="type">{escape(rel["relationship_type"])}</data>')
            lines.append(f'<data key="confidence">{rel["confidence"]}</data>')
            lines.append(f'<data key="status">{escape(rel["validation_status"])}</data>')
            lines.append("</edge>")
        lines.extend(["</graph>", "</graphml>"])
        return "\n".join(lines)

    def _csv(self, sql: str, run_id: str) -> str:
        with self.repository.connect() as conn:
            rows = conn.execute(sql, (run_id,)).fetchall()
        output = io.StringIO()
        if not rows:
            return ""
        writer = csv.DictWriter(output, fieldnames=list(dict(rows[0]).keys()))
        writer.writeheader()
        for row in rows:
            writer.writerow(dict(row))
        return output.getvalue()

    def as_text(self, run_id: str, fmt: str, kind: str = "bundle") -> str:
        fmt = fmt.lower()
        if fmt == "json":
            return json.dumps(self.json_bundle(run_id), indent=2, sort_keys=True)
        if fmt == "graphml":
            return self.graphml(run_id)
        if fmt == "csv" and kind == "relationships":
            return self.csv_relationships(run_id)
        if fmt == "csv":
            return self.csv_assets(run_id)
        raise ValueError(f"unsupported export format: {fmt}")
