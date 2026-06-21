"""ANTLR COBOL-85 → mip.cobol_ast.Unit adapter (the only hand-written part of the
advanced backend).

Two public functions, both called by `cobol_antlr.parse()`:

  preprocess(text, resolver=None) -> str
      A *real*, pure-Python COBOL source normalizer + COPY/REPLACING expander.
      The ProLeap `Cobol85.g4` main grammar does NOT parse raw COBOL: it expects
      preprocessor-normalized text (ProLeap ships ~1.5k lines of Java glue —
      `CobolPreprocessorImpl` — to do this). We re-implement the slice that matters for
      MIP, in Python, so the generated grammar can parse our estate AND so COPY /
      REPLACING expansion (genuinely useful, fully testable) works offline today:
        * drop comment lines (`*` / `/` in the indicator area) and the comment-only
          paragraphs (AUTHOR / INSTALLATION / DATE-* / SECURITY / REMARKS) whose free
          text the main grammar can't consume;
        * expand `COPY name [REPLACING ==a== BY ==b== ...]` by inlining the copybook,
          applying pseudo-text / token REPLACING (this is the deliverable expander);
        * fold each `EXEC SQL … END-EXEC` / `EXEC CICS … END-EXEC` block into the single
          tagged line (`*>EXECSQL …` / `*>EXECCICS …`) the ProLeap main grammar matches
          as EXECSQLLINE / EXECCICSLINE (rules `execSqlStatement` / `execCicsStatement`).

  to_unit(tree, text) -> mip.cobol_ast.Unit
      Walk the ANTLR parse tree and fill the SAME Unit fields the default parser fills.

Honesty note (Principle 1 / honesty mandate): a handful of facts that ProLeap captures
only as opaque token lines — EXEC SQL table edges + host-var lineage, EXEC CICS edges,
and the COPY edges themselves — are recovered by reusing the *verified* `cobol_ast`
helpers on the original source text, not re-implemented here. That keeps the advanced
backend at parity with the reference parser (the test suite is the contract) instead of
forking a second, unverified SQL/CICS extractor. AST structure (program-id, divisions,
paragraphs, data items) and CALL resolution (incl. constant propagation) ARE recovered
from the ANTLR tree — that is where the full grammar adds coverage.

Context-class names below are the ANTLR4-Python3 classes generated from the ProLeap
rule names (e.g. rule `programIdParagraph` -> `ProgramIdParagraphContext`, accessor
`.programIdParagraph()`). See scripts/gen_grammar.py for generation.
"""

from __future__ import annotations

import re
from pathlib import Path

from . import cobol_ast
from .cobol_ast import Unit

# ---------------------------------------------------------------------------
# COPY resolution
# ---------------------------------------------------------------------------
# Copybook directory names searched, relative to the source file's estate root.
_COPY_DIRS = ("COPYLIB", "COPYBOOK", "COPY", "CPY")


def default_resolver(estate_root: Path | None):
    """Return a `resolver(name) -> str | None` that finds a copybook by name under the
    estate's COPY directories. `None` (no root) -> a resolver that finds nothing, so COPY
    statements are simply removed (the COPY *edge* is still recorded from the raw text)."""
    def resolve(name: str) -> str | None:
        if estate_root is None:
            return None
        for d in _COPY_DIRS:
            for cand in (estate_root / d / name, estate_root / d / f"{name}.cpy",
                         estate_root / d / f"{name}.CPY"):
                if cand.is_file():
                    return cand.read_text(encoding="utf-8", errors="replace")
        return None
    return resolve


# ---------------------------------------------------------------------------
# preprocess()  — normalizer + COPY/REPLACING expander (pure Python, testable now)
# ---------------------------------------------------------------------------
_COMMENT_PARAGRAPHS = ("AUTHOR", "INSTALLATION", "DATE-WRITTEN", "DATE-COMPILED",
                       "SECURITY", "REMARKS")
# A DIVISION or SECTION header line, e.g. `ENVIRONMENT DIVISION.` / `FILE SECTION.`
_DIV_SECT_RE = re.compile(r"(?i)^[A-Z0-9][A-Z0-9-]*\s+(DIVISION|SECTION)\b")
# `COPY name [ (REPLACING ==x== BY ==y== [...]) ] .`   (REPLACING is optional)
_COPY_STMT = re.compile(
    r"(?is)\bCOPY\s+([A-Z0-9][A-Z0-9-]*)"
    r"(?:\s+REPLACING\s+(.*?))?\s*\.")
