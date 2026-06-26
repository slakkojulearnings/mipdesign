from __future__ import annotations

import json
import multiprocessing as mp
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import replace
from pathlib import Path
from typing import Any

from .ingestion import (
    ClassifiedMember,
    _asset_for_member,
    _cobol_relationships,
    _insert_relationship,
    _upsert_asset,
)
from .models import Evidence, Relationship, SourceMember, now_iso, stable_id
from .reference_parser import DEEP_PARSER_VERSION, ast_tree, copybook_resolver, parse_cobol_deep
from .repositories import SQLiteGraphRepository

DEEP_DISCOVERY_METHOD = "antlr4_deep_parser"
DEFAULT_DIALECT = "ibm-enterprise-cobol"


class EnrichmentService:
    def __init__(self, repository: SQLiteGraphRepository) -> None:
        self.repository = repository

    def enrich(
        self,
        run_id: str,
        *,
        top_n: int = 5000,
        timeout: float = 20.0,
        max_workers: int = 1,
        priority: str = "roots",
        changed_only: bool = False,
        force: bool = False,
    ) -> dict[str, Any]:
        source_root = self._source_root(run_id)
        copybooks, metadata, resolver_fingerprint = self._copybooks(run_id, source_root)
        resolver = copybook_resolver(copybooks, metadata)
        self._ensure_member_statuses(run_id, resolver_fingerprint, priority=priority)
        candidates = self._select_candidates(run_id, top_n=top_n, changed_only=changed_only, force=force)
        job_id = self._start_job(
            run_id,
            {
                "top_n": top_n,
                "timeout": timeout,
                "max_workers": max_workers,
                "priority": priority,
                "changed_only": changed_only,
                "force": force,
            },
            selected_count=len(candidates),
        )
        counts = {"selected": len(candidates), "enriched": 0, "failed": 0, "skipped": 0}
        if not candidates:
            self._finish_job(job_id, status="COMPLETED", counts=counts)
            return {"run_id": run_id, "job_id": job_id, **counts, "coverage": self.coverage(run_id)}

        workers = max(1, min(int(max_workers or 1), 16))
        if workers == 1:
            for candidate in candidates:
                self._process_candidate(run_id, source_root, resolver, resolver_fingerprint, candidate, timeout, force, counts)
        else:
            with ThreadPoolExecutor(max_workers=workers) as executor:
                futures = {}
                for candidate in candidates:
                    artifact_id = self._artifact_id(candidate["source_sha256"], resolver_fingerprint)
                    cached = None if force else self._artifact(artifact_id)
                    if cached:
                        self._materialize_or_mark(run_id, source_root, resolver, candidate, cached, counts)
                        continue
                    text = self._read_member_text(source_root, candidate)
                    futures[
                        executor.submit(_deep_parse_hard_timeout_worker, text, resolver, timeout)
                    ] = (candidate, artifact_id)
                for future in as_completed(futures):
                    candidate, artifact_id = futures[future]
                    try:
                        payload, issue = future.result()
                    except Exception as exc:
                        payload = _parse_error_payload(str(exc))
                        issue = {"error_type": type(exc).__name__, "message": str(exc)}
                    artifact = self._store_artifact(
                        artifact_id,
                        candidate["source_sha256"],
                        resolver_fingerprint,
                        payload,
                        issue,
                    )
                    self._materialize_or_mark(run_id, source_root, resolver, candidate, artifact, counts)

        self._finish_job(job_id, status="COMPLETED", counts=counts)
        return {"run_id": run_id, "job_id": job_id, **counts, "coverage": self.coverage(run_id)}

    def status_for_asset(self, run_id: str, asset_id: str) -> dict[str, Any]:
        with self.repository.connect() as conn:
            row = conn.execute(
                """
                SELECT a.asset_id, a.technical_name, a.asset_type, a.attributes_json,
                       sm.member_id, sm.sha256, ems.state, ems.materialized_at,
                       ems.updated_at, ems.last_error, eac.parser_version,
                       eac.parse_status, eac.parser_confidence, eac.elapsed_ms
                FROM asset a
                LEFT JOIN source_member sm ON sm.member_id = a.member_id
                LEFT JOIN enrichment_member_status ems
                  ON ems.run_id = a.run_id AND ems.member_id = sm.member_id
                LEFT JOIN enrichment_artifact_cache eac ON eac.artifact_id = ems.artifact_id
                WHERE a.run_id = ? AND a.asset_id = ?
                """,
                (run_id, asset_id),
            ).fetchone()
        if row is None:
            raise KeyError(f"asset not found: {asset_id}")
        attrs = json.loads(row["attributes_json"] or "{}")
        baseline = attrs.get("parser") or {}
        deep = attrs.get("deep_parser") or {}
        return {
            "asset_id": row["asset_id"],
            "program": row["technical_name"],
            "asset_type": row["asset_type"],
            "baseline_parser": baseline.get("effective", "not_available"),
            "baseline_parse_status": baseline.get("validation_status", "unknown"),
            "deep_parser": deep.get("effective") or "antlr4_deep_parser",
            "deep_parse_status": attrs.get("deep_parse_status") or row["state"] or "not_requested",
            "last_deep_parsed": attrs.get("last_deep_parsed") or row["materialized_at"],
            "deep_parser_version": row["parser_version"],
            "deep_parse_error": row["last_error"],
            "parser_confidence": row["parser_confidence"],
            "elapsed_ms": row["elapsed_ms"],
        }

    def coverage(self, run_id: str) -> dict[str, Any]:
        with self.repository.connect() as conn:
            total = conn.execute(
                """
                SELECT COUNT(*) AS c
                FROM source_member
                WHERE run_id = ? AND artifact_type = 'COBOL' AND text_status = 'TEXT'
                """,
                (run_id,),
            ).fetchone()["c"]
            rows = conn.execute(
                """
                SELECT COALESCE(ems.state, 'baseline_only') AS state, COUNT(*) AS c
                FROM source_member sm
                LEFT JOIN enrichment_member_status ems
                  ON ems.run_id = sm.run_id AND ems.member_id = sm.member_id
                WHERE sm.run_id = ? AND sm.artifact_type = 'COBOL' AND sm.text_status = 'TEXT'
                GROUP BY COALESCE(ems.state, 'baseline_only')
                """,
                (run_id,),
            ).fetchall()
        counts = {row["state"]: int(row["c"]) for row in rows}
        enriched = counts.get("materialized", 0)
        failed = counts.get("failed", 0)
        unsupported = counts.get("unsupported", 0)
        baseline_only = max(total - enriched - failed - unsupported, 0)
        pct = lambda value: round((value / total * 100), 2) if total else 0.0
        return {
            "members": total,
            "baseline_only": baseline_only,
            "materialized": enriched,
            "failed": failed,
            "unsupported": unsupported,
            "baseline_only_pct": pct(baseline_only),
            "enriched_pct": pct(enriched),
            "failed_pct": pct(failed),
            "unsupported_pct": pct(unsupported),
        }

    def _process_candidate(
        self,
        run_id: str,
        source_root: Path,
        resolver,
        resolver_fingerprint: str,
        candidate: dict[str, Any],
        timeout: float,
        force: bool,
        counts: dict[str, int],
    ) -> None:
        artifact_id = self._artifact_id(candidate["source_sha256"], resolver_fingerprint)
        artifact = None if force else self._artifact(artifact_id)
        if artifact is None:
            text = self._read_member_text(source_root, candidate)
            payload, issue = _deep_parse_hard_timeout_worker(text, resolver, timeout)
            artifact = self._store_artifact(
                artifact_id,
                candidate["source_sha256"],
                resolver_fingerprint,
                payload,
                issue,
            )
        self._materialize_or_mark(run_id, source_root, resolver, candidate, artifact, counts)

    def _materialize_or_mark(
        self,
        run_id: str,
        source_root: Path,
        resolver,
        candidate: dict[str, Any],
        artifact: dict[str, Any],
        counts: dict[str, int],
    ) -> None:
        status = artifact["parse_status"]
        if status != "parsed":
            self._update_member_status(
                run_id,
                candidate["member_id"],
                candidate["source_sha256"],
                state=status if status == "unsupported" else "failed",
                artifact_id=artifact["artifact_id"],
                last_error=artifact.get("last_error"),
            )
            counts["failed" if status != "unsupported" else "skipped"] += 1
            return
        payload = json.loads(artifact["payload_json"] or "{}")
        text = self._read_member_text(source_root, candidate)
        member = self._source_member_from_candidate(run_id, candidate)
        item = ClassifiedMember(member=member, text=text, lines=tuple(text.splitlines()))
        fact_count = self._materialize_payload(run_id, item, payload)
        self._update_member_status(
            run_id,
            candidate["member_id"],
            candidate["source_sha256"],
            state="materialized",
            artifact_id=artifact["artifact_id"],
            fact_count=fact_count,
        )
        counts["enriched"] += 1

    def _materialize_payload(self, run_id: str, item: ClassifiedMember, payload: dict[str, Any]) -> int:
        parsed_at = now_iso()
        source = _asset_for_member(item, payload)
        existing = self.repository.get_asset(source.asset_id)
        attributes = dict(existing.get("attributes", {}) if existing else source.attributes)
        attributes.setdefault("baseline_parser", attributes.get("parser", {}))
        attributes.setdefault("baseline_ast_tree", attributes.get("ast_tree"))
        attributes["deep_parser"] = payload.get("parser", {})
        attributes["deep_parse_status"] = "completed"
        attributes["last_deep_parsed"] = parsed_at
        attributes["deep_ast_tree"] = ast_tree(payload)
        attributes["parser_status"] = {
            "baseline_parser": (attributes.get("baseline_parser") or {}).get("effective", "not_available"),
            "deep_parser": "antlr4_deep_parser",
            "deep_parse_status": "completed",
            "last_deep_parsed": parsed_at,
        }
        source = replace(source, attributes=attributes)
        relationships = _cobol_relationships(item, source, payload)
        with self.repository.connect() as conn:
            conn.execute(
                "DELETE FROM relationship WHERE run_id = ? AND origin = 'enrichment' AND enriched_by_member = ?",
                (run_id, item.member.member_id),
            )
            conn.execute(
                "DELETE FROM enrichment_fact_source WHERE run_id = ? AND origin = 'enrichment' AND source_member_id = ?",
                (run_id, item.member.member_id),
            )
            conn.execute("DELETE FROM graph_slice_cache WHERE run_id = ?", (run_id,))
            _upsert_asset(conn, self.repository, source, [])
            fact_count = 0
            for rel in relationships:
                if rel.source_asset:
                    _upsert_asset(conn, self.repository, rel.source_asset, [])
                _upsert_asset(conn, self.repository, rel.target, [])
                evidence = replace(
                    rel.evidence,
                    extractor=DEEP_DISCOVERY_METHOD,
                    discovery_method=DEEP_DISCOVERY_METHOD,
                    confidence=min(float(rel.evidence.confidence or 1.0), float(payload.get("parser", {}).get("confidence") or 1.0)),
                )
                relationship = Relationship(
                    run_id=run_id,
                    relationship_type=rel.relationship_type,
                    source_asset_id=rel.source_asset_id,
                    target_asset_id=rel.target.asset_id,
                    confidence=min(float(rel.confidence or 1.0), float(payload.get("parser", {}).get("confidence") or 1.0)),
                    validation_status=rel.validation_status,
                    discovery_method=DEEP_DISCOVERY_METHOD,
                    attributes={**(rel.attributes or {}), "parser_effective": payload.get("parser", {}).get("effective")},
                    origin="enrichment",
                    enriched_by_member=item.member.member_id,
                )
                _insert_relationship(conn, self.repository, relationship, [evidence])
                evidence_id = _evidence_id(run_id, "RELATIONSHIP", relationship.relationship_id, evidence)
                self._insert_fact_source(conn, run_id, "RELATIONSHIP", relationship.relationship_id, item.member.member_id, evidence_id, relationship.confidence)
                fact_count += 1
        return fact_count

    def _source_root(self, run_id: str) -> Path:
        with self.repository.connect() as conn:
            row = conn.execute("SELECT source_root FROM run_manifest WHERE run_id = ?", (run_id,)).fetchone()
        if row is None:
            raise KeyError(f"run not found: {run_id}")
        return Path(row["source_root"])

    def _copybooks(self, run_id: str, source_root: Path) -> tuple[dict[str, str], dict[str, dict[str, Any]], str]:
        copybooks: dict[str, str] = {}
        metadata: dict[str, dict[str, Any]] = {}
        rows = []
        with self.repository.connect() as conn:
            rows = [dict(row) for row in conn.execute(
                """
                SELECT *
                FROM source_member
                WHERE run_id = ? AND artifact_type = 'COPYBOOK' AND text_status = 'TEXT'
                ORDER BY member_name, relative_path
                """,
                (run_id,),
            )]
        for row in rows:
            text = self._read_member_text(source_root, row)
            name = str(row["member_name"]).upper()
            copybooks[name] = text
            metadata[name] = {
                "source_path": row["relative_path"],
                "artifact_type": row["artifact_type"],
                "candidate_count": 1,
                "selected_by": "enrichment_current_run",
            }
        fingerprint = stable_id(
            "copybook-resolver",
            [(row["member_name"], row["relative_path"], row["sha256"]) for row in rows],
        )
        return copybooks, metadata, fingerprint

    def _ensure_member_statuses(self, run_id: str, resolver_fingerprint: str, *, priority: str) -> None:
        del resolver_fingerprint
        with self.repository.connect() as conn:
            rows = conn.execute(
                """
                SELECT sm.*, a.asset_id, COALESCE(nd.total_degree, 0) AS total_degree,
                       CASE WHEN rs.root_asset_id IS NULL THEN 0 ELSE 1 END AS is_root
                FROM source_member sm
                LEFT JOIN asset a ON a.member_id = sm.member_id
                LEFT JOIN node_degree nd ON nd.run_id = sm.run_id AND nd.asset_id = a.asset_id
                LEFT JOIN root_summary rs ON rs.run_id = sm.run_id AND rs.root_asset_id = a.asset_id
                WHERE sm.run_id = ? AND sm.artifact_type = 'COBOL' AND sm.text_status = 'TEXT'
                """,
                (run_id,),
            ).fetchall()
            now = now_iso()
            for row in rows:
                priority_value = int(row["total_degree"] or 0)
                if priority == "roots" and row["is_root"]:
                    priority_value += 10000
                conn.execute(
                    """
                    INSERT INTO enrichment_member_status(
                        run_id, member_id, source_sha256, state, priority, updated_at
                    ) VALUES (?, ?, ?, 'pending', ?, ?)
                    ON CONFLICT(run_id, member_id) DO UPDATE SET
                        source_sha256 = excluded.source_sha256,
                        state = CASE
                            WHEN enrichment_member_status.source_sha256 <> excluded.source_sha256 THEN 'stale'
                            ELSE enrichment_member_status.state
                        END,
                        priority = excluded.priority,
                        updated_at = excluded.updated_at
                    """,
                    (run_id, row["member_id"], row["sha256"], priority_value, now),
                )

    def _select_candidates(self, run_id: str, *, top_n: int, changed_only: bool, force: bool) -> list[dict[str, Any]]:
        states = ("pending", "stale") if not force else ("pending", "stale", "failed", "unsupported", "materialized")
        placeholders = ",".join("?" for _ in states)
        condition = f"ems.state IN ({placeholders})"
        if changed_only:
            condition = f"({condition}) AND ems.state = 'stale'"
        params: list[Any] = [run_id, *states, min(max(int(top_n), 1), 100000)]
        with self.repository.connect() as conn:
            rows = conn.execute(
                f"""
                SELECT ems.source_sha256, ems.state, sm.*
                FROM enrichment_member_status ems
                JOIN source_member sm ON sm.member_id = ems.member_id
                WHERE ems.run_id = ? AND {condition}
                ORDER BY ems.priority DESC, sm.relative_path
                LIMIT ?
                """,
                params,
            ).fetchall()
            return [dict(row) for row in rows]

    def _artifact_id(self, source_sha256: str, resolver_fingerprint: str) -> str:
        return stable_id("enrichment-artifact", source_sha256, DEEP_PARSER_VERSION, DEFAULT_DIALECT, resolver_fingerprint)

    def _artifact(self, artifact_id: str) -> dict[str, Any] | None:
        with self.repository.connect() as conn:
            row = conn.execute("SELECT * FROM enrichment_artifact_cache WHERE artifact_id = ?", (artifact_id,)).fetchone()
            return dict(row) if row else None

    def _store_artifact(
        self,
        artifact_id: str,
        source_sha256: str,
        resolver_fingerprint: str,
        payload: dict[str, Any],
        issue: dict[str, Any] | None,
    ) -> dict[str, Any]:
        parser = payload.get("parser", {}) or {}
        status = _parse_status(parser, issue)
        diagnostics = {
            "parser": parser,
            "issue": issue or {},
        }
        artifact = {
            "artifact_id": artifact_id,
            "source_sha256": source_sha256,
            "parser_version": DEEP_PARSER_VERSION,
            "grammar_dialect": DEFAULT_DIALECT,
            "resolver_fingerprint": resolver_fingerprint,
            "parse_status": status,
            "ast_json": json.dumps(ast_tree(payload), sort_keys=True),
            "payload_json": json.dumps(payload, sort_keys=True),
            "diagnostics_json": json.dumps(diagnostics, sort_keys=True),
            "fact_count": _payload_fact_count(payload),
            "parser_confidence": float(parser.get("confidence") or 0.0),
            "elapsed_ms": float(parser.get("elapsed_ms") or 0.0),
            "last_error": (issue or {}).get("message") or parser.get("antlr4_error") or parser.get("preprocess_error"),
        }
        with self.repository.connect() as conn:
            conn.execute(
                """
                INSERT INTO enrichment_artifact_cache(
                    artifact_id, source_sha256, parser_version, grammar_dialect,
                    resolver_fingerprint, parse_status, ast_json, payload_json,
                    diagnostics_json, fact_count, parser_confidence, elapsed_ms, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(artifact_id) DO UPDATE SET
                    parse_status = excluded.parse_status,
                    ast_json = excluded.ast_json,
                    payload_json = excluded.payload_json,
                    diagnostics_json = excluded.diagnostics_json,
                    fact_count = excluded.fact_count,
                    parser_confidence = excluded.parser_confidence,
                    elapsed_ms = excluded.elapsed_ms,
                    created_at = excluded.created_at
                """,
                (
                    artifact["artifact_id"],
                    artifact["source_sha256"],
                    artifact["parser_version"],
                    artifact["grammar_dialect"],
                    artifact["resolver_fingerprint"],
                    artifact["parse_status"],
                    artifact["ast_json"],
                    artifact["payload_json"],
                    artifact["diagnostics_json"],
                    artifact["fact_count"],
                    artifact["parser_confidence"],
                    artifact["elapsed_ms"],
                    now_iso(),
                ),
            )
        return artifact

    def _update_member_status(
        self,
        run_id: str,
        member_id: str,
        source_sha256: str,
        *,
        state: str,
        artifact_id: str | None = None,
        last_error: str | None = None,
        fact_count: int = 0,
    ) -> None:
        del fact_count
        with self.repository.connect() as conn:
            conn.execute(
                """
                INSERT INTO enrichment_member_status(
                    run_id, member_id, source_sha256, artifact_id, state, attempts,
                    last_error, materialized_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, 1, ?, ?, ?)
                ON CONFLICT(run_id, member_id) DO UPDATE SET
                    source_sha256 = excluded.source_sha256,
                    artifact_id = excluded.artifact_id,
                    state = excluded.state,
                    attempts = enrichment_member_status.attempts + 1,
                    last_error = excluded.last_error,
                    materialized_at = excluded.materialized_at,
                    updated_at = excluded.updated_at
                """,
                (
                    run_id,
                    member_id,
                    source_sha256,
                    artifact_id,
                    state,
                    last_error,
                    now_iso() if state == "materialized" else None,
                    now_iso(),
                ),
            )

    def _insert_fact_source(
        self,
        conn,
        run_id: str,
        entity_kind: str,
        entity_id: str,
        member_id: str,
        evidence_id: str,
        confidence: float,
    ) -> None:
        fact_source_id = stable_id(run_id, "fact_source", entity_kind, entity_id, "enrichment", member_id, evidence_id)
        conn.execute(
            """
            INSERT OR REPLACE INTO enrichment_fact_source(
                fact_source_id, run_id, entity_kind, entity_id, origin, source_member_id,
                evidence_id, parser_tier, confidence, created_at
            ) VALUES (?, ?, ?, ?, 'enrichment', ?, ?, 'antlr-full', ?, ?)
            """,
            (fact_source_id, run_id, entity_kind, entity_id, member_id, evidence_id, confidence, now_iso()),
        )

    def _start_job(self, run_id: str, config: dict[str, Any], *, selected_count: int) -> str:
        job_id = stable_id(run_id, "enrichment-job", now_iso(), selected_count)
        with self.repository.connect() as conn:
            conn.execute(
                """
                INSERT INTO enrichment_job(job_id, run_id, started_at, status, selected_count, config_json)
                VALUES (?, ?, ?, 'RUNNING', ?, ?)
                """,
                (job_id, run_id, now_iso(), selected_count, json.dumps(config, sort_keys=True)),
            )
        return job_id

    def _finish_job(self, job_id: str, *, status: str, counts: dict[str, int]) -> None:
        with self.repository.connect() as conn:
            conn.execute(
                """
                UPDATE enrichment_job
                SET finished_at = ?, status = ?, enriched_count = ?, failed_count = ?, skipped_count = ?
                WHERE job_id = ?
                """,
                (
                    now_iso(),
                    status,
                    counts.get("enriched", 0),
                    counts.get("failed", 0),
                    counts.get("skipped", 0),
                    job_id,
                ),
            )

    def _read_member_text(self, source_root: Path, row: dict[str, Any]) -> str:
        path = source_root / str(row["relative_path"])
        encoding = row.get("encoding") or "utf-8"
        try:
            return path.read_text(encoding=encoding, errors="replace")
        except LookupError:
            return path.read_text(encoding="utf-8", errors="replace")

    @staticmethod
    def _source_member_from_candidate(run_id: str, row: dict[str, Any]) -> SourceMember:
        return SourceMember(
            run_id=run_id,
            relative_path=row["relative_path"],
            folder_path=row["folder_path"],
            member_name=row["member_name"],
            sha256=row["sha256"],
            size_bytes=row["size_bytes"],
            encoding=row["encoding"],
            is_binary=bool(row["is_binary"]),
            text_status=row["text_status"],
            artifact_type=row["artifact_type"],
            classification_basis=row["classification_basis"],
            confidence=row["confidence"],
            validation_status=row["validation_status"],
            discovered_at=row["discovered_at"],
        )


