from __future__ import annotations

import logging
from collections.abc import Iterable
from pathlib import Path

from mip.config import Settings
from mip.discovery import RepositoryScanner
from mip.models import (
    AnalysisSummary,
    AssetCandidate,
    ParseIssue,
    RelationshipCandidate,
)
from mip.parsers import ParserRegistry
from mip.persistence import SQLiteRepository
from mip.services.exporter import MemoryExporter
from mip.services.report import ReportGenerator

logger = logging.getLogger(__name__)


class AnalysisPipeline:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self.repository = SQLiteRepository(settings.db_path)
        self.scanner = RepositoryScanner(settings)
        self.parsers = ParserRegistry()

    def analyze(self, source_root: Path) -> AnalysisSummary:
        self.repository.initialize()
        source_root = source_root.resolve()
        run_id = self.repository.create_run(str(source_root))
        source_file_ids: dict[str, str] = {}
        asset_ids: dict[tuple[str, str], str] = {}
        relationship_candidates: list[RelationshipCandidate] = []
        files_parsed = 0

        try:
            discovered = self.scanner.scan(source_root)
            for source in discovered:
                source_file_id = self.repository.insert_source_file(run_id, source)
                source_file_ids[source.relative_path] = source_file_id
                parser = self.parsers.get(source.artifact_type)
                if parser is None:
                    self.repository.mark_source_status(source_file_id, "SKIPPED")
                    continue

                try:
                    result = parser.parse(source)
                    files_parsed += 1
                    self.repository.mark_source_status(source_file_id, "PARSED")
                except Exception as exc:  # isolate individual artifact failures
                    logger.exception("Parser failed for %s", source.relative_path)
                    self.repository.mark_source_status(source_file_id, "FAILED")
                    self.repository.insert_issue(
                        run_id,
                        source_file_id,
                        ParseIssue(
                            severity="ERROR",
                            message=f"Unhandled parser error: {exc}",
                            source_path=source.relative_path,
                        ),
                    )
                    continue

                for issue in result.issues:
                    self.repository.insert_issue(run_id, source_file_id, issue)
                for candidate in result.assets:
                    source_id = source_file_ids.get(candidate.source_path or source.relative_path)
                    asset_id = self.repository.upsert_asset(run_id, candidate, source_id)
                    asset_ids[(candidate.asset_type.value, candidate.technical_name.upper())] = (
                        asset_id
                    )
                    for evidence in candidate.evidence:
                        self.repository.insert_evidence(run_id, "ASSET", asset_id, evidence)
                relationship_candidates.extend(result.relationships)

            self._persist_relationships(
                run_id,
                relationship_candidates,
                asset_ids,
                source_file_ids,
            )
            self.repository.complete_run(run_id)

            run_output = self.settings.output_dir / run_id
            run_output.mkdir(parents=True, exist_ok=True)
            MemoryExporter(self.repository).export(run_output / "memory", run_id)
            report_path = ReportGenerator(self.repository).generate(run_output, run_id)
            stats = self.repository.stats(run_id)
            return AnalysisSummary(
                run_id=run_id,
                source_root=str(source_root),
                files_discovered=len(discovered),
                files_parsed=files_parsed,
                files_unknown=int(stats["run"]["unknown_count"]),
                assets=int(stats["run"]["asset_count"]),
                relationships=int(stats["run"]["relationship_count"]),
                parse_issues=int(stats["run"]["issue_count"]),
                database=str(self.settings.db_path),
                report_path=str(report_path),
            )
        except Exception:
            logger.exception("Analysis run failed")
            self.repository.complete_run(run_id, status="FAILED")
            raise

    def _persist_relationships(
        self,
        run_id: str,
        candidates: Iterable[RelationshipCandidate],
        asset_ids: dict[tuple[str, str], str],
        source_file_ids: dict[str, str],
    ) -> None:
        for candidate in candidates:
            source_key = (candidate.source_type.value, candidate.source_name.upper())
            target_key = (candidate.target_type.value, candidate.target_name.upper())
            source_id = asset_ids.get(source_key)
            if source_id is None:
                source_asset = AssetCandidate(
                    asset_type=candidate.source_type,
                    technical_name=candidate.source_name,
                    confidence=candidate.confidence,
                )
                source_id = self.repository.upsert_asset(
                    run_id, source_asset, None, placeholder=True
                )
                asset_ids[source_key] = source_id
            target_id = asset_ids.get(target_key)
            if target_id is None:
                target_asset = AssetCandidate(
                    asset_type=candidate.target_type,
                    technical_name=candidate.target_name,
                    confidence=candidate.confidence,
                )
                target_id = self.repository.upsert_asset(
                    run_id, target_asset, None, placeholder=True
                )
                asset_ids[target_key] = target_id

            relationship_id = self.repository.insert_relationship(
                run_id, candidate, source_id, target_id
            )
            for evidence in candidate.evidence:
                self.repository.insert_evidence(run_id, "RELATIONSHIP", relationship_id, evidence)