# one REPLACING pair:  ==pseudo== BY ==text==   |   word BY word   |   :tag: BY ...
_REPL_PAIR = re.compile(
    r"(?is)(==.*?==|:[^:]+:|'[^']*'|\"[^\"]*\"|[^\s.]+)\s+BY\s+"
    r"(==.*?==|:[^:]+:|'[^']*'|\"[^\"]*\"|[^\s.]+)")


def _strip_pseudo(tok: str) -> str:
    """Strip ProLeap pseudo-text delimiters (==…==) / pseudo-tag colons from a REPLACING
    operand, leaving the literal text to match/insert."""
    t = tok.strip()
    if t.startswith("==") and t.endswith("=="):
        return t[2:-2]
    if len(t) >= 2 and t[0] == ":" and t[-1] == ":":
        return t[1:-1]
    return t


def _is_pseudo(tok: str) -> bool:
    """A REPLACING operand written as pseudo-text (==…==) or a :tag: placeholder. Pseudo-
    text matches as a literal substring (so ==PREFIX== rewrites PREFIX inside PREFIX-REC);
    a bare COBOL word matches only on word boundaries (PREFIX won't touch PREFIXED)."""
    t = tok.strip()
    return (t.startswith("==") and t.endswith("==")) or (
        len(t) >= 2 and t[0] == ":" and t[-1] == ":")


def _parse_replacing(spec: str) -> list[tuple[str, str, bool]]:
    """`==A== BY ==B==  ==C== BY ==D==` -> [(A,B,pseudo?),…]; longest source first so a
    longer operand can't be partially clobbered by a shorter one."""
    pairs = [(_strip_pseudo(a), _strip_pseudo(b), _is_pseudo(a))
             for a, b in _REPL_PAIR.findall(spec or "")]
    return sorted(pairs, key=lambda p: len(p[0]), reverse=True)


def _apply_replacing(text: str, pairs: list[tuple[str, str, bool]]) -> str:
    """Apply COPY ... REPLACING substitutions to copybook text. Pseudo-text operands are
    replaced as literal substrings; bare COBOL-word operands are replaced on word
    boundaries (so they don't rewrite a larger name that merely contains them)."""
    for src, dst, pseudo in pairs:
        if not src:
            continue
        if pseudo:
            text = text.replace(src, dst)
        else:
            text = re.sub(rf"(?<![\w-]){re.escape(src)}(?![\w-])", dst, text)
    return text


def expand_copy(text: str, resolver, _seen: frozenset[str] = frozenset(),
                _depth: int = 0) -> str:
    """Inline every `COPY name [REPLACING …]` using `resolver(name) -> text|None`.

    - Recursive (copybooks may COPY copybooks); guards against cycles via `_seen` and a
      depth cap so a self-referential library can't loop forever.
    - Unresolved COPY (resolver returns None) -> the statement is removed so the grammar
      can parse; the COPY *edge* is still recorded by to_unit() from the original text,
      so nothing is dropped from the metadata (degrade gracefully, Principle 2)."""
    if _depth > 25:
        return text

    def repl(m: re.Match) -> str:
        name = m.group(1).upper()
        body = resolver(name) if resolver else None
        if body is None:
            return ""                                   # unresolved -> remove statement
        if name in _seen:                               # cycle guard
            return ""
        pairs = _parse_replacing(m.group(2))
        if pairs:
            body = _apply_replacing(body, pairs)
        body = _strip_comment_lines(body)               # copybooks carry comments too
        return expand_copy(body, resolver, _seen | {name}, _depth + 1)

    return _COPY_STMT.sub(repl, text)


def _strip_comment_lines(text: str) -> str:
    """Remove fixed-format comment lines (indicator-area `*` or `/`). Blank the line
    (keep the newline) so downstream line counts stay stable for messages."""
    return "\n".join("" if cobol_ast._is_comment(l) else l for l in text.splitlines())


def _is_comment_paragraph_header(head: str) -> bool:
    """True if `head` (stripped, upper) begins a comment-only IDENTIFICATION paragraph."""
    return any(head == p or head.startswith(p + ".") or head.startswith(p + " ")
               for p in _COMMENT_PARAGRAPHS)


