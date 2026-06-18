from __future__ import annotations

import os
from pathlib import Path
from typing import Any

from mip.graph import KnowledgeGraph
from mip.persistence import SQLiteRepository
from mip.services.query import QueryService


def _repository() -> SQLiteRepository:
    repository = SQLiteRepository(Path(os.getenv("MIP_DB_PATH", "data/mip.db")))
    repository.initialize()
    return repository


def get_mip_statistics() -> dict[str, Any]:
    """Return counts and status for the latest MIP repository analysis."""
    return _repository().stats()


def find_program_callers(program_name: str) -> list[dict[str, Any]]:
    """Find programs that directly call the supplied program."""
    return KnowledgeGraph(_repository()).callers(program_name)


def find_program_callees(program_name: str) -> list[dict[str, Any]]:
    """Find programs directly called by the supplied program."""
    return KnowledgeGraph(_repository()).callees(program_name)


def find_jobs_executing_program(program_name: str) -> list[dict[str, Any]]:
    """Find batch jobs that execute the supplied program."""
    return KnowledgeGraph(_repository()).jobs_executing(program_name)


def analyze_asset_impact(asset_name: str, asset_type: str = "PROGRAM") -> dict[str, Any]:
    """Calculate the evidence-backed dependency blast radius of an asset."""
    return KnowledgeGraph(_repository()).impact(asset_name, asset_type)


def ask_mip(question: str) -> dict[str, Any]:
    """Answer a supported deterministic MIP repository question."""
    return QueryService(_repository()).ask(question)


root_agent: Any | None

try:
    from google.adk import Agent

    root_agent = Agent(
        name="mip_repository_assistant",
        model=os.getenv("MIP_ADK_MODEL", "gemini-2.5-flash"),
        instruction=(
            "You are the Mainframe Intelligence Platform assistant. Use tools for all factual "
            "repository answers. Clearly distinguish observed metadata from inference. Never invent "
            "programs, jobs, relationships, or business meanings."
        ),
        tools=[
            get_mip_statistics,
            find_program_callers,
            find_program_callees,
            find_jobs_executing_program,
            analyze_asset_impact,
            ask_mip,
        ],
    )
except ImportError:  # Optional dependency; core MIP remains deterministic and runnable.
    root_agent = None
