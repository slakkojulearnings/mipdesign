from __future__ import annotations

from dataclasses import dataclass

from .repositories import SQLiteGraphRepository


@dataclass(frozen=True)
class StorageConfig:
    backend: str = "sqlite"
    dsn: str = "data/mip-intel.db"

    @classmethod
    def from_dsn(cls, dsn: str) -> "StorageConfig":
        lowered = dsn.lower()
        if lowered.startswith(("postgresql://", "postgres://")):
            return cls(backend="postgresql", dsn=dsn)
        return cls(backend="sqlite", dsn=dsn)


def create_repository(config: StorageConfig) -> SQLiteGraphRepository:
    backend = config.backend.lower()
    if backend == "sqlite":
        return SQLiteGraphRepository(config.dsn)
    if backend in {"postgres", "postgresql"}:
        raise NotImplementedError(
            "PostgreSQL storage is a planned adapter; keep using repository interfaces and SQLite for v1."
        )
    raise ValueError(f"unsupported storage backend: {config.backend}")
