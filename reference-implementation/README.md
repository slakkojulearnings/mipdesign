# MIP v0.1 — Reference Implementation (runnable spine)

The **vertical slice** that proves the MIP spine end-to-end:

```
scan (content-based) → parse COBOL + JCL → SQLite metadata store → queries
```

It answers the Stage-1 question — *"which jobs execute program X?"* — plus call
graph, root/driver detection, and dead-code detection, with every fact carrying the
**evidence envelope** (confidence + validation status). Dynamic `CALL WS-VAR` is
**kept and flagged** `needs_review`, never dropped.

Stdlib-only at runtime (sqlite3 + argparse + dataclasses) — **runs on any machine with
Python 3.13+, no network required.**

## Setup & run with `uv` (recommended)

```bash
cd reference-implementation
uv venv --python 3.13
uv pip install -e ".[dev]"

uv run mip scan sample_estate                       # inventory + parse + load SQLite (./mip.db)
uv run mip query "which jobs execute CRDPOST"       # -> DAILYCRD
uv run mip query "what does INTDRV call"            # INTCOMP + WS-RATE-PGM [needs_review]
uv run mip roots                                    # CRDPOST, INTDRV, PAYDRV, STMTDRV
uv run mip dead                                     # DEADPROG (needs_review)
uv run pytest -q                                    # ground-truth precision/recall = 1.0
```

## Run without installing (pure stdlib, any Python 3.13+)

```bash
PYTHONPATH=src python -m mip scan sample_estate
PYTHONPATH=src python -m mip query "which jobs execute CRDPOST"
python tests/test_groundtruth.py                    # prints precision/recall + checks
```

## What you get

```
$ mip scan sample_estate
  artifacts : 20  {'cobol': 10, 'copybook': 3, 'db2': 3, 'jcl': 4}
  programs  : 10
  jobs      : 4  (steps: 4)
  edges     : 24  (needs_review: 1)
```

The 20 members are **extension-less** (as real PDS library members are); the scanner
classifies them by **content**, not by extension.

## Layout

```
src/mip/
  scanner.py   content-based file classification (Level 1: inventory)
  cobol.py     PROGRAM-ID, CALL (static+dynamic), COPY, EXEC SQL  (Level 2)
  jcl.py       JOB, EXEC PGM=  -> root-driver discovery            (Level 2)
  store.py     SQLite load against schema.sql + evidence envelope  (Level 2)
  queries.py   jobs-executing / calls / deps / roots / dead-code + NL router
  pipeline.py  scan -> parse -> store
  cli.py       argparse CLI (mip scan|query|roots|dead)
  schema.sql   mirror of ../../01-metadata-model/schema.sql
sample_estate/ realistic card-processing estate (JCL/ COBOL/ COPYLIB/ DB2/)
tests/         hand-labeled ground truth + precision/recall test
```

## Honest v0.1 limits (documented, not hidden)

- Regex extraction, not a full COBOL grammar/AST. Next step: ProLeap/Koopa/ANTLR
  (see [`../00-foundation/ARCHITECTURE.md`](../00-foundation/ARCHITECTURE.md)).
- No `COPY ... REPLACING` expansion; CICS/IMS/MQ flows out of scope.
- Dynamic call targets are flagged `needs_review` (low confidence), not resolved.
- Graph algorithms (blast radius, clustering) are specified in
  [`../02-algorithms/CORE_ALGORITHMS.md`](../02-algorithms/CORE_ALGORITHMS.md) and land
  in the next phase on NetworkX.

## Try it on a real estate

Point `mip scan` at any folder of mainframe source. For a larger public corpus, clone
the AWS CardDemo (its COBOL/JCL/copybooks) and scan it:

```bash
git clone -b experimentation https://github.com/hpatel-appliedai/aws-mainframe-modernization-carddemo
uv run mip scan aws-mainframe-modernization-carddemo
```

(Real-world repos exercise the documented limits above — that's the point: the gaps
become measurable instead of theoretical.)
