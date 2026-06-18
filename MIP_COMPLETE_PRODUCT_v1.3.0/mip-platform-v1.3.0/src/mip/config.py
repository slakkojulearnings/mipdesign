from __future__ import annotations

import os
from collections.abc import Iterable
from dataclasses import dataclass, field
from pathlib import Path


@dataclass(slots=True)
class Settings:
    db_path: Path = Path("data/mip.db")
    output_dir: Path = Path("output")
    max_file_size_bytes: int = 20 * 1024 * 1024
    include_hidden: bool = False
    follow_symlinks: bool = False
    extract_business_rules: bool = True
    ignored_directories: tuple[str, ...] = field(
        default_factory=lambda: (
            ".git",
            ".venv",
            "node_modules",
            "target",
            "build",
            "dist",
            "__pycache__",
        )
    )

    @classmethod
    def from_env(cls) -> Settings:
        return cls(
            db_path=Path(os.getenv("MIP_DB_PATH", "data/mip.db")),
            output_dir=Path(os.getenv("MIP_OUTPUT_DIR", "output")),
            max_file_size_bytes=int(os.getenv("MIP_MAX_FILE_SIZE_BYTES", str(20 * 1024 * 1024))),
            include_hidden=os.getenv("MIP_INCLUDE_HIDDEN", "false").lower() == "true",
            follow_symlinks=os.getenv("MIP_FOLLOW_SYMLINKS", "false").lower() == "true",
            extract_business_rules=(
                os.getenv("MIP_EXTRACT_BUSINESS_RULES", "true").lower() == "true"
            ),
        )

    def with_overrides(
        self,
        *,
        db_path: Path | None = None,
        output_dir: Path | None = None,
        ignored_directories: Iterable[str] | None = None,
    ) -> Settings:
        return Settings(
            db_path=db_path or self.db_path,
            output_dir=output_dir or self.output_dir,
            max_file_size_bytes=self.max_file_size_bytes,
            include_hidden=self.include_hidden,
            follow_symlinks=self.follow_symlinks,
            extract_business_rules=self.extract_business_rules,
            ignored_directories=(
                tuple(ignored_directories)
                if ignored_directories is not None
                else self.ignored_directories
            ),
        )
