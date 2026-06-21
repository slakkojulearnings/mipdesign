from __future__ import annotations

import json
import shutil
from pathlib import Path
from typing import Any


def write_reverse_engineering_bundle(
    payload: dict[str, Any],
    output_dir: str | Path,
    *,
    include_sources: bool = True,
) -> dict[str, Any]:
    target = Path(output_dir)
    target.mkdir(parents=True, exist_ok=True)
    _write_json(target / "manifest.json", _manifest(payload))
    _write_json(target / "files.json", payload.get("files", []))
    _write_json(target / "assets.json", payload.get("assets", []))
    _write_json(target / "relationships.json", payload.get("relationships", []))
    _write_json(target / "evidence.json", payload.get("evidence", []))
    _write_json(target / "ast.json", payload.get("ast_summaries", []))
    _write_json(target / "minimal_context.json", payload.get("minimal_context", {}))
    copied = []
    skipped = []
    if include_sources:
        source_root = Path(str(payload.get("source_root", ""))) if payload.get("source_root") else None
        source_target = target / "source"
        source_target.mkdir(exist_ok=True)
        for item in payload.get("files", []):
            relative = item.get("relative_path")
            absolute = item.get("absolute_path")
            if not relative:
                continue
            source = Path(absolute) if absolute else source_root / relative if source_root else None
            if source is None or not source.is_file():
                skipped.append({"relative_path": relative, "reason": "source_not_available"})
                continue
            destination = source_target / Path(relative.replace("\\", "/"))
            destination.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(source, destination)
            copied.append({"relative_path": relative, "output": str(destination)})
    summary = {
        "output_dir": str(target),
        "json_files": [
            "manifest.json",
            "files.json",
            "assets.json",
            "relationships.json",
            "evidence.json",
            "ast.json",
            "minimal_context.json",
        ],
        "copied_sources": copied,
        "skipped_sources": skipped,
    }
    _write_json(target / "bundle_summary.json", summary)
    return summary


def _manifest(payload: dict[str, Any]) -> dict[str, Any]:
    return {
        "run_id": payload.get("run_id"),
        "root_asset_id": payload.get("root_asset_id"),
        "source_root": payload.get("source_root"),
        "depth": payload.get("depth"),
        "truncated": payload.get("truncated"),
        "file_count": len(payload.get("files", [])),
        "asset_count": len(payload.get("assets", [])),
        "relationship_count": len(payload.get("relationships", [])),
        "evidence_count": len(payload.get("evidence", [])),
        "ast_count": len(payload.get("ast_summaries", [])),
    }


def _write_json(path: Path, payload: Any) -> None:
    path.write_text(json.dumps(payload, indent=2, sort_keys=True, default=str), encoding="utf-8")