def _is_comment_entry_terminator(head: str) -> bool:
    """True if `head` begins a new COBOL construct that ends a comment-entry's free text:
    a DIVISION/SECTION header or the PROGRAM-ID paragraph. (Other comment paragraphs are
    handled separately.) The comment-entry VALUE of e.g. DATE-WRITTEN runs until one of
    these — NOT until the first period, since the header line itself ends with a period."""
    return bool(_DIV_SECT_RE.match(head)) or head == "PROGRAM-ID" or head.startswith("PROGRAM-ID.")


def _strip_comment_paragraphs(text: str) -> str:
    """Drop IDENTIFICATION DIVISION comment-only paragraphs (AUTHOR / INSTALLATION /
    DATE-WRITTEN / DATE-COMPILED / SECURITY / REMARKS), HEADER AND free-text VALUE. The
    ProLeap main grammar models these as `commentEntry` consumed by the preprocessor; we
    remove the whole entry so the grammar reaches PROGRAM-ID/DATA. The entry's value can
    span lines and is NOT delimited by a period (the header `DATE-WRITTEN.` already ends in
    one), so we skip until the next comment paragraph, PROGRAM-ID, or DIVISION/SECTION."""
    out = []
    skip = False
    for line in text.splitlines():
        head = line.strip().upper()
        if _is_comment_paragraph_header(head):          # start (or restart) skipping
            skip = True
            continue                                    # drop the header line itself
        if skip:
            if _is_comment_entry_terminator(head):      # next real construct -> keep it
                skip = False
                out.append(line)
            # else: still inside the comment-entry's free text -> drop the line
            continue
        out.append(line)
    return "\n".join(out)


_EXEC_BLOCK = re.compile(r"(?is)\bEXEC\s+(SQL|CICS)\b(.*?)\bEND-EXEC\b\s*\.?")


def _fold_exec_blocks(text: str) -> str:
    """Fold each `EXEC SQL|CICS … END-EXEC` into the single tagged line the ProLeap main
    grammar matches (EXECSQLLINE / EXECCICSLINE): `*>EXECSQL <one-line body>`. Newlines
    inside the block are collapsed (the grammar token is single-line) but the body text is
    preserved verbatim so to_unit() can still mine table / host-var / CICS facts from it."""
    def repl(m: re.Match) -> str:
        kind = m.group(1).upper()
        body = " ".join(m.group(2).split())             # collapse internal whitespace
        return f"*>EXEC{kind} {body}}}"                  # '}' is a valid EXEC*LINE terminator
    return _EXEC_BLOCK.sub(repl, text)


def preprocess(text: str, resolver=None) -> str:
    """Normalize raw COBOL into text the generated ProLeap `Cobol85` grammar can parse.

    Pipeline (all pure-Python, runs offline):
        comment lines -> comment paragraphs -> COPY/REPLACING expansion -> EXEC folding.
    `resolver(name) -> copybook_text | None`; default (None) removes COPY statements (edge
    still recorded downstream). Returns the transformed source string."""
    text = _strip_comment_lines(text)
    text = _strip_comment_paragraphs(text)
    text = expand_copy(text, resolver)
    text = _fold_exec_blocks(text)
    if not text.endswith("\n"):
        text += "\n"
    return text


# ---------------------------------------------------------------------------
# to_unit()  — walk the ANTLR parse tree into the canonical Unit
# ---------------------------------------------------------------------------
def _txt(ctx) -> str:
    """Original (concatenated) token text of a parse-tree node, upper-cased."""
    return ctx.getText().upper() if ctx is not None else ""


def _line(ctx) -> int:
    """1-based source line of a node's first token (best-effort)."""
    try:
        return ctx.start.line
    except Exception:
        return 0


def _find_all(node, ctx_type, out=None):
    """Depth-first collect of every descendant whose class name == ctx_type (a string).
    String match (not isinstance) keeps this resilient to the generated module identity
    and avoids importing the giant parser module here."""
    if out is None:
        out = []
    if type(node).__name__ == ctx_type:
        out.append(node)
    for i in range(getattr(node, "getChildCount", lambda: 0)()):
        _find_all(node.getChild(i), ctx_type, out)
    return out


