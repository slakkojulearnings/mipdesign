from __future__ import annotations

import csv
import json
from pathlib import Path
from typing import Any

from .models import Asset, Evidence, Relationship, now_iso, stable_id
from .repositories import SQLiteGraphRepository


EXTERNAL_EXTRACTOR = "external_evidence_importer_v1"


class ExternalEvidenceService:
    def __init__(self, repository: SQLiteGraphRepository) -> None:
        self.repository = repository

    def import_runtime_calls(self, run_id: str, path: str | Path, *, source_system: str = "runtime") -> dict[str, Any]:
        records = _load_records(path)
        imported = 0
        skipped = 0
        for row in records:
            source = _clean_name(row.get("source_program") or row.get("source") or row.get("caller") or "")
            target = _clean_name(row.get("target_program") or row.get("target") or row.get("callee") or "")
            if not source or not target:
                skipped += 1
                continue
            count = _int(row.get("count") or row.get("observation_count") or 1, default=1)
            attrs = {
                "runtime_observed": True,
                "observation_source": str(row.get("source_system") or source_system),
                "observation_count": count,
                "first_seen": _optional_text(row.get("first_seen")),
                "last_seen": _optional_text(row.get("last_seen")),
                "environment": _optional_text(row.get("environment")),
                "job": _clean_name(row.get("job") or ""),
                "transaction": _clean_name(row.get("transaction") or row.get("transaction_id") or ""),
                "evidence": dict(row),
            }
            self._store_runtime_observation(run_id, source, target, attrs)
            source_asset = _asset(run_id, "PROGRAM", source, confidence=0.98, validation_status="confirmed", discovery_method="runtime-observation")
            target_asset = _asset(run_id, "PROGRAM", target, confidence=0.98, validation_status="confirmed", discovery_method="runtime-observation")
            self._ensure_asset(source_asset, [_external_evidence(path, attrs, 0.98, "confirmed")])
            self._ensure_asset(target_asset, [_external_evidence(path, attrs, 0.98, "confirmed")])
            rel = Relationship(
                run_id=run_id,
                relationship_type="OBSERVED_CALLS",
                source_asset_id=source_asset.asset_id,
                target_asset_id=target_asset.asset_id,
                confidence=0.98,
                validation_status="confirmed",
                discovery_method="runtime-observation",
                attributes=attrs,
                origin="external_evidence",
            )
            self.repository.insert_relationship(rel, [_external_evidence(path, attrs, 0.98, "confirmed")])
            imported += 1
        return {
            "run_id": run_id,
            "input": str(path),
            "source_system": source_system,
            "imported": imported,
            "skipped": skipped,
            "record_count": len(records),
        }

    def import_catalog(self, run_id: str, path: str | Path, *, catalog_source: str = "catalog") -> dict[str, Any]:
        records = _load_records(path)
        imported = 0
        skipped = 0
        for row in records:
            raw = _clean_dataset(row.get("raw_dataset") or row.get("dataset") or row.get("dsn") or row.get("name") or "")
            canonical = _clean_dataset(row.get("canonical_dataset") or row.get("canonical") or row.get("base") or raw)
            if not raw or not canonical:
                skipped += 1
                continue
            attrs = _catalog_attrs(row, raw, canonical, catalog_source)
            self._store_catalog_dataset(run_id, attrs)
            raw_asset = _asset(run_id, "DATASET", raw, confidence=0.92, validation_status="confirmed", discovery_method="catalog-import")
            identity = _asset(
                run_id,
                "DATASET_IDENTITY",
                canonical,
                confidence=0.96,
                validation_status="confirmed",
                discovery_method="catalog-import",
                attributes=attrs,
            )
            self._ensure_asset(raw_asset, [_external_evidence(path, attrs, 0.92, "confirmed")])
            self._ensure_asset(identity, [_external_evidence(path, attrs, 0.96, "confirmed")])
            rel = Relationship(
                run_id=run_id,
                relationship_type="CATALOG_DESCRIBES_DATASET",
                source_asset_id=identity.asset_id,
                target_asset_id=raw_asset.asset_id,
                confidence=0.96,
                validation_status="confirmed",
                discovery_method="catalog-import",
                attributes=attrs,
                origin="external_evidence",
            )
            self.repository.insert_relationship(rel, [_external_evidence(path, attrs, 0.96, "confirmed")])
            if raw != canonical:
                alias_rel = Relationship(
                    run_id=run_id,
                    relationship_type="CATALOG_ALIASES_DATASET",
                    source_asset_id=raw_asset.asset_id,
                    target_asset_id=identity.asset_id,
                    confidence=0.94,
                    validation_status="confirmed",
                    discovery_method="catalog-import",
                    attributes={**attrs, "alias": raw},
                    origin="external_evidence",
                )
                self.repository.insert_relationship(alias_rel, [_external_evidence(path, attrs, 0.94, "confirmed")])
            imported += 1
        return {
            "run_id": run_id,
            "input": str(path),
            "catalog_source": catalog_source,
            "imported": imported,
            "skipped": skipped,
            "record_count": len(records),
        }

    def evidence_summary(self, run_id: str) -> dict[str, Any]:
        with self.repository.connect() as conn:
            runtime = conn.execute(
                """
                SELECT observation_type, COUNT(*) AS count, SUM(observation_count) AS observed_count
                FROM runtime_observation
                WHERE run_id = ?
                GROUP BY observation_type
                ORDER BY observation_type
                """,
                (run_id,),
            ).fetchall()
            catalog = conn.execute(
                """
                SELECT catalog_source, COUNT(*) AS count, COUNT(DISTINCT canonical_dataset) AS identities
                FROM catalog_dataset
                WHERE run_id = ?
                GROUP BY catalog_source
                ORDER BY catalog_source
                """,
                (run_id,),
            ).fetchall()
        return {
            "run_id": run_id,
            "runtime_observations": [dict(row) for row in runtime],
            "catalog_datasets": [dict(row) for row in catalog],
        }

    def _ensure_asset(self, asset: Asset, evidence: list[Evidence]) -> None:
        existing = self.repository.get_asset(asset.asset_id)
        if existing is None:
            self.repository.upsert_asset(asset, evidence)
            return
        with self.repository.connect() as conn:
            for item in evidence:
                self.repository._insert_evidence(conn, asset.run_id, "ASSET", asset.asset_id, item)

    def _store_runtime_observation(self, run_id: str, source: str, target: str, attrs: dict[str, Any]) -> None:
        observation_id = stable_id(
            run_id,
            "runtime_observation",
            source,
            target,
            attrs.get("observation_source"),
            attrs.get("environment"),
            attrs.get("job"),
            attrs.get("transaction"),
        )
        with self.repository.connect() as conn:
            conn.execute(
                """
                INSERT INTO runtime_observation(
                    observation_id, run_id, observation_type, source_asset, target_asset,
                    observation_count, first_seen, last_seen, environment, job,
                    transaction_id, source_system, evidence_json, imported_at
                ) VALUES (?, ?, 'CALL', ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(observation_id) DO UPDATE SET
                    observation_count = runtime_observation.observation_count + excluded.observation_count,
                    first_seen = COALESCE(runtime_observation.first_seen, excluded.first_seen),
                    last_seen = COALESCE(excluded.last_seen, runtime_observation.last_seen),
                    evidence_json = excluded.evidence_json,
                    imported_at = excluded.imported_at
                """,
                (
                    observation_id,
                    run_id,
                    source,
                    target,
                    int(attrs.get("observation_count") or 1),
                    attrs.get("first_seen"),
                    attrs.get("last_seen"),
                    attrs.get("environment"),
                    attrs.get("job"),
                    attrs.get("transaction"),
                    attrs.get("observation_source"),
                    json.dumps(attrs.get("evidence") or {}, sort_keys=True),
                    now_iso(),
                ),
            )

    def _store_catalog_dataset(self, run_id: str, attrs: dict[str, Any]) -> None:
        catalog_id = stable_id(run_id, "catalog_dataset", attrs["raw_dataset"], attrs["catalog_source"])
        with self.repository.connect() as conn:
            conn.execute(
                """
                INSERT INTO catalog_dataset(
                    catalog_id, run_id, raw_dataset, canonical_dataset, dataset_type,
                    gdg_base, vsam_cluster, volume, storage_class, management_class,
                    record_format, lrecl, owner, application, catalog_source,
                    evidence_json, imported_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(run_id, raw_dataset, catalog_source) DO UPDATE SET
                    canonical_dataset = excluded.canonical_dataset,
                    dataset_type = excluded.dataset_type,
                    gdg_base = excluded.gdg_base,
                    vsam_cluster = excluded.vsam_cluster,
                    volume = excluded.volume,
                    storage_class = excluded.storage_class,
                    management_class = excluded.management_class,
                    record_format = excluded.record_format,
                    lrecl = excluded.lrecl,
                    owner = excluded.owner,
                    application = excluded.application,
                    evidence_json = excluded.evidence_json,
                    imported_at = excluded.imported_at
                """,
                (
                    catalog_id,
                    run_id,
                    attrs["raw_dataset"],
                    attrs["canonical_dataset"],
                    attrs.get("dataset_type"),
                    attrs.get("gdg_base"),
                    attrs.get("vsam_cluster"),
                    attrs.get("volume"),
                    attrs.get("storage_class"),
                    attrs.get("management_class"),
                    attrs.get("record_format"),
                    attrs.get("lrecl"),
                    attrs.get("owner"),
                    attrs.get("application"),
                    attrs["catalog_source"],
                    json.dumps(attrs.get("evidence") or {}, sort_keys=True),
                    now_iso(),
                ),
            )


