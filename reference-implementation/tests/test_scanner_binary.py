"""Scanner tests for binary/compiled artifact handling + header-capped classification.

These tests build their own files in a tempdir and NEVER modify sample_estate. The
last test asserts the real sample_estate still classifies into the exact same type
distribution as before (ground-truth depends on it).
"""

from __future__ import annotations

import sys
from pathlib import Path

_SRC = Path(__file__).resolve().parent.parent / "src"
sys.path.insert(0, str(_SRC))

from mip import scanner  # noqa: E402

ESTATE = Path(__file__).resolve().parent.parent / "sample_estate"

_COBOL_SNIPPET = (
    "       IDENTIFICATION DIVISION.\n"
    "       PROGRAM-ID. TESTPGM.\n"
    "       PROCEDURE DIVISION.\n"
    "           GOBACK.\n"
)


def _types(artifacts):
    """artifact_type counts keyed by type."""
    out: dict[str, int] = {}
    for a in artifacts:
        out[a.artifact_type] = out.get(a.artifact_type, 0) + 1
    return out


def _by_path(artifacts):
    return {a.path: a for a in artifacts}


def test_load_module_with_nuls_is_binary(tmp_path):
    # A fake load module: object-ish bytes with embedded NULs (as real load modules have).
    mod = tmp_path / "LOADLIBX" / "MYPGM"
    mod.parent.mkdir(parents=True)
    mod.write_bytes(b"\x00\x01\x02PGM\x00\xc1\xc2\xc3\x00\x00rmode\x00" * 64)

    arts = _by_path(scanner.scan(tmp_path))
    assert arts["LOADLIBX/MYPGM"].artifact_type == "binary"
    # binary members are inventory-only: not line-counted, size still recorded.
    assert arts["LOADLIBX/MYPGM"].line_count is None
    assert arts["LOADLIBX/MYPGM"].size_bytes > 0


def test_normal_cobol_snippet_is_cobol(tmp_path):
    src = tmp_path / "src" / "TESTPGM"
    src.parent.mkdir(parents=True)
    src.write_text(_COBOL_SNIPPET, encoding="utf-8")

    arts = _by_path(scanner.scan(tmp_path))
    assert arts["src/TESTPGM"].artifact_type == "cobol"
    assert arts["src/TESTPGM"].line_count == _COBOL_SNIPPET.count("\n") + 1


def test_large_text_file_classifies_from_header(tmp_path):
    # COBOL signature at the top, then padding far beyond the header cap. The scanner
    # must still classify it "cobol" from the capped header without reading it all.
    big = tmp_path / "BIGPGM"
    padding = "      * filler comment line to make the program very large.\n"
    body = _COBOL_SNIPPET + padding * (scanner.HEADER_CAP // len(padding) + 5000)
    big.write_text(body, encoding="utf-8")
    assert big.stat().st_size > scanner.HEADER_CAP   # genuinely exceeds the cap

    arts = _by_path(scanner.scan(tmp_path))
    a = arts["BIGPGM"]
    assert a.artifact_type == "cobol"               # classified from header alone
    # capped files are not fully read, so line_count is left unknown (no 2nd read).
    assert a.line_count is None
    assert a.size_bytes == big.stat().st_size       # size from os.stat, still exact


def test_binary_library_name_hint_is_binary(tmp_path):
    # Even text-looking content in a known binary library is inventory-only "binary".
    for lib in ("DBRMLIB", "DBDLIB", "PSBLIB", "CICSLOAD", "VOG", "LDV"):
        member = tmp_path / lib / "MEMBER1"
        member.parent.mkdir(parents=True)
        member.write_text("this looks like text but lives in a binary library\n",
                          encoding="utf-8")

    arts = _by_path(scanner.scan(tmp_path))
    for lib in ("DBRMLIB", "DBDLIB", "PSBLIB", "CICSLOAD", "VOG", "LDV"):
        assert arts[f"{lib}/MEMBER1"].artifact_type == "binary", lib


def test_looks_binary_unit():
    assert scanner._looks_binary(b"\x00\x01\x02") is True          # NUL -> binary
    assert scanner._looks_binary(b"\xff\xfe\xfd\xfc" * 64) is True  # high non-text ratio
    assert scanner._looks_binary(b"IDENTIFICATION DIVISION.\n") is False
    assert scanner._looks_binary(b"") is False                     # empty is not binary


def test_sample_estate_type_distribution_unchanged():
    # The frozen expected distribution of the text estate. If a future change
    # misclassifies a member (or introduces a stray "binary"), this fails.
    arts = scanner.scan(ESTATE)
    dist = _types(arts)
    expected = {
        "cobol": 12,      # 10 batch + AUTHTRAN + AUTHVAL
        "jcl": 4,         # DAILYCRD, STMTGEN, PAYPROC, INTCALC
        "copybook": 3,    # CARDREC, ACCTREC, PAYREC
        "db2": 3,         # CARDMAST, ACCTMAST, PAYMENT
        "cics": 1,        # AUTHCSD
        "unknown": 1,     # runtime/runtime.json (no mainframe signature)
    }
    assert dist == expected, f"sample_estate distribution changed: {dist}"
    # And specifically: nothing in the text estate was tagged binary.
    assert "binary" not in dist
