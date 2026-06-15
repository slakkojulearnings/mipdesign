#!/usr/bin/env python3
"""Generate the ANTLR4 COBOL-85 Python parser into `src/mip/grammar/` — one command.

This is the *only* step the advanced backend needs that requires Java + network (so it is
not bundled). Everything else (the adapter, the COPY/REPLACING preprocessor, the fallback)
ships and is tested without it.

    python scripts/gen_grammar.py            # fetch grammar + ANTLR tool, generate
    python scripts/gen_grammar.py --check    # just report what's required / present

Pinned, reproducible inputs (verified to generate a parser that passes the MIP suite under
MIP_PARSER=advanced):
  * ANTLR tool : antlr-4.13.2-complete.jar      (matches antlr4-python3-runtime>=4.13)
  * Grammar    : ProLeap proleap-cobol-parser, commit GRAMMAR_COMMIT below
                 files Cobol.g4 (-> grammar Cobol85) and CobolPreprocessor.g4
                 (-> grammar Cobol85Preprocessor)

What it does, in order:
  1. ensure Java is on PATH (needs 11+),
  2. download the ANTLR tool jar into .antlr_build/ (cached),
  3. download the two ProLeap .g4 files (pinned commit) and rename the `grammar` decls to
     Cobol85 / Cobol85Preprocessor so the generated classes match cobol_antlr.available(),
  4. run `java -jar antlr -Dlanguage=Python3 -visitor` for each,
  5. copy the generated *.py / *.tokens into src/mip/grammar/ (with an __init__.py).

After it finishes, `MIP_PARSER=advanced` activates the ANTLR backend; verify with
`MIP_PARSER=advanced python -m pytest tests/test_groundtruth.py tests/test_antlr_backend.py -q`.
"""

from __future__ import annotations

import shutil
import subprocess
import sys
import urllib.request
from pathlib import Path

# --- pinned versions (change here only) -----------------------------------
ANTLR_VERSION = "4.13.2"
ANTLR_JAR = f"antlr-{ANTLR_VERSION}-complete.jar"
ANTLR_URL = f"https://www.antlr.org/download/{ANTLR_JAR}"

# ProLeap proleap-cobol-parser — pinned commit on the `main` branch (verified 2026-06).
GRAMMAR_REPO = "uwol/proleap-cobol-parser"
GRAMMAR_COMMIT = "d1bfe75bdd6d480f70c74c6345bcc02610ac30d3"
_RAW = f"https://raw.githubusercontent.com/{GRAMMAR_REPO}/{GRAMMAR_COMMIT}"
_G4_DIR = "src/main/antlr4/io/proleap/cobol"
# (remote file, local file, grammar-decl rename)  — ProLeap names them Cobol.g4 /
# CobolPreprocessor.g4; we rename the grammar to Cobol85* so generated class names line up.
GRAMMARS = [
    (f"{_RAW}/{_G4_DIR}/Cobol.g4", "Cobol85.g4", ("grammar Cobol;", "grammar Cobol85;")),
    (f"{_RAW}/{_G4_DIR}/CobolPreprocessor.g4", "Cobol85Preprocessor.g4",
     ("grammar CobolPreprocessor;", "grammar Cobol85Preprocessor;")),
]

ROOT = Path(__file__).resolve().parent.parent           # reference-implementation/
BUILD = ROOT / ".antlr_build"
OUT_PKG = ROOT / "src" / "mip" / "grammar"


def _have_java() -> bool:
    exe = shutil.which("java")
    if not exe:
        return False
    try:
        subprocess.run([exe, "-version"], capture_output=True, check=True)
        return True
    except Exception:
        return False


def _download(url: str, dest: Path) -> None:
    if dest.exists() and dest.stat().st_size > 0:
        print(f"  cached  {dest.name}")
        return
    print(f"  fetch   {url}")
    dest.parent.mkdir(parents=True, exist_ok=True)
    with urllib.request.urlopen(url, timeout=60) as r:
        dest.write_bytes(r.read())


def check() -> int:
    print("Requirements for the advanced (ANTLR) backend:")
    print(f"  Java 11+        : {'present' if _have_java() else 'MISSING (install a JDK)'}")
    print(f"  antlr4 runtime  : ", end="")
    try:
        import antlr4  # noqa: F401
        print(f"present ({antlr4.__name__})")
    except Exception:
        print("MISSING (uv pip install -e '.[advanced]')")
    gen = OUT_PKG / "Cobol85Parser.py"
    print(f"  generated parser: {'present at ' + str(OUT_PKG) if gen.exists() else 'NOT generated yet'}")
    print(f"\nPinned: ANTLR {ANTLR_VERSION}; grammar {GRAMMAR_REPO}@{GRAMMAR_COMMIT[:10]}")
    return 0


def generate() -> int:
    if not _have_java():
        print("ERROR: Java 11+ not found on PATH. Install a JDK, then re-run.", file=sys.stderr)
        return 2
    try:
        import antlr4  # noqa: F401
    except Exception:
        print("ERROR: antlr4 runtime missing. Run:  uv pip install -e '.[advanced]'",
              file=sys.stderr)
        return 2

    BUILD.mkdir(exist_ok=True)
    print("1) ANTLR tool")
    jar = BUILD / ANTLR_JAR
    _download(ANTLR_URL, jar)

    print("2) ProLeap grammar (.g4)")
    for url, local, (old, new) in GRAMMARS:
        dest = BUILD / local
        _download(url, dest)
        text = dest.read_text(encoding="utf-8")
        if old in text:                                 # rename grammar decl -> Cobol85*
            dest.write_text(text.replace(old, new, 1), encoding="utf-8")

    print("3) generate Python3 parsers")
    gen_out = BUILD / "out"
    if gen_out.exists():
        shutil.rmtree(gen_out)
    gen_out.mkdir()
    for _, local, _ in GRAMMARS:
        cmd = ["java", "-jar", str(jar), "-Dlanguage=Python3", "-visitor",
               "-o", str(gen_out), local]
        print("   ", " ".join(cmd))
        subprocess.run(cmd, cwd=str(BUILD), check=True)

    print(f"4) install into {OUT_PKG}")
    OUT_PKG.mkdir(parents=True, exist_ok=True)
    for pat in ("*.py", "*.tokens"):
        for f in gen_out.glob(pat):
            shutil.copy2(f, OUT_PKG / f.name)
    (OUT_PKG / "__init__.py").write_text(
        '"""Generated ANTLR4 COBOL-85 parser (ProLeap grammar). Do not edit by hand.\n\n'
        'Regenerate with scripts/gen_grammar.py. See ADVANCED_PARSER.md.\n"""\n',
        encoding="utf-8")

    print("\nDone. Activate with MIP_PARSER=advanced and verify:")
    print("  MIP_PARSER=advanced python -m pytest tests/test_groundtruth.py "
          "tests/test_antlr_backend.py -q")
    return 0


def main(argv: list[str]) -> int:
    if "--check" in argv:
        return check()
    return generate()


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
