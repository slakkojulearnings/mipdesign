from __future__ import annotations

import atexit
import sys
import tempfile
from pathlib import Path
from typing import Any


sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from mip_intel.api import IntelligenceApi  # noqa: E402


_tmp: tempfile.TemporaryDirectory[str] | None = None
_api: IntelligenceApi | None = None
_run_id: str | None = None


def demo_context() -> dict[str, Any]:
    global _api, _run_id, _tmp
    if _api is None:
        _tmp = tempfile.TemporaryDirectory()
        _api = IntelligenceApi(Path(_tmp.name) / "demo.db")
        _run_id = _api.init_demo()["run_id"]
        atexit.register(_tmp.cleanup)
    return {"api": _api, "run_id": _run_id, "db": _api.repository.db_path}
