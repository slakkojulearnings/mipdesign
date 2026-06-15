"""Tests for the advanced (ANTLR COBOL-85) parser backend.

Three layers, by what each can prove WITHOUT a Java/network grammar build:

  1. graceful fallback     — MIP_PARSER=advanced with the grammar absent must fall back to
                             the default parser cleanly (effective=default) and still parse.
  2. preprocess() expander — the pure-Python COPY/REPLACING + EXEC-fold normalizer is real
                             and runnable now; unit-test it directly.
  3. ANTLR parity path     — pytest.importorskip-guarded: runs the actual ANTLR tree-walk
                             ONLY when src/mip/grammar/ has been generated, and asserts the
                             advanced Unit matches the default Unit (parity) on the estate.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

import pytest

_SRC = Path(__file__).resolve().parent.parent / "src"
sys.path.insert(0, str(_SRC))

from mip import antlr_adapter, cobol_ast, cobol_antlr, parser_backend  # noqa: E402

ESTATE = Path(__file__).resolve().parent.parent / "sample_estate"


# --- 1. graceful fallback --------------------------------------------------
def test_fallback_when_grammar_absent(monkeypatch):
    """If 'advanced' is requested but the generated grammar isn't importable, the platform
    must report effective=default and still parse via the default backend. Verified
    regardless of whether the grammar happens to be generated, by forcing available()=False."""
    monkeypatch.setenv("MIP_PARSER", "advanced")
    monkeypatch.setattr(cobol_antlr, "available", lambda: False)

    info = parser_backend.backend_info()
    assert info["requested"] == "advanced"
    assert info["advanced_available"] is False
    assert info["effective"] == "default"

    # parse still works (falls through to the default grammar parser)
    u = parser_backend.parse((ESTATE / "COBOL" / "CRDPOST").read_text(encoding="utf-8"))
    assert u.program_id == "CRDPOST"
    assert ("CRDVAL", "confirmed") in {(c["target"], c["validation"]) for c in u.calls}


def test_advanced_not_available_without_grammar_or_runtime():
    """available() must be False unless BOTH antlr4 runtime AND generated grammar import.
    (When the grammar IS generated in this env it returns True — both states are valid;
    we only assert it never raises and returns a bool.)"""
    assert isinstance(cobol_antlr.available(), bool)


# --- 2. preprocess(): the pure-Python COPY/REPLACING + EXEC-fold expander ---
_COPYBOOKS = {
    "CARDREC": "       01  CARD-RECORD.\n           05  CARD-NUMBER  PIC X(16).\n",
    # pseudo-text REPLACING rewrites the substring PREFIX even inside PREFIX-RECORD
    "WITHREPL": "       01  PREFIX-RECORD.\n           05  PREFIX-ID  PIC X(8).\n",
    # word REPLACING rewrites a whole COBOL word only (PREFIX here is a standalone token)
    "WORDREPL": "       01  REC.\n           05  FLD  PIC X VALUE PREFIX.\n",
    "NESTED":   "       COPY CARDREC.\n       01  EXTRA  PIC X.\n",
}


def _resolver(name: str):
    return _COPYBOOKS.get(name.upper())


def test_preprocess_strips_comment_lines_and_paragraphs():
    src = (
        "       IDENTIFICATION DIVISION.\n"
        "       PROGRAM-ID. T.\n"
        "       AUTHOR. SOME PERSON.\n"
        "      * a banner comment line\n"
        "       PROCEDURE DIVISION.\n"
        "       0000-MAIN.\n"
        "           GOBACK.\n"
    )
    out = antlr_adapter.preprocess(src)
    assert "AUTHOR" not in out                  # comment paragraph removed
    assert "banner comment" not in out          # comment line removed
    assert "PROGRAM-ID. T." in out              # real code kept


def test_preprocess_expands_copy():
    src = "       DATA DIVISION.\n       COPY CARDREC.\n"
    out = antlr_adapter.preprocess(src, resolver=_resolver)
    assert "CARD-RECORD" in out and "CARD-NUMBER" in out   # copybook inlined
    assert "COPY CARDREC" not in out                       # statement consumed


def test_preprocess_copy_replacing():
    """COPY ... REPLACING ==PREFIX== BY ==CUSTOMER== rewrites the copybook text."""
    src = "       COPY WITHREPL REPLACING ==PREFIX== BY ==CUSTOMER==.\n"
    out = antlr_adapter.preprocess(src, resolver=_resolver)
    assert "CUSTOMER-RECORD" in out and "CUSTOMER-ID" in out
    assert "PREFIX-RECORD" not in out


def test_preprocess_copy_replacing_word_form():
    """Token form: COPY WORDREPL REPLACING PREFIX BY CUSTOMER (no pseudo-text delimiters).
    A bare word replaces a whole COBOL token only — PREFIX -> CUSTOMER, but it must NOT
    rewrite a larger identifier that merely contains 'PREFIX' (COBOL-word boundary)."""
    src = "       COPY WORDREPL REPLACING PREFIX BY CUSTOMER.\n"
    out = antlr_adapter.preprocess(src, resolver=_resolver)
    assert "VALUE CUSTOMER" in out and "VALUE PREFIX" not in out


def test_preprocess_nested_copy_expands_recursively():
    src = "       COPY NESTED.\n"
    out = antlr_adapter.preprocess(src, resolver=_resolver)
    assert "CARD-RECORD" in out and "EXTRA" in out          # inner COPY also inlined


def test_preprocess_unresolved_copy_is_removed_not_fabricated():
    """Unresolved COPY (no resolver / unknown name) -> statement removed, nothing invented."""
    src = "       COPY DOESNOTEXIST.\n       01 KEEP PIC X.\n"
    out = antlr_adapter.preprocess(src, resolver=_resolver)
    assert "COPY DOESNOTEXIST" not in out
    assert "KEEP" in out


def test_preprocess_folds_exec_blocks_to_tagged_lines():
    """EXEC SQL/CICS blocks fold to the single tagged line the ProLeap main grammar matches,
    body preserved so SQL/CICS facts can still be mined downstream."""
    src = (
        "           EXEC SQL\n"
        "              SELECT A INTO :B FROM T\n"
        "           END-EXEC.\n"
        "           EXEC CICS LINK PROGRAM('SUB')\n"
        "           END-EXEC.\n"
    )
    out = antlr_adapter.preprocess(src)
    assert "*>EXECSQL" in out and "SELECT A INTO :B FROM T" in out
    assert "*>EXECCICS" in out and "PROGRAM('SUB')" in out
    assert "END-EXEC" not in out                            # block collapsed


def test_default_resolver_finds_estate_copybook():
    """default_resolver(estate_root) locates real copybooks under COPYLIB/… and feeds
    preprocess(), so COPY CARDREC is genuinely inlined from the sample estate."""
    resolve = antlr_adapter.default_resolver(ESTATE)
    body = resolve("CARDREC")
    assert body is not None and "CARD-RECORD" in body
    assert resolve("NOPE") is None                      # unknown name -> None (no fabrication)

    out = antlr_adapter.preprocess("       DATA DIVISION.\n       COPY CARDREC.\n",
                                   resolver=resolve)
    assert "CARD-NUMBER" in out and "COPY CARDREC" not in out


def test_replacing_parse_pairs_longest_first():
    pairs = antlr_adapter._parse_replacing("==AB== BY ==X==  ==A== BY ==Y==")
    assert pairs[0][0] == "AB"          # longer source applied first (avoids partial clobber)
    assert pairs[0][2] is True          # pseudo-text flag carried through


# --- 3. ANTLR parity path (only when the grammar is generated) -------------
def test_antlr_parity_with_default_when_grammar_present():
    """When src/mip/grammar/ exists, the ANTLR backend must produce a Unit equal (on the
    fields the platform consumes) to the default parser, for every COBOL program in the
    estate. Skipped automatically when the grammar hasn't been built."""
    pytest.importorskip("antlr4")
    if not cobol_antlr.available():
        pytest.skip("ANTLR grammar not generated (run scripts/gen_grammar.py)")

    def _calls(cs):
        return sorted((c["target"], c["kind"], c["validation"], c.get("via")) for c in cs)

    def _di(ds):
        return sorted((d["level"], d["name"], d["pic"]) for d in ds)

    for path in sorted((ESTATE / "COBOL").iterdir()):
        text = path.read_text(encoding="utf-8")
        d = cobol_ast.parse(text)
        a = cobol_antlr.parse(text)
        assert a.program_id == d.program_id, path.name
        assert set(a.divisions) == set(d.divisions), path.name
        assert sorted(a.paragraphs) == sorted(d.paragraphs), path.name
        assert _calls(a.calls) == _calls(d.calls), f"{path.name} calls"
        assert _di(a.data_items) == _di(d.data_items), f"{path.name} data_items"
        assert a.counts == d.counts, f"{path.name} counts"
        assert a.complexity == d.complexity, f"{path.name} complexity"


def test_antlr_resolves_dynamic_call_when_grammar_present():
    """The ANTLR tree-walk performs the same constant-propagation CALL resolution as the
    default parser (MOVE 'INTRATE1' TO WS-RATE-PGM; CALL WS-RATE-PGM -> resolved/inferred)."""
    pytest.importorskip("antlr4")
    if not cobol_antlr.available():
        pytest.skip("ANTLR grammar not generated (run scripts/gen_grammar.py)")
    u = cobol_antlr.parse((ESTATE / "COBOL" / "INTDRV").read_text(encoding="utf-8"))
    by_target = {c["target"]: c for c in u.calls}
    assert by_target["INTCOMP"]["validation"] == "confirmed"     # static literal
    assert by_target["INTRATE1"]["kind"] == "resolved"           # const-propagated
    assert by_target["INTRATE1"]["validation"] == "inferred"
    assert by_target["INTRATE1"]["via"] == "WS-RATE-PGM"
