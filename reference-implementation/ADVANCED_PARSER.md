# Advanced parser backend — ANTLR COBOL-85 (opt-in)

MIP ships with two parser backends, switchable with one env var:

| `MIP_PARSER` | Backend | Status |
|--------------|---------|--------|
| `default` (or unset) | hand-written grammar parser (`cobol_ast.py`) | ✅ works out of the box, no setup |
| `advanced` | ANTLR COBOL-85 (`cobol_antlr.py`) | ⚙️ opt-in; needs a one-time grammar build |

Both produce the **same** `Unit` shape, so everything downstream (metadata, graph,
lineage, UI) is identical — `advanced` just gives broader language **coverage**
(full statement set, `COPY REPLACING` expansion, nested programs, complete CICS),
which makes field lineage and call resolution complete on messy real-world code.

Check which is active any time:
```bash
curl -s localhost:8000/api/health | python -m json.tool   # -> "parser": {requested, advanced_available, effective}
```
If you request `advanced` but haven't built the grammar, MIP **falls back to default**
automatically (`effective: default`) — it never breaks.

## One-time setup for `advanced`

Requires **Java 11+** and the **ANTLR 4 tool** (this step needs network + Java, which is
why it isn't bundled).

```bash
# 1. ANTLR runtime for Python
uv pip install -e ".[advanced]"            # antlr4-python3-runtime

# 2. ANTLR tool (the generator)
curl -O https://www.antlr.org/download/antlr-4.13.2-complete.jar

# 3. Get a COBOL-85 grammar (e.g. ProLeap) and generate the Python parser into the package
#    grammar: https://github.com/uwol/proleap-cobol-parser  (Cobol85.g4 / Cobol85Preprocessor.g4)
java -jar antlr-4.13.2-complete.jar -Dlanguage=Python3 -o src/mip/grammar Cobol85.g4

# 4. Provide the tree->Unit adapter (src/mip/antlr_adapter.py) implementing:
#       preprocess(text) -> str        # expand COPY / REPLACING
#       to_unit(tree, text) -> Unit    # populate the same fields cobol_ast.Unit uses

# 5. Use it
export MIP_PARSER=advanced
uv run pytest -q                            # the same suite must stay green
```

`cobol_antlr.available()` returns True only when `antlr4`, the generated
`grammar/Cobol85Parser`, and `antlr_adapter` are all importable. The adapter is the only
real work — the rest is generated. Keep the **default** parser as the reference: the test
suite is the contract both backends must satisfy.

> Why it's staged this way: the default parser is correct for the constructs it claims
> and is fully portable (stdlib-only). The advanced backend is for production coverage and
> deliberately isolated so it can't compromise the zero-setup path.
