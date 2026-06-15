"""Adaptive / content-driven classification tests.

Proves the scanner learns from the estate instead of relying on hardcoded folder names:
arbitrary folder names classify by content; unresolved members inherit a folder's learned
dominant type; binary is content-driven; conventions are an env-extensible fallback.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

_SRC = Path(__file__).resolve().parent.parent / "src"
sys.path.insert(0, str(_SRC))

from mip import scanner  # noqa: E402

_COBOL = ("       IDENTIFICATION DIVISION.\n       PROGRAM-ID. {name}.\n"
          "       PROCEDURE DIVISION.\n           GOBACK.\n")
_JCL = "//{name} JOB (ACCT)\n//STEP1 EXEC PGM=THING\n"


def _by_path(arts):
    return {a.path: a for a in arts}


def test_arbitrary_folder_names_classified_by_content(tmp_path):
    # Folders named nothing like JCL/COBOL — classification must come from content alone.
    (tmp_path / "weird-src").mkdir()
    (tmp_path / "weird-src" / "P1").write_text(_COBOL.format(name="P1"), encoding="utf-8")
    (tmp_path / "ops").mkdir()
    (tmp_path / "ops" / "J1").write_text(_JCL.format(name="J1"), encoding="utf-8")
    arts = _by_path(scanner.scan(tmp_path))
    assert arts["weird-src/P1"].artifact_type == "cobol"
    assert arts["ops/J1"].artifact_type == "jcl"


def test_unresolved_member_inherits_folder_dominant_type(tmp_path):
    # A folder dominated (by content) by COBOL; one extension-less member has NO signature.
    lib = tmp_path / "MYLIB"
    lib.mkdir()
    for i in range(3):
        (lib / f"PGM{i}").write_text(_COBOL.format(name=f"PGM{i}"), encoding="utf-8")
    # text, but no IDENTIFICATION/PROGRAM-ID, no // JOB, no PIC -> _content_type is None
    (lib / "FRAGMENT").write_text("           MOVE A TO B.\n           ADD 1 TO C.\n",
                                  encoding="utf-8")
    arts = _by_path(scanner.scan(tmp_path))
    assert arts["MYLIB/FRAGMENT"].artifact_type == "cobol"   # folder-inferred


def test_binary_by_content_in_any_folder(tmp_path):
    d = tmp_path / "whatever"
    d.mkdir()
    (d / "MOD").write_bytes(b"\x00\x01ESD\x00\xc1\xc2\x00" * 64)
    arts = _by_path(scanner.scan(tmp_path))
    assert arts["whatever/MOD"].artifact_type == "binary"


def test_profile_estate_reports_learned_folder_roles(tmp_path):
    (tmp_path / "A").mkdir()
    for i in range(2):
        (tmp_path / "A" / f"P{i}").write_text(_COBOL.format(name=f"P{i}"), encoding="utf-8")
    (tmp_path / "B").mkdir()
    (tmp_path / "B" / "BIN").write_bytes(b"\x00\x00\x00" * 100)
    prof = scanner.profile_estate(tmp_path)
    assert prof["A"]["dominant_type"] == "cobol"
    assert prof["B"]["binary_ratio"] == 1.0


def test_binary_libs_env_extensible(tmp_path, monkeypatch):
    # A site-specific compiled library name, added at runtime with no code change.
    member = tmp_path / "ACMELOAD" / "M1"
    member.parent.mkdir(parents=True)
    member.write_text("plain text but it lives in a site binary library\n", encoding="utf-8")
    # without the hint it's not binary (it's text, lonely in its folder)...
    assert _by_path(scanner.scan(tmp_path))["ACMELOAD/M1"].artifact_type != "binary"
    # ...with the env hint, it is.
    monkeypatch.setenv("MIP_BINARY_LIBS", "ACMELOAD")
    assert _by_path(scanner.scan(tmp_path))["ACMELOAD/M1"].artifact_type == "binary"
