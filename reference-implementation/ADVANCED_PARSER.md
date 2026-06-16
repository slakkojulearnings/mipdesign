# Advanced parser backend — ANTLR COBOL-85 (opt-in)

MIP ships with two parser backends, switchable with one env var:

| `MIP_PARSER` | Backend | Status |
|--------------|---------|--------|
| `default` (or unset) | hand-written grammar parser (`cobol_ast.py`) | works out of the box, stdlib-only, no setup |
| `advanced` | ANTLR COBOL-85 (`cobol_antlr.py` + generated `grammar/` + `antlr_adapter.py`) | opt-in; needs a one-time grammar build (Java + network) |

Both produce the **same** `cobol_ast.Unit` shape, so everything downstream (metadata,
graph, lineage, UI) is identical. The `advanced` backend uses the full ProLeap COBOL-85
grammar for broader language **coverage** (the complete statement set, nested programs,
real `COPY … REPLACING` expansion).

Check which is active at any time:
```bash
curl -s localhost:8000/api/health | python -m json.tool   # -> "parser": {requested, advanced_available, effective}
```
If you request `advanced` but haven't built the grammar, MIP **falls back to default**
automatically (`effective: default`) — it never breaks. (Regression-tested:
`tests/test_antlr_backend.py::test_fallback_when_grammar_absent`.)

---

## What is generated-and-tested vs. scaffolded

This repo was built and verified on a machine **with Java 11 + network**, so:

- **Generated and tested NOW** (committed to `src/mip/grammar/`): the ANTLR4 Python parser
  for the ProLeap `Cobol85` and `Cobol85Preprocessor` grammars. With the antlr4 runtime
  installed, `MIP_PARSER=advanced` activates it and the **full ground-truth suite passes on
  the ANTLR backend** — proving parity with the default reference parser:
  ```bash
  MIP_PARSER=advanced python -m pytest tests/test_groundtruth.py tests/test_parser.py tests/test_antlr_backend.py -q
  ```
- **Pure-Python, runnable NOW regardless of the grammar**: `antlr_adapter.preprocess()` —
  the COPY/REPLACING expander + normalizer (see "Adapter contract"). Unit-tested directly
  in `tests/test_antlr_backend.py` (the `test_preprocess_*` tests).

If you are on a machine **without** the generated grammar (e.g. a fresh clone, or no Java),
run the one-time build below. Until then everything still works on the default parser.

---

## One-time setup for `advanced` (one command)

