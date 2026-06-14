from __future__ import annotations

from typing import Any

from mip.persistence import SQLiteRepository


class ValidationService:
    def __init__(self, repository: SQLiteRepository) -> None:
        self.repository = repository

    def validate(self, run_id: str | None = None) -> dict[str, Any]:
        selected = run_id or self.repository.latest_run_id()
        if selected is None:
            return {"status": "FAIL", "checks": [], "message": "No analysis run available"}

        stats = self.repository.stats(selected)
        files = self.repository.source_files(selected)
        issues = self.repository.parse_issues(selected)
        unresolved = [
            asset
            for asset in self.repository.list_assets(run_id=selected, limit=1_000_000)
            if asset["status"] == "UNRESOLVED"
        ]
        failed_files = [item for item in files if item["parse_status"] == "FAILED"]
        unknown_files = [item for item in files if item["artifact_type"] in {"UNKNOWN", "BINARY"}]
        error_issues = [item for item in issues if item["severity"].upper() == "ERROR"]

        checks: list[dict[str, Any]] = [
            {
                "name": "inventory-reconciliation",
                "status": "PASS" if len(files) == int(stats["run"]["file_count"]) else "FAIL",
                "details": {
                    "source_files": len(files),
                    "run_file_count": stats["run"]["file_count"],
                },
            },
            {
                "name": "parser-failures",
                "status": "PASS" if not failed_files else "FAIL",
                "details": {"failed_files": [item["relative_path"] for item in failed_files]},
            },
            {
                "name": "parse-errors",
                "status": "PASS" if not error_issues else "FAIL",
                "details": {"error_count": len(error_issues)},
            },
            {
                "name": "unknown-artifacts",
                "status": "PASS" if not unknown_files else "WARN",
                "details": {"unknown_count": len(unknown_files)},
            },
            {
                "name": "unresolved-assets",
                "status": "PASS" if not unresolved else "WARN",
                "details": {
                    "count": len(unresolved),
                    "examples": [
                        {"type": item["asset_type"], "name": item["technical_name"]}
                        for item in unresolved[:20]
                    ],
                },
            },
        ]
        statuses = {item["status"] for item in checks}
        overall = "FAIL" if "FAIL" in statuses else ("WARN" if "WARN" in statuses else "PASS")
        return {"status": overall, "run_id": selected, "checks": checks}