def _load_records(path: str | Path) -> list[dict[str, Any]]:
    selected = Path(path)
    text = selected.read_text(encoding="utf-8-sig")
    if selected.suffix.lower() == ".json":
        payload = json.loads(text)
        if isinstance(payload, dict):
            for key in ("records", "items", "runtime_calls", "datasets"):
                if isinstance(payload.get(key), list):
                    return [dict(item) for item in payload[key]]
            return [payload]
        if isinstance(payload, list):
            return [dict(item) for item in payload]
        raise ValueError(f"Unsupported JSON payload in {selected}")
    rows = csv.DictReader(text.splitlines())
    return [dict(row) for row in rows]


def _catalog_attrs(row: dict[str, Any], raw: str, canonical: str, catalog_source: str) -> dict[str, Any]:
    return {
        "raw_dataset": raw,
        "canonical_dataset": canonical,
        "catalog_dataset": raw,
        "dataset_type": _optional_text(row.get("dataset_type") or row.get("type")),
        "gdg_base": _clean_dataset(row.get("gdg_base") or ""),
        "vsam_cluster": _clean_dataset(row.get("vsam_cluster") or row.get("cluster") or ""),
        "volume": _optional_text(row.get("volume")),
        "storage_class": _optional_text(row.get("storage_class") or row.get("storclas")),
        "management_class": _optional_text(row.get("management_class") or row.get("mgmtclas")),
        "record_format": _optional_text(row.get("record_format") or row.get("recfm")),
        "lrecl": _optional_text(row.get("lrecl")),
        "owner": _optional_text(row.get("owner")),
        "application": _optional_text(row.get("application") or row.get("app")),
        "catalog_source": _optional_text(row.get("catalog_source") or catalog_source) or "catalog",
        "catalog_confirmed": True,
        "evidence": dict(row),
    }


