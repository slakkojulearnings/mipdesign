from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from mip.config import Settings
from mip.discovery import RepositoryScanner
from mip.models import ArtifactType
from mip.persistence import SQLiteRepository
from mip.semantics import CobolSemanticAnalyzer
from mip.services.intelligence_suite import IntelligenceSuite
from mip.services.jcl_expansion import EnterpriseJclExpander
from mip.services.pipeline import AnalysisPipeline


class AdvancedAnalysisPipeline:
    """Runs repository analysis plus compiler-oriented and intelligence stages."""

    def __init__(self, settings: Settings) -> None:
        self.settings = settings

    def analyze(
        self,
        source_root: Path,
        copybook_dirs: list[Path] | None = None,
        proclib_dirs: list[Path] | None = None,
        defines: set[str] | None = None,
        jcl_symbols: dict[str, str] | None = None,
    ) -> dict[str, Any]:
        source_root = source_root.resolve()
        summary = AnalysisPipeline(self.settings).analyze(source_root)
        scanner = RepositoryScanner(self.settings)
        discovered = scanner.scan(source_root)
        advanced_root = self.settings.output_dir / summary.run_id / "advanced"
        cobol_root = advanced_root / "cobol"
        jcl_root = advanced_root / "jcl"
        cobol_root.mkdir(parents=True, exist_ok=True)
        jcl_root.mkdir(parents=True, exist_ok=True)

        default_copybooks = [
            source_root / name
            for name in ("copybooks", "cpy", "copy", "copysrc")
            if (source_root / name).exists()
        ]
        default_proclib = [
            source_root / name
            for name in ("proclib", "proc", "jcllib")
            if (source_root / name).exists()
        ]
        cobol_analyzer = CobolSemanticAnalyzer(
            (copybook_dirs or []) + default_copybooks, defines=defines
        )
        jcl_expander = EnterpriseJclExpander((proclib_dirs or []) + default_proclib)

        cobol_outputs: list[str] = []
        jcl_outputs: list[str] = []
        issues: list[dict[str, Any]] = []
        for item in discovered:
            if item.artifact_type == ArtifactType.COBOL:
                result = cobol_analyzer.analyze_file(item.absolute_path)
                output = (
                    cobol_root
                    / f"{item.relative_path.replace('/', '__').replace('\\\\', '__')}.json"
                )
                output.parent.mkdir(parents=True, exist_ok=True)
                output.write_text(json.dumps(result, indent=2, default=str), encoding="utf-8")
                cobol_outputs.append(str(output))
                issues.extend(result.get("issues", []))
            elif item.artifact_type == ArtifactType.JCL:
                result = jcl_expander.expand_file(item.absolute_path, jcl_symbols)
                output = (
                    jcl_root / f"{item.relative_path.replace('/', '__').replace('\\\\', '__')}.json"
                )
                output.parent.mkdir(parents=True, exist_ok=True)
                output.write_text(json.dumps(result, indent=2, default=str), encoding="utf-8")
                jcl_outputs.append(str(output))
                issues.extend(result.get("issues", []))

        repository = SQLiteRepository(self.settings.db_path)
        intelligence = IntelligenceSuite(repository, summary.run_id).generate(
            advanced_root / "intelligence"
        )
        manifest: dict[str, Any] = {
            "summary": summary.model_dump(),
            "advanced": {
                "cobol_files": len(cobol_outputs),
                "jcl_files": len(jcl_outputs),
                "issues": issues,
                "cobol_outputs": cobol_outputs,
                "jcl_outputs": jcl_outputs,
                "intelligence": intelligence,
            },
        }
        manifest_path = advanced_root / "advanced-analysis-manifest.json"
        manifest_path.write_text(json.dumps(manifest, indent=2, default=str), encoding="utf-8")
        manifest["manifest_path"] = str(manifest_path)
        return manifest
