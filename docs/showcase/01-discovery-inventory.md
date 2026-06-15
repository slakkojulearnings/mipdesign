# 1. Discovery & Inventory

**Business value.** Before you can modernize a mainframe, you need an honest census:
how much code is there, what are the true entry points that drive the business, and
what is no longer used. MIP produces this automatically in seconds — no tribal
knowledge required — so planning starts from facts, not folklore.

## What MIP does

Pointed at a folder of source, MIP inventories every artifact, classifies it (COBOL,
JCL, copybook, DB2, CICS), parses the relationships between them, and loads everything
into a queryable store. It then identifies **root programs** (the entry points jobs or
terminals actually launch) and **dead-code candidates** (programs nothing reaches).

## Real sample output

**Inventory (`mip scan`):**

```
Scanned '../source_mf_code' -> mip.db
  artifacts : 24  {'cics': 1, 'cobol': 12, 'copybook': 3, 'db2': 3, 'jcl': 4, 'unknown': 1}
  programs  : 12
  jobs      : 4  (steps: 4)
  edges     : 31  (needs_review: 0, inferred: 1)
```

**Root / driver programs (`mip roots`):**

```
Root / driver programs:
  - AUTHTRAN
  - CRDPOST
  - INTDRV
  - PAYDRV
  - STMTDRV
```

These are the five business processes that actually start work: one online
(`AUTHTRAN`, launched from a terminal) and four batch (each launched by a job).

**Dead-code candidates (`mip dead`):**

```
Dead-code candidates (needs_review - may be invoked dynamically/externally):
  - DEADPROG
```

**Answering a plain question (`mip query`):**

```
> which jobs execute CRDPOST
Jobs that execute it:
  - DAILYCRD

> what does AUTHTRAN call
  CALLS AUTHVAL
```

## What this means

- You get a **complete, classified inventory** of the estate in one command, with the
  relationship count up front (31 connections discovered here).
- The five roots tell you exactly **where the business logic begins** — the natural
  units to reason about for risk and modernization.
- `DEADPROG` is flagged as a dead-code candidate, but note the wording:
  **"needs_review — may be invoked dynamically/externally."** MIP does *not* tell you
  to delete it. It surfaces the candidate and leaves the call, because a program can be
  reached by a dynamic call the static code doesn't reveal. (Runtime evidence later
  *confirms* this one really is dead — see [07-runtime-correlation.md](07-runtime-correlation.md).)
- Plain-English questions return evidence-backed answers, not opinions.
