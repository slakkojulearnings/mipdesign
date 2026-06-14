from __future__ import annotations

from abc import ABC, abstractmethod

from mip.models import DiscoveredFile, ParseResult


class ArtifactParser(ABC):
    @abstractmethod
    def parse(self, source: DiscoveredFile) -> ParseResult:
        """Parse one discovered source artifact."""
