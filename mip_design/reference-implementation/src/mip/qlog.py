"""Q&A reasoning log.

Every query is appended — question, intent, thought process, evidence, the reason for
the conclusion, and the response — to BOTH:
  - question_log.md    (human-readable audit trail, as requested)
  - question_log.jsonl (machine-readable mirror the React app reads via /api/log)

This operationalizes Principle 3 (Explainability & Auditability): answers are never a
black box; the reasoning and evidence behind each one are recorded and reviewable.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

# Logs live next to the app so they're easy to find / leverage.
_LOG_DIR = Path(__file__).resolve().parents[4] / "mip_design" / "app"
MD_PATH = _LOG_DIR / "question_log.md"
JSONL_PATH = _LOG_DIR / "question_log.jsonl"

_MD_HEADER = (
    "# MIP Q&A Log\n\n"
    "Auto-generated audit trail of every question asked, the reasoning, the evidence,\n"
    "and the answer. Append-only. Viewable in the React app under **Q&A Log**.\n"
)


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _render_md(e: dict) -> str:
    lines = [f"\n## {e['discovered_at']} — {e['question']}", f"**Intent:** `{e['intent']}`"]
    if e.get("program"):
        lines.append(f"**Program:** `{e['program']}`")
    lines.append("\n**Thought process:**")
    lines += [f"{i}. {s}" for i, s in enumerate(e.get("thought_process", []), 1)]
    if e.get("evidence"):
        lines.append("\n**Evidence:**")
        for ev in e["evidence"]:
            src = ev.get("source_evidence") or "—"
            vs = ev.get("validation_status", "")
            conf = ev.get("confidence", "")
            lines.append(f"- `{ev.get('source_id')} {ev.get('rel_type')} {ev.get('target_id')}`"
                         f"  — {src} ({vs}, conf {conf})")
    lines.append(f"\n**Reason:** {e.get('reason', '')}")
    lines.append(f"\n**Response:** `{json.dumps(e.get('response'))}`")
    lines.append("\n---")
    return "\n".join(lines) + "\n"


def log_entry(entry: dict) -> dict:
    """Append one reasoning trace to both logs. Returns the stored entry."""
    _LOG_DIR.mkdir(parents=True, exist_ok=True)
    entry = {"discovered_at": _now(), **entry}

    if not MD_PATH.exists():
        MD_PATH.write_text(_MD_HEADER, encoding="utf-8")
    with MD_PATH.open("a", encoding="utf-8") as f:
        f.write(_render_md(entry))

    with JSONL_PATH.open("a", encoding="utf-8") as f:
        f.write(json.dumps(entry) + "\n")
    return entry


def read_entries(limit: int = 100) -> list[dict]:
    """Most-recent-first structured entries for the UI."""
    if not JSONL_PATH.exists():
        return []
    entries = [json.loads(line) for line in JSONL_PATH.read_text(encoding="utf-8").splitlines() if line.strip()]
    return list(reversed(entries))[:limit]


def raw_md() -> str:
    return MD_PATH.read_text(encoding="utf-8") if MD_PATH.exists() else _MD_HEADER