def _literal_value(ctx) -> str | None:
    """If a node ultimately is a quoted alphanumeric literal, return its unquoted value."""
    t = ctx.getText() if ctx is not None else ""
    if len(t) >= 2 and t[0] in "'\"" and t[-1] == t[0]:
        return t[1:-1]
    return None


def _source_slice(ctx, src: str) -> str:
    """The original (un-concatenated) source text spanned by a node — needed where
    `getText()` would glue tokens together and lose layout (e.g. a PIC clause)."""
    try:
        return src[ctx.start.start: ctx.stop.stop + 1]
    except Exception:
        return ctx.getText()


def _section_for_line(text: str, line_no: int) -> str | None:
    section = None
    for current_line, line in enumerate(text.splitlines(), 1):
        if current_line >= line_no:
            return section
        match = cobol_ast._SECTION.match(line)
        if match:
            section = match.group(1).upper()
    return section


def to_unit(tree, text: str, pre: str | None = None) -> Unit:
    """Walk a `startRule` parse tree (+ the original `text`) into a cobol_ast.Unit with the
    same shape the default parser produces. ANTLR-derived: program_id, divisions,
    paragraphs, data_items, calls (with constant-propagation resolution). Reused from the
    verified cobol_ast helpers on the original text (parity, honesty): copies, sql, cics,
    field_flows. Counts/complexity recomputed from the original text exactly as default.

    `pre` is the preprocessed source the tree was built from (parse-tree token offsets
    index into it). When omitted we re-run preprocess(text) so slicing stays correct."""
    if pre is None:
        pre = preprocess(text)
    u = Unit()

    # ---- program_id (rule programIdParagraph: PROGRAM-ID. programName …) ----
    pid_nodes = _find_all(tree, "ProgramIdParagraphContext")
    if pid_nodes:
        name = _find_all(pid_nodes[0], "ProgramNameContext")
        if name:
            u.program_id = _txt(name[0]).strip(". ")
    if u.program_id is None:                          # fallback to regex (degrade)
        m = cobol_ast._PROGRAM_ID.search(text)
        u.program_id = m.group(1).upper() if m else None

    # ---- divisions present (rule contexts) ----
    div_map = (("IdentificationDivisionContext", "IDENTIFICATION"),
               ("EnvironmentDivisionContext", "ENVIRONMENT"),
               ("DataDivisionContext", "DATA"),
               ("ProcedureDivisionContext", "PROCEDURE"))
    u.divisions = [label for ctx, label in div_map if _find_all(tree, ctx)]

    # ---- paragraphs (rule paragraph -> paragraphName) ----
    for para in _find_all(tree, "ParagraphContext"):
        names = _find_all(para, "ParagraphNameContext")
        if names:
            nm = _txt(names[0]).strip(". ")
            if nm and nm not in cobol_ast._NON_PARA:
                u.paragraphs.append(nm)

    # ---- data items (rule dataDescriptionEntryFormat1: level dataName … PIC …) ----
    # level + name come from the typed child nodes (clean); the PIC text comes from the
    # original source slice (getText() would glue 'PIC' 'S9' '(' '4' ')' together).
    for d in _find_all(tree, "DataDescriptionEntryFormat1Context"):
        level_m = re.match(r"\s*(\d{1,2})", d.getText())
        names = _find_all(d, "DataNameContext")
        if not level_m or not names:
            continue
        # PIC from the original entry slice using the SAME regex the default parser uses,
        # so the captured string (incl. any trailing '.') is byte-identical to default.
        entry = _source_slice(d, pre)
        pm = cobol_ast._PIC.search(entry)
        pic = pm.group(1) if pm else None
        redefines = cobol_ast._REDEFINES.search(entry)
        occurs = cobol_ast._OCCURS.search(entry)
        depending = cobol_ast._DEPENDING.search(entry)
        usage = cobol_ast._USAGE.search(entry)
        value = cobol_ast._VALUE.search(entry)
        level = int(level_m.group(1))
        u.data_items.append({
            "level": level,
            "name": _txt(names[0]).strip().upper(),
            "pic": pic,
            "line": _line(d),
            "section": _section_for_line(text, _line(d)),
            "redefines": redefines.group(1).upper() if redefines else None,
            "occurs": int(occurs.group(1)) if occurs else None,
            "occurs_to": int(occurs.group(2)) if occurs and occurs.group(2) else None,
            "depending_on": depending.group(1).upper() if depending else None,
            "usage": usage.group(1).upper() if usage else None,
            "value": value.group(1).strip().rstrip(".") if value else None,
            "condition_name": level == 88,
        })

    # ---- CALLs with constant propagation (rule callStatement: CALL (identifier|literal)) ----
    _walk_calls(tree, u)

    # ---- COPY / SQL / CICS / field-flows: reuse the verified cobol_ast helpers on the
    #      ORIGINAL text so the advanced backend stays at parity with the reference parser
    #      (these constructs are opaque token lines in the ProLeap main grammar). ----
    _fill_from_reference(text, u)

    # ---- counts + complexity: identical computation to the default parser ----
    code = "\n".join(l for l in text.splitlines() if not cobol_ast._is_comment(l))
    u.counts = {
        "CALL": len(re.findall(r"(?i)\bCALL\b", code)),
        "PERFORM": len(re.findall(r"(?i)\bPERFORM\b", code)),
        "IF": len(re.findall(r"(?i)\bIF\b", code)),
        "COPY": len(u.copies),
        "EXEC_SQL": len(u.sql),
    }
    u.complexity = 1 + u.counts["IF"] + u.counts["PERFORM"]
    return u


