# 2. Parsing & Program Structure (AST)

**Business value.** Everything MIP knows starts with reading the code accurately. A
shallow text scan misses how programs actually behave; MIP parses each program into a
real structural model (an "AST" — a map of its divisions, paragraphs and statements)
and measures its complexity. This is the trustworthy foundation the graph, lineage and
rules are all built on.

## What MIP does

MIP parses each COBOL program into a structured form: its divisions, its paragraphs,
the mix of statements it contains (CALL / PERFORM / IF / COPY / EXEC SQL), and a
complexity score. Critically, it also handles **dynamic calls** — where the program
called is decided at runtime — by keeping the edge and flagging it as *inferred* rather
than dropping it or pretending it's certain.

## Real sample output

**Structure / AST for `CRDPOST`** (from its profile):

```json
"structure": {
  "divisions": ["IDENTIFICATION", "DATA", "PROCEDURE"],
  "paragraphs": ["0000-MAIN"],
  "counts": { "CALL": 2, "PERFORM": 0, "IF": 2, "COPY": 1, "EXEC_SQL": 0 },
  "complexity": 3
}
```

**Dynamic-call resolution.** `INTDRV` chooses which interest-rate program to call at
runtime:

```cobol
MOVE 'INTRATE1' TO WS-RATE-PGM.
CALL WS-RATE-PGM USING ACCT-RECORD.
```

MIP doesn't drop this and doesn't pretend it's certain. It keeps the edge, resolves the
likely target, and marks it **inferred** with reduced confidence (from the relationship
export):

```
program,INTDRV,CALLS,program,INTRATE1,inferred,0.7,COBOL/INTDRV:16
```

(Compare a normal static call: `INTDRV CALLS INTCOMP ... confirmed,1.0`.)

## The advanced ANTLR COBOL-85 backend

MIP ships **two** parser backends that produce the *same* output shape:

| Mode | Backend | Use |
|---|---|---|
| `default` | hand-written grammar parser | works out of the box, no setup |
| `advanced` | industrial **ANTLR COBOL-85** grammar | broader language coverage for real-world code |

The advanced backend is **opt-in** and **parity-tested** — the full ground-truth suite
passes on it, proving it agrees with the reference parser (**28 tests passing**). The
platform reports which backend is active (`/api/health`):

```json
"parser": {
  "requested": "default",
  "advanced_available": true,
  "effective": "default"
}
```

`advanced_available: true` confirms the heavy-duty backend is built and ready on this
machine. If `advanced` is requested but the grammar isn't built, MIP **falls back to
the default automatically** — it never breaks.

## What this means

- The structure model and complexity score give a **per-program difficulty signal** for
  modernization estimates.
- Dynamic calls — historically a blind spot that breaks naive tooling — are
  **preserved and honestly flagged**, never silently lost.
- The dual-backend design means MIP runs anywhere with zero setup, yet can switch to an
  industrial-strength parser for messy real-world code, with **proven parity** between
  the two.