def _deep_parse_hard_timeout_worker(text: str, resolver, timeout_seconds: float) -> tuple[dict[str, Any], dict[str, Any] | None]:
    if timeout_seconds <= 0:
        return _deep_parse_worker(text, resolver)
    queue: mp.Queue = mp.Queue(1)
    process = mp.Process(target=_deep_parse_process_target, args=(queue, text, resolver))
    started = time.perf_counter()
    process.start()
    process.join(timeout_seconds)
    elapsed_ms = int((time.perf_counter() - started) * 1000)
    if process.is_alive():
        process.terminate()
        process.join(2)
        payload = _parse_error_payload(f"Deep parse exceeded hard timeout of {timeout_seconds}s")
        payload["parser"]["hard_timeout_exceeded"] = True
        payload["parser"]["elapsed_ms"] = elapsed_ms
        return payload, {
            "error_type": "HardDeepParseTimeoutExceeded",
            "message": f"Deep parse exceeded hard timeout of {timeout_seconds}s",
            "elapsed_ms": elapsed_ms,
        }
    if queue.empty():
        payload = _parse_error_payload("Deep parser process exited without a payload")
        payload["parser"]["elapsed_ms"] = elapsed_ms
        return payload, {
            "error_type": "DeepParserProcessNoPayload",
            "message": "Deep parser process exited without a payload",
            "elapsed_ms": elapsed_ms,
        }
    status, payload_or_error = queue.get()
    if status == "ok":
        payload = payload_or_error
        parser = dict(payload.get("parser", {}))
        parser["elapsed_ms"] = elapsed_ms
        parser["parallel_backend"] = "hard-timeout-process"
        payload["parser"] = parser
        return payload, None
    error_type, message = payload_or_error
    payload = _parse_error_payload(str(message))
    payload["parser"]["elapsed_ms"] = elapsed_ms
    return payload, {"error_type": str(error_type), "message": str(message), "elapsed_ms": elapsed_ms}