def _walk_calls(tree, u: Unit) -> None:
    """Resolve CALL targets from the parse tree with the same model the default parser uses:
    literal -> static/confirmed; variable whose last MOVE'd literal is known -> resolved/
    inferred (constant propagation); otherwise dynamic/needs_review. We track constants by
    walking statements in source order across the whole procedure."""
    const: dict[str, str] = {}

    # Visit statements in document order: collect MOVE-literal-to-var and CALL nodes.
    events: list[tuple[int, str, object]] = []
    for mv in _find_all(tree, "MoveToStatementContext"):
        events.append((_node_index(mv), "move", mv))
    for cl in _find_all(tree, "CallStatementContext"):
        events.append((_node_index(cl), "call", cl))
    events.sort(key=lambda e: e[0])

    for _, kind, node in events:
        if kind == "move":
            # moveToStatement: moveToSendingArea TO identifier+
            sending = _find_all(node, "MoveToSendingAreaContext")
            lit = _literal_value(sending[0]) if sending else None
            if lit is None:
                # non-literal move clears constants for its targets
                for ident in _find_all(node, "IdentifierContext"):
                    const.pop(_txt(ident).strip(), None)
                continue
            targets = _find_all(node, "IdentifierContext")
            for t in targets:
                const[_txt(t).strip()] = lit.upper()
        else:  # call
            ln = _line(node)
            lit = None
            for ch_name in ("LiteralContext",):
                lits = _find_all(node, ch_name)
                if lits:
                    lit = _literal_value(lits[0])
                    break
            if lit is not None:
                u.calls.append({"target": lit.upper(), "kind": "static", "line": ln,
                                "confidence": 1.0, "validation": "confirmed"})
                continue
            idents = _find_all(node, "IdentifierContext")
            var = _txt(idents[0]).strip() if idents else ""
            if var in const:
                u.calls.append({"target": const[var].upper(), "kind": "resolved",
                                "via": var, "line": ln, "confidence": 0.7,
                                "validation": "inferred"})
            elif var:
                u.calls.append({"target": var, "kind": "dynamic", "line": ln,
                                "confidence": 0.3, "validation": "needs_review"})


def _node_index(ctx) -> int:
    """Token start index — a stable document-order key for parse-tree nodes."""
    try:
        return ctx.start.tokenIndex
    except Exception:
        return 0


def _fill_from_reference(text: str, u: Unit) -> None:
    """Copies, EXEC SQL edges + lineage, EXEC CICS edges, and MOVE/COMPUTE/arith field
    flows — taken from the verified cobol_ast extractors on the ORIGINAL source. These are
    the constructs ProLeap leaves as opaque token lines, so reusing the reference keeps the
    two backends at exact parity (the honesty mandate) rather than forking a second,
    unverified extractor."""
    ref = cobol_ast.parse(text)
    u.copies = ref.copies
    u.sql = ref.sql
    u.cics = ref.cics
    u.field_flows = ref.field_flows
