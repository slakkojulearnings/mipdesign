# Vendored COBOL ANTLR Parser

This package vendors the COBOL parser files required by `mip-enterprise-intelligence`
so the application can be shipped without depending on `reference-implementation` at
runtime.

Included local files:

- `cobol_antlr.py`
- `antlr_adapter.py`
- `cobol_ast.py`
- `parser_backend.py`
- `grammar/Cobol85*.py`
- `grammar/Cobol85Preprocessor*.py`
- `grammar/*.tokens`

The generated grammar files came from the MIP reference implementation, which generated
ANTLR4 Python files from the ProLeap COBOL-85 grammar. The runtime dependency is declared
in `pyproject.toml` as `antlr4-python3-runtime`.

Runtime behavior:

- Primary path: generated ANTLR grammar via `mip_intel.cobol_antlr.cobol_antlr`.
- Preprocess path: `antlr_adapter.preprocess()` expands `COPY ... REPLACING`.
- Graceful fallback: local `cobol_ast` parser if ANTLR runtime or grammar parsing fails.

Every parser mode is recorded in the emitted asset metadata under `attributes.parser`.
