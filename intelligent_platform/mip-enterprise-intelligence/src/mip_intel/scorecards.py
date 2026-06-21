from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from .repositories import SQLiteGraphRepository


def load_scorecard(path: str | Path) -> dict[str, Any]:
    return json.loads(Path(path).read_text(encoding="utf-8"))


def run_scorecard(
    repository: SQLiteGraphRepository,
    run_id: str,
    manifest: dict[str, Any],
) -> dict[str, Any]:
    name = str(manifest.get("name") or "ground-truth")
    expected_members = [_member_key(row) for row in manifest.get("expected_members", [])]
    expected_nodes = [_node_key(row) for row in manifest.get("expected_nodes", [])]
    expected_edges = [_edge_key(row) for row in manifest.get("expected_edges", [])]
    forbidden_nodes = [_node_key(row) for row in manifest.get("forbidden_nodes", [])]
    forbidden_edges = [_edge_key(row) for row in manifest.get("forbidden_edges", [])]

    with repository.connect() as conn:
        observed_members = {
            (row["relative_path"].upper(), row["artifact_type"].upper())
            for row in conn.execute(
                "SELECT relative_path, artifact_type FROM source_member WHERE run_id = ?",
                (run_id,),
            )
        }
        observed_nodes = {
            (row["asset_type"].upper(), row["technical_name"].upper())
            for row in conn.execute(
                "SELECT asset_type, technical_name FROM asset WHERE run_id = ?",
                (run_id,),
            )
        }
        observed_edges = {
            (
                row["relationship_type"].upper(),
                row["source_name"].upper(),
                row["target_name"].upper(),
            )
            for row in conn.execute(
                """
                SELECT r.relationship_type, s.technical_name AS source_name, t.technical_name AS target_name
                FROM relationship r
                JOIN asset s ON s.asset_id = r.source_asset_id
                JOIN asset t ON t.asset_id = r.target_asset_id
                WHERE r.run_id = ?
                """,
                (run_id,),
            )
        }

    expected = {
        "members": set(expected_members),
        "nodes": set(expected_nodes),
        "edges": set(expected_edges),
    }
    observed = {
        "members": observed_members,
        "nodes": observed_nodes,
        "edges": observed_edges,
    }
    forbidden = {
        "nodes": set(forbidden_nodes),
        "edges": set(forbidden_edges),
    }
    matched = {
        section: sorted(values & observed[section])
        for section, values in expected.items()
    }
    missing = {
        section: sorted(values - observed[section])
        for section, values in expected.items()
    }
    unexpected = {
        "nodes": sorted(forbidden["nodes"] & observed["nodes"]),
        "edges": sorted(forbidden["edges"] & observed["edges"]),
    }
    expected_count = sum(len(values) for values in expected.values()) + sum(len(values) for values in forbidden.values())
    matched_count = sum(len(values) for values in matched.values())
    missing_count = sum(len(values) for values in missing.values())
    unexpected_count = sum(len(values) for values in unexpected.values())
    recall = matched_count / max(sum(len(values) for values in expected.values()), 1)
    precision = matched_count / max(matched_count + unexpected_count, 1)
    status = "passed" if missing_count == 0 and unexpected_count == 0 else "failed"
    payload = {
        "run_id": run_id,
        "name": name,
        "expected_count": expected_count,
        "matched_count": matched_count,
        "missing_count": missing_count,
        "unexpected_count": unexpected_count,
        "precision": round(precision, 4),
        "recall": round(recall, 4),
        "status": status,
        "details": {
            "matched": _jsonable_sets(matched),
            "missing": _jsonable_sets(missing),
            "unexpected": _jsonable_sets(unexpected),
            "manifest_version": manifest.get("version", "1"),
        },
    }
    scorecard_id = repository.replace_scorecard_result(run_id, name, payload)
    return {"scorecard_id": scorecard_id, **payload}


def _member_key(row: dict[str, Any]) -> tuple[str, str]:
    return (str(row.get("path") or row.get("relative_path") or "").upper(), str(row.get("artifact_type") or "").upper())


def _node_key(row: dict[str, Any]) -> tuple[str, str]:
    return (str(row.get("type") or row.get("asset_type") or "").upper(), str(row.get("name") or row.get("technical_name") or "").upper())


def _edge_key(row: dict[str, Any]) -> tuple[str, str, str]:
    return (
        str(row.get("type") or row.get("relationship_type") or "").upper(),
        str(row.get("source") or row.get("source_name") or "").upper(),
        str(row.get("target") or row.get("target_name") or "").upper(),
    )


def _jsonable_sets(sections: dict[str, list[tuple[Any, ...]]]) -> dict[str, list[list[Any]]]:
    return {name: [list(value) for value in values] for name, values in sections.items()}
