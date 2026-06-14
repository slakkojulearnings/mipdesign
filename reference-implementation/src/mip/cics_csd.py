"""CICS resource-definition (CSD / RDO / DFHCSDUP) parser.

Maps online **transactions to their entry programs** — the online equivalent of a JCL
job naming its driver. `DEFINE TRANSACTION(AUTH) PROGRAM(AUTHTRAN)` becomes an edge
`transaction:AUTH --STARTS--> program:AUTHTRAN`, so MIP knows which transaction triggers
which program (and the program stays the root-driver, like a job's EXEC PGM=).
"""

from __future__ import annotations

import re

from .records import Edge, Evidence

_DEFINE = re.compile(r"(?is)DEFINE\s+TRANSACTION\s*\(\s*([A-Z0-9$#@]+)\s*\)(.*?)(?=DEFINE\s|\Z)")
_PROGRAM = re.compile(r"(?i)PROGRAM\s*\(\s*([A-Z0-9$#@]+)\s*\)")


def is_csd(text: str) -> bool:
    up = text.upper()
    return "DEFINE TRANSACTION" in up or "DEFINE PROGRAM" in up or "DFHCSDUP" in up


def extract_edges(text: str, rel_path: str) -> list[Edge]:
    edges: list[Edge] = []
    for m in _DEFINE.finditer(text):
        txn, body = m.group(1).upper(), m.group(2)
        pm = _PROGRAM.search(body)
        if not pm:
            continue
        line = text.count("\n", 0, m.start()) + 1
        edges.append(Edge.build("transaction", txn, "STARTS", "program", pm.group(1).upper(),
                                Evidence(source_evidence=f"{rel_path}:{line}",
                                         discovery_method="cics-csd",
                                         confidence=1.0, validation_status="confirmed")))
    return edges
