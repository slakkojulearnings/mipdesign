# MIP — User Manual

A simple guide to the MIP web app. It turns a folder of mainframe code into something
you can explore and ask questions about.

## Start

1. Put your mainframe code in `source_mf_code/` (COBOL, JCL, copybooks, DB2 — file
   extensions optional). A sample card-processing estate is already there.
2. Start the app (see `app/README.md`) and open it in your browser.
3. Click **↻ Rescan source** any time you change the code.

Every screen is in the left sidebar.

## Screens

**Dashboard** — the big picture. Counts of programs, jobs, relationships, plus three
insights: the most depended-on program, dynamic calls that need review, and dead-code.

**Programs** — every program in a table. Columns show how many programs it calls,
how many call it, and flags (`root`, `dead`). Click a row to open its detail.

**Program detail** — everything about one program:
- *Insights*: complexity, fan-out, fan-in, how many jobs run it.
- *Profile*: its capability, the jobs that run it, what it calls/uses/reads/writes, who calls it.
- *Structure / AST*: its divisions, paragraphs, a statement mix, and a complexity score.
- *Source*: click **View** to see the actual code.

**Capabilities** — the business functions found in the code (e.g. *Card Posting*,
*Payment*). Each card lists its programs, data tables, and shared structures. Labels are
*inferred* and shown with a confidence — review before trusting.

**Jobs** — each batch job and the program every step runs (`EXEC PGM=`).

**Call Graph** — a picture of how things connect. Jobs and programs are boxes; arrows
are calls/executions. Dashed amber arrows are dynamic calls (uncertain).
- **Click a node** → full profile + structure on the right.
- **Click an edge** → that relationship's evidence and confidence.

**Root Programs** — the true entry points (a job runs them; nothing calls them).

**Dead Code** — programs nothing reaches. Flagged for review (they might still be
called dynamically), never deleted.

**Query Console** — ask in plain English, e.g.:
- “which jobs execute CRDPOST”
- “what does PAYUPD write”
- “tell me everything about INTDRV”
- “show dead code”

You get the answer, a **reasoning trace** (the steps + the evidence), and the
program's **complete profile**.

**Q&A Log** — every question is saved to `question_log.md` with its reasoning and
evidence. This screen shows that history; you can also view the raw file.

## The one rule to remember

MIP never guesses silently. Anything uncertain — a dynamic call, an inferred capability
— is **kept and marked “needs review”** with a confidence score, never shown as fact.
That's what makes its answers safe to act on.