Requires **Java 11+** and network (to fetch the ANTLR tool + ProLeap grammar — that's why
it isn't bundled). The project targets **Python 3.13+**.

```bash
# 1. ANTLR runtime for Python (into a 3.13 environment)
uv pip install -e ".[advanced]"               # antlr4-python3-runtime>=4.13

# 2. Generate the parser into src/mip/grammar/  (fetches ANTLR 4.13.2 + the pinned
#    ProLeap Cobol.g4 / CobolPreprocessor.g4, renames them to Cobol85*, runs ANTLR)
python scripts/gen_grammar.py                 # or: --check to see what's required/present

# 3. Use it
export MIP_PARSER=advanced
python -m pytest tests/test_groundtruth.py tests/test_antlr_backend.py -q   # must stay green
```

`scripts/gen_grammar.py` pins everything for reproducibility:
- ANTLR tool: `antlr-4.13.2-complete.jar`
- Grammar: `uwol/proleap-cobol-parser` @ commit `d1bfe75bdd6d480f70c74c6345bcc02610ac30d3`,
  files `Cobol.g4` (→ `grammar Cobol85`) and `CobolPreprocessor.g4`
  (→ `grammar Cobol85Preprocessor`).

`cobol_antlr.available()` returns True only when `antlr4`, the generated
`grammar/Cobol85Parser`, and `antlr_adapter` are all importable — otherwise False and the
platform uses the default parser.

---

## Adapter contract (`src/mip/antlr_adapter.py`)

The generated parser is mechanical; the adapter is the only hand-written part. Two
functions, both called by `cobol_antlr.parse()`:

### `preprocess(text, resolver=None) -> str`
A real, pure-Python COBOL source normalizer + **COPY/REPLACING expander**. The ProLeap
`Cobol85.g4` main grammar does **not** parse raw COBOL — it expects preprocessor-normalized
text (ProLeap implements this with ~1.5k lines of Java glue). We implement the slice MIP
needs, in Python, so the generated grammar can parse our estate *and* so COPY expansion
works offline. Pipeline:

1. strip indicator-area comment lines (`*` / `/`);
2. drop comment-only paragraphs (`AUTHOR.` / `INSTALLATION.` / `DATE-*` / `SECURITY.` /
   `REMARKS.`) whose free text the grammar can't consume;
3. expand `COPY name [REPLACING ==a== BY ==b== …]` by inlining the copybook (recursive,
   cycle-guarded). **Pseudo-text** operands (`==…==`) match as literal substrings; **bare
   words** match on COBOL-word boundaries. Unresolved COPY → statement removed (the COPY
   *edge* is still recorded, so nothing is dropped from the metadata — degrade gracefully);
4. fold each `EXEC SQL|CICS … END-EXEC` into the single tagged line the grammar matches
   (`*>EXECSQL …` / `*>EXECCICS …`, rules `execSqlStatement` / `execCicsStatement`), body
   preserved verbatim.

`resolver(name) -> copybook_text | None` locates copybooks; `antlr_adapter.default_resolver(estate_root)`
searches `COPYLIB/COPYBOOK/COPY/CPY`. When `resolver` is omitted, COPY statements are
removed (edge still recovered downstream).

### `to_unit(tree, text, pre=None) -> cobol_ast.Unit`
Walks the ANTLR `startRule` parse tree into the canonical `Unit`. Rule-context → field map:

| Unit field | Source |
|------------|--------|
| `program_id` | `ProgramIdParagraphContext` → `ProgramNameContext` |
| `divisions` | presence of `Identification/Environment/Data/ProcedureDivisionContext` |
| `paragraphs` | `ParagraphContext` → `ParagraphNameContext` |
| `data_items` | `DataDescriptionEntryFormat1Context` (level + `DataNameContext`; PIC from the original source slice via `cobol_ast._PIC`) |
| `calls` | `CallStatementContext` + `MoveToStatementContext` — literal → static/`confirmed`; variable resolved by **constant propagation** over MOVEs → `resolved`/`inferred` (with `via`); else `dynamic`/`needs_review` |
| `copies`, `sql`, `cics`, `field_flows` | recovered by reusing the **verified `cobol_ast`** extractors on the original text |
| `counts`, `complexity` | recomputed from the original text, identically to default |

**Honesty note.** EXEC SQL table edges + host-var lineage, EXEC CICS edges, and the COPY
edges are constructs the ProLeap main grammar captures only as opaque token lines. Rather
than fork a second, unverified SQL/CICS extractor, the adapter reuses the proven
`cobol_ast` helpers on the original source for those fields. AST structure and CALL
resolution **are** derived from the ANTLR tree — that is where the full grammar adds
coverage. The result is byte-for-byte parity with the default parser on the whole sample
estate (`tests/test_antlr_backend.py::test_antlr_parity_with_default_when_grammar_present`).

> Why staged this way: the default parser is correct for the constructs it claims and is
> fully portable (stdlib-only); it stays the **reference / source of truth**. The advanced
> backend is for production coverage and is deliberately isolated so it can't compromise
> the zero-setup path. The shared test suite is the contract both backends must satisfy.

---

## Seeing the difference (default vs advanced)

A frequent question: *"both backends give the same output — what does advanced buy me?"*
On clean COBOL inside the common subset they are **identical by design** (the parity test
above enforces it). The advanced backend's distinct value is its **preprocessing stage** —
`COPY ... REPLACING` expansion, `EXEC` folding, comment-paragraph stripping — which only
changes the extracted facts when a copybook **resolver** supplies the copybook text.

`scripts/parser_compare.py` makes this visible on a worked example
(`examples/advanced_parser/`), where the called program name is hidden inside a copybook
behind a `REPLACING` placeholder:

```
uv run python scripts/parser_compare.py examples/advanced_parser/CARDADV \
    --copylib examples/advanced_parser
```

- **default** and **advanced (raw)** → no CALL (parity): the copybook is not expanded.
- **advanced + resolver** → `CALL 'REALSUB'` (confirmed): COPY `REPLACING ==:SUBPGM:== BY
  ==REALSUB==` inlines `CALL ':SUBPGM:'` from the copybook and rewrites it, so the call
  edge the default parser cannot see is recovered.

> Note (honest): the production `parse(text)` path does **not** pass a resolver, so today
> the toggle does not change results on the sample estate. Wiring the copybook resolver
> into the pipeline (so real estates expand their `COPY ... REPLACING`) is the next step
> that turns the advanced backend's coverage into a visible production gain. The
> `examples/` member lives outside `sample_estate/` so it does not affect the ground-truth
> counts the test suite asserts.
