# MIP Coding Standards

- Python 3.12+ and complete type hints for public code
- Pydantic for external/runtime models; dataclasses for small internal configuration
- explicit enums for artifact, asset, and relationship types
- `pathlib.Path` rather than string path concatenation
- structured, non-sensitive logging
- parameterized SQL only
- no global mutable application state
- no swallowed exceptions; isolate at artifact boundaries and persist issues
- deterministic IDs and stable sort order
- functions should be small enough to test independently
- comments explain mainframe semantics or tradeoffs, not obvious syntax
- generated outputs use UTF-8 unless the interface specification requires another encoding
- credentials come only from environment or secret managers
