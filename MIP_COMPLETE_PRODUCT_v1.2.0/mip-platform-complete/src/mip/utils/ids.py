from __future__ import annotations

from uuid import NAMESPACE_URL, uuid5


def stable_id(namespace: str, *parts: str) -> str:
    normalized = "|".join(part.strip().upper() for part in parts)
    return str(uuid5(NAMESPACE_URL, f"mip:{namespace}:{normalized}"))