def _external_evidence(path: str | Path, attrs: dict[str, Any], confidence: float, status: str) -> Evidence:
    return Evidence(
        source_path=str(path),
        line_start=None,
        line_end=None,
        evidence_text=json.dumps(attrs.get("evidence") or attrs, sort_keys=True)[:500],
        extractor=EXTERNAL_EXTRACTOR,
        discovery_method=str(attrs.get("observation_source") or attrs.get("catalog_source") or "external-import"),
        confidence=confidence,
        validation_status=status,
    )


def _asset(
    run_id: str,
    asset_type: str,
    name: str,
    *,
    confidence: float,
    validation_status: str,
    discovery_method: str,
    attributes: dict[str, Any] | None = None,
) -> Asset:
    technical_name = _clean_dataset(name) if asset_type in {"DATASET", "DATASET_IDENTITY"} else _clean_name(name)
    return Asset(
        run_id=run_id,
        asset_type=asset_type,
        technical_name=technical_name,
        display_name=technical_name,
        confidence=confidence,
        validation_status=validation_status,
        discovery_method=discovery_method,
        attributes={"external_evidence": True, **(attributes or {})},
        origin="external_evidence",
    )


def _clean_name(value: Any) -> str:
    return str(value or "").strip().strip("'\"()[],.").upper()


def _clean_dataset(value: Any) -> str:
    return str(value or "").strip().strip("'\"[],.").upper()


def _optional_text(value: Any) -> str | None:
    text = str(value or "").strip()
    return text or None


def _int(value: Any, *, default: int) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return default
