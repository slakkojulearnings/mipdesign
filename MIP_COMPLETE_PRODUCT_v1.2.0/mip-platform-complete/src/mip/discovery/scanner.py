from __future__ import annotations

import hashlib
import logging
from collections.abc import Iterator
from pathlib import Path

from mip.config import Settings
from mip.discovery.classifier import classify
from mip.models import ArtifactType, DiscoveredFile
from mip.utils.text import decode_source

logger = logging.getLogger(__name__)


class RepositoryScanner:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings

    def _should_skip(self, path: Path, root: Path) -> bool:
        try:
            relative_parts = path.relative_to(root).parts
        except ValueError:
            relative_parts = path.parts
        if any(part in self.settings.ignored_directories for part in relative_parts):
            return True
        return not self.settings.include_hidden and any(
            part.startswith(".") for part in relative_parts
        )

    def iter_files(self, root: Path) -> Iterator[Path]:
        for path in root.rglob("*"):
            if self._should_skip(path, root):
                continue
            if path.is_symlink() and not self.settings.follow_symlinks:
                continue
            if path.is_file():
                yield path

    def scan(self, root: Path) -> list[DiscoveredFile]:
        root = root.resolve()
        if not root.exists() or not root.is_dir():
            raise ValueError(f"repository path does not exist or is not a directory: {root}")

        discovered: list[DiscoveredFile] = []
        for path in self.iter_files(root):
            try:
                size = path.stat().st_size
                data = path.read_bytes()
                sha256 = hashlib.sha256(data).hexdigest()
                decoded = decode_source(data)
                if size > self.settings.max_file_size_bytes:
                    classification = classify(path, None, True)
                    reasons = [
                        *classification.reasons,
                        f"file exceeds analysis size limit {self.settings.max_file_size_bytes}",
                    ]
                    discovered.append(
                        DiscoveredFile(
                            absolute_path=path,
                            relative_path=path.relative_to(root).as_posix(),
                            sha256=sha256,
                            size_bytes=size,
                            artifact_type=ArtifactType.BINARY,
                            classification_confidence=0.50,
                            classification_reasons=reasons,
                            encoding=None,
                            is_binary=True,
                            text=None,
                        )
                    )
                    continue

                classification = classify(path, decoded.text, decoded.is_binary)
                discovered.append(
                    DiscoveredFile(
                        absolute_path=path,
                        relative_path=path.relative_to(root).as_posix(),
                        sha256=sha256,
                        size_bytes=size,
                        artifact_type=classification.artifact_type,
                        classification_confidence=classification.confidence,
                        classification_reasons=classification.reasons,
                        encoding=decoded.encoding,
                        is_binary=decoded.is_binary,
                        text=decoded.text,
                    )
                )
            except OSError as exc:
                logger.exception("Failed to scan %s: %s", path, exc)
        return discovered