def _deep_parse_worker(text: str, resolver) -> tuple[dict[str, Any], dict[str, Any] | None]:
    started = time.perf_counter()
    try:
        payload = parse_cobol_deep(text, resolver=resolver)
    except Exception as exc:
        return _parse_error_payload(str(exc)), {"error_type": type(exc).__name__, "message": str(exc)}
    parser = dict(payload.get("parser", {}))
    parser["elapsed_ms"] = int((time.perf_counter() - started) * 1000)
    payload["parser"] = parser
    return payload, None


def _deep_parse_process_target(queue: mp.Queue, text: str, resolver) -> None:
    try:
        queue.put(("ok", parse_cobol_deep(text, resolver=resolver)))
    except Exception as exc:
        queue.put(("error", (type(exc).__name__, str(exc))))


def _parse_error_payload(message: str) -> dict[str, Any]:
    return {
        "program_id": "UNKNOWN",
        "divisions": [],
        "paragraphs": [],
        "data_items": [],
        "calls": [],
        "copies": [],
        "sql": [],
        "cics": [],
        "field_flows": [],
        "counts": {},
        "complexity": 1,
        "parser": {
            "requested": "local-antlr4",
            "effective": "parse-error",
            "version": DEEP_PARSER_VERSION,
            "confidence": 0.0,
            "validation_status": "needs_review",
            "error": message,
        },
    }


def _parse_status(parser: dict[str, Any], issue: dict[str, Any] | None) -> str:
    if issue:
        return "failed"
    effective = str(parser.get("effective") or "")
    if effective == "local-antlr4-full-grammar":
        return "parsed"
    if effective == "antlr4-unavailable":
        return "unsupported"
    return "failed"


def _payload_fact_count(payload: dict[str, Any]) -> int:
    return sum(
        len(payload.get(key, []) or [])
        for key in ("calls", "copies", "sql", "cics", "field_flows", "data_items", "business_rules")
    )


def _evidence_id(run_id: str, entity_kind: str, entity_id: str, evidence: Evidence) -> str:
    return stable_id(
        run_id,
        "evidence",
        entity_kind,
        entity_id,
        evidence.source_path,
        evidence.line_start,
        evidence.evidence_text,
    )
