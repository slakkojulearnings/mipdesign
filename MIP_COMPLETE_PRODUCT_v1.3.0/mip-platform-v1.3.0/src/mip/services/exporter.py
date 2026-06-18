from __future__ import annotations

from pathlib import Path

from mip.persistence import SQLiteRepository


class MemoryExporter:
    def __init__(self, repository: SQLiteRepository) -> None:
        self.repository = repository

    def export(self, output_dir: Path, run_id: str | None = None) -> dict[str, Path]:
        output_dir.mkdir(parents=True, exist_ok=True)
        selected = run_id or self.repository.latest_run_id()
        if selected is None:
            raise ValueError("no analysis run available")

        catalog = output_dir / "catalog.txt"
        relationships = output_dir / "relationships.txt"
        todo = output_dir / "todo.list"
        processed = output_dir / "processed.log"

        asset_rows = self.repository.list_assets(run_id=selected, limit=1_000_000)
        catalog_lines = [
            "# TYPE|ID|READABLE_NAME|CATEGORY|SOURCE_PATH|DOC_PATH|CONTENT_HASH|CONFIDENCE|REVIEW_STATUS"
        ]
        for asset in asset_rows:
            catalog_lines.append(
                "|".join(
                    [
                        asset["asset_type"],
                        asset["technical_name"],
                        (asset.get("readable_name") or "").replace("|", "/"),
                        asset["attributes"].get("language", ""),
                        str(asset.get("source_path") or ""),
                        "",
                        "",
                        f"{float(asset['confidence']):.2f}",
                        asset["status"],
                    ]
                )
            )
        catalog.write_text("\n".join(catalog_lines) + "\n", encoding="utf-8")

        relationship_lines = [
            "# RELATION_TYPE|FROM_TYPE|FROM_ID|TO_TYPE|TO_ID|SOURCE_PATH|LINE_RANGE|CONFIDENCE|NOTES"
        ]
        for item in self.repository.relationship_rows(selected):
            relationship_lines.append(
                "|".join(
                    [
                        item["relationship_type"],
                        item["source_type"],
                        item["source_name"],
                        item["target_type"],
                        item["target_name"],
                        str(item.get("evidence_source_path") or ""),
                        (
                            f"{item.get('evidence_line_start') or ''}-{item.get('evidence_line_end') or ''}"
                            if item.get("evidence_line_start") or item.get("evidence_line_end")
                            else ""
                        ),
                        f"{float(item['confidence']):.2f}",
                        str(item["attributes"]).replace("|", "/"),
                    ]
                )
            )
        relationships.write_text("\n".join(relationship_lines) + "\n", encoding="utf-8")

        stats = self.repository.stats(selected)
        todo_lines = [
            "# STATUS|ARTIFACT_TYPE|ARTIFACT_ID|SOURCE_PATH|CONTENT_HASH|OWNER|STARTED_AT|COMPLETED_AT|OUTPUT_PATH|ERROR"
        ]
        for source_file in self.repository.source_files(selected):
            todo_lines.append(
                "|".join(
                    [
                        "DONE"
                        if source_file["parse_status"] in {"PARSED", "SKIPPED"}
                        else "BLOCKED",
                        source_file["artifact_type"],
                        source_file["id"],
                        source_file["relative_path"],
                        source_file["sha256"],
                        "mip-pipeline",
                        stats["run"]["started_at"] or "",
                        stats["run"]["completed_at"] or "",
                        "",
                        "" if source_file["parse_status"] != "FAILED" else "parser failed",
                    ]
                )
            )
        todo.write_text("\n".join(todo_lines) + "\n", encoding="utf-8")
        processed.write_text(
            "# TIMESTAMP|RUN_ID|AGENT|ACTION|ARTIFACT_ID|RESULT|DETAILS\n"
            f"{stats['run']['completed_at']}|{selected}|mip-pipeline|ANALYZE|REPOSITORY|{stats['run']['status']}|"
            f"files={stats['run']['file_count']};assets={stats['run']['asset_count']};relationships={stats['run']['relationship_count']}\n",
            encoding="utf-8",
        )
        return {
            "catalog": catalog,
            "relationships": relationships,
            "todo": todo,
            "processed": processed,
        }
