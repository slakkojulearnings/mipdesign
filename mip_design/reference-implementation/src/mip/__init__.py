"""MIP v0.1 reference implementation — the runnable spine.

Inventory -> parse (COBOL/JCL) -> SQLite metadata store -> queries.
Stdlib-only (sqlite3 + argparse + dataclasses) so it runs on any machine
with just Python; no pip install or network required.

The canonical metadata spec lives in ../../01-metadata-model/ (Pydantic models +
schema.sql); this package mirrors that schema and uses lightweight dataclasses at
runtime to stay dependency-free and portable.
"""

__version__ = "0.1.0"
