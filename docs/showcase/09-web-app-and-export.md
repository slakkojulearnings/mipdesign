# 9. The Web App & Data Export

**Business value.** All of MIP's intelligence is delivered through a clean, calm web app
that a non-engineer can explore, plus open data exports that feed any other tool. You
don't read raw output — you click through a dashboard, a call-graph picture, and a
plain-English question box, and every answer shows its reasoning and is logged for
audit.

## What the app gives you

A single-page React app (Apple-inspired, light and uncluttered) with these screens —
documented in `app/USER_MANUAL.md` and `app/UX_SHOWCASE.md`:

- **Dashboard** — the big picture: counts of programs, jobs and relationships, plus
  most-depended-on, needs-review (dynamic) and dead-code tiles.
- **Programs / Program detail** — every program in a table; click for its capability,
  callers, dependencies, structure/AST, and a **View** button for the real source.
- **Call & Execution Graph** — a two-pane picture with **zoom/pan**: jobs and programs
  as boxes, calls as arrows, dynamic calls as dashed amber arrows. Click a node for its
  full profile; click an edge for its **evidence and confidence**.
- **Sequence & lineage diagrams** — the CICS interaction sequence
  ([06](06-online-cics.md)) and field-level data lineage ([04](04-data-lineage.md))
  rendered visually.
- **Query Console** — ask in plain English; get the answer, a **logged reasoning trace**
  (the steps + the evidence), and the program's complete profile.
- **Q&A Log** — every question recorded to `question_log.md` with its reasoning and
  evidence; an append-only **audit trail**.

## Real sample: a logged Q&A reasoning trace

Asking *"which jobs execute CRDPOST"* through the app returns the answer **and** this
trace, which is appended to `app/question_log.md`:

```json
{
  "question": "which jobs execute CRDPOST",
  "intent": "jobs_executing",
  "thought_process": [
    "Parsed the question and routed it to intent: \"jobs_executing\".",
    "Identified the program token: CRDPOST.",
    "Looked up job_step rows whose EXEC PGM= names this program (EXECUTES edges)."
  ],
  "evidence": [
    { "source_id": "DAILYCRD", "rel_type": "EXECUTES", "target_id": "CRDPOST",
      "source_evidence": "JCL/DAILYCRD:5", "validation_status": "confirmed", "confidence": 1.0 }
  ],
  "reason": "CRDPOST is named in EXEC PGM= of 1 job step(s); each is a confirmed EXECUTES edge traced to JCL source, so those jobs execute it.",
  "response": ["DAILYCRD"]
}
```

Every answer shows its work and cites its source line. Nothing is asserted without
evidence.

## Real sample: data export

MIP exports the whole estate as **JSON, CSV, or GraphML** (for graph tools). CSV
program export (`/api/export?format=csv&kind=programs`) — header + first rows:

```
program_id,language,line_count,calls_out,called_by,is_root,is_dead
AUTHTRAN,cobol,27,1,1,True,False
CRDPOST,cobol,18,2,1,True,False
DEADPROG,cobol,15,0,0,False,True
```

The relationship export carries the full evidence on every edge
(`/api/export?format=csv&kind=edges`):

```
source_type,source_id,rel_type,target_type,target_id,validation_status,confidence,source_evidence
program,INTDRV,CALLS,program,INTRATE1,inferred,0.7,COBOL/INTDRV:16
job,DAILYCRD,EXECUTES,program,CRDPOST,confirmed,1.0,JCL/DAILYCRD:5
```

## What this means

- The platform is **usable by leadership and analysts**, not just engineers — explore,
  click, and ask questions in plain English.
- Every answer is **explainable and audited**: the reasoning trace and the append-only
  `question_log.md` mean decisions can be traced back to evidence.
- Open exports (JSON/CSV/GraphML) carry the **validation status and confidence on every
  fact**, so MIP's intelligence flows cleanly into spreadsheets, BI tools, and graph
  visualizers without losing its honesty.
