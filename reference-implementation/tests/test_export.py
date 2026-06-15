"""Tests for the export endpoints (graphml / json / csv) over the sample estate."""

from __future__ import annotations

import csv
import io
import json
import sys
from pathlib import Path

_SRC = Path(__file__).resolve().parent.parent / "src"
sys.path.insert(0, str(_SRC))

from fastapi.testclient import TestClient   # noqa: E402

from mip.api import app                       # noqa: E402

ESTATE = Path(__file__).resolve().parent.parent / "sample_estate"


def _client() -> TestClient:
    c = TestClient(app)
    r = c.post("/api/scan", params={"path": str(ESTATE)})
    assert r.status_code == 200, r.text
    return c


def test_export_graphml():
    c = _client()
    r = c.get("/api/export", params={"format": "graphml"})
    assert r.status_code == 200
    assert r.headers["content-type"].startswith("application/xml")
    assert "attachment" in r.headers["content-disposition"]
    assert "mip-graph.graphml" in r.headers["content-disposition"]
    body = r.text
    assert "<graphml" in body
    assert "CRDPOST" in body and "CRDVAL" in body      # node ids present


def test_export_json():
    c = _client()
    r = c.get("/api/export", params={"format": "json"})
    assert r.status_code == 200
    assert r.headers["content-type"].startswith("application/json")
    assert "mip-export.json" in r.headers["content-disposition"]
    data = json.loads(r.text)
    assert {"summary", "programs", "graph"} <= set(data.keys())
    assert data["summary"]["programs"] > 0
    assert any(p["program_id"] == "CRDPOST" for p in data["programs"])


def test_export_csv_programs():
    c = _client()
    r = c.get("/api/export", params={"format": "csv", "kind": "programs"})
    assert r.status_code == 200
    assert r.headers["content-type"].startswith("text/csv")
    assert "mip-programs.csv" in r.headers["content-disposition"]
    rows = list(csv.reader(io.StringIO(r.text)))
    assert rows[0] == ["program_id", "language", "line_count", "calls_out",
                       "called_by", "is_root", "is_dead"]
    assert any(row and row[0] == "CRDPOST" for row in rows[1:])


def test_export_csv_edges():
    c = _client()
    r = c.get("/api/export", params={"format": "csv", "kind": "edges"})
    assert r.status_code == 200
    rows = list(csv.reader(io.StringIO(r.text)))
    assert rows[0] == ["source_type", "source_id", "rel_type", "target_type",
                       "target_id", "validation_status", "confidence", "source_evidence"]
    # CRDPOST CALLS CRDVAL is a confirmed edge in the estate
    assert any(row[1] == "CRDPOST" and row[2] == "CALLS" and row[4] == "CRDVAL"
               for row in rows[1:])


def test_export_unknown_format_is_400():
    c = _client()
    r = c.get("/api/export", params={"format": "pdf"})
    assert r.status_code == 400
