from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from mip.config import Settings
from mip.discovery.scanner import RepositoryScanner
from mip.models import DiscoveredFile


@dataclass(frozen=True)
class ShardPlan:
    shard_index: int
    shard_count: int
    files: list[str]

    @property
    def file_count(self) -> int:
        return len(self.files)


class DistributedPlanner:
    """Creates deterministic file shards for distributed or parallel analysis.

    This is intentionally infrastructure-neutral: shards can be executed by local
    workers, CI matrix jobs, a queue-based worker pool, or future ADK workflows.
    """

    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self.scanner = RepositoryScanner(settings)

    def plan(self, source_root: Path, shard_count: int) -> list[ShardPlan]:
        if shard_count < 1:
            raise ValueError("shard_count must be >= 1")
        discovered = sorted(self.scanner.scan(source_root), key=lambda item: item.relative_path)
        buckets: list[list[str]] = [[] for _ in range(shard_count)]
        # Greedy balancing by size keeps large copybooks/programs from clustering in one shard.
        sized: list[DiscoveredFile] = sorted(
            discovered, key=lambda item: item.size_bytes, reverse=True
        )
        weights = [0 for _ in range(shard_count)]
        for item in sized:
            idx = min(range(shard_count), key=lambda i: weights[i])
            buckets[idx].append(item.relative_path)
            weights[idx] += item.size_bytes
        return [ShardPlan(index, shard_count, sorted(files)) for index, files in enumerate(buckets)]
