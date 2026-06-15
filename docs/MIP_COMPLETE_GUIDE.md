# MIP — The Complete Guide (in plain language)

*One long, simple document that explains everything MIP does, and how the Claude/Copilot
skills and agents are used — each with a real example and the outcome you get. No prior
mainframe knowledge needed.*

---

## The problem, in one breath

A bank runs **tens of thousands of mainframe programs** written over 40 years. The people
who wrote them are retiring. The documentation is stale. When someone asks *"where is the
credit limit updated?"* or *"what breaks if we change this table?"*, the honest answer
today is *"give us three weeks and two experts."*

**MIP turns that estate into something you can ask questions of — in seconds — with proof
behind every answer.**

## The one big idea

> **Understand the system before you transform it.**

Most tools jump straight to "convert COBOL to Java." MIP does the opposite: it first builds
*understanding*, layer by layer, and only then supports change:

```
Source Code → Inventory → Metadata → Knowledge Graph → Reasoning → Copilot → Modernization
```

Each layer stands on the one below it. You never skip a layer, because a confident answer
built on a shaky foundation is worse than no answer.

## The golden rule (read this once, it explains everything)

**Every fact MIP states carries evidence and a confidence level. Anything it had to guess
is labelled "needs review" or "inferred" — never presented as certain.**

- A fact it can prove from the source → **confirmed** (e.g. "program A calls program B,
  see file CRDPOST line 13").
- A fact it had to infer → **inferred / needs review** with a confidence score (e.g. "this
  looks like the *Authorization* capability — 50% sure, please verify").

That honesty is the whole product. It's why a bank can act on MIP's answers.

Throughout this guide we use one small, real sample estate — a **credit-card processing
system** — so every example is concrete and consistent.

---

# Part 1 — What MIP can do (every functionality)

Each functionality below follows the same simple shape: **What it is · Example · Outcome.**

## 1. Discovery & Inventory — "what do we even have?"

**What it is.** Point MIP at a folder of mainframe code; it walks every file and builds a
catalogue: which are COBOL programs, JCL jobs, copybooks, DB2 tables, CICS definitions, and
which are just compiled binaries. It does this **by reading the content**, not by trusting
file names (real mainframe files often have no extension at all).

**Example.**
```
$ mip scan source_mf_code
artifacts : 24  {'cobol': 12, 'jcl': 4, 'copybook': 3, 'db2': 3, 'cics': 1, 'unknown': 1}
programs  : 12     jobs : 4 (steps: 4)     relationships : 31
```

**Outcome.** In one pass you know exactly what the estate contains and how the pieces are
connected — the foundation everything else builds on.

## 2. Adaptive classification — "it learns your folders, nothing is hardcoded"

**What it is.** MIP figures out what each folder holds by profiling its contents. If you
add or rename folders tomorrow, it adapts — no code change. A folder full of COBOL is
recognised as such even if it's named `WEIRD-SRC`; a folder of compiled load modules is
recognised as binary by the bytes inside them.

**Example.**
```
$ ... profile_estate(...)
"COBOL": { "dominant_type": "cobol", "members": 12, "binary_ratio": 0.0 }
"CICS":  { "dominant_type": "cics",  "members": 1,  "binary_ratio": 0.0 }
```

**Outcome.** MIP works on *your* estate's real structure, not an idealised one — and keeps
working as that structure changes.

## 3. Binary-artifact handling — "don't garbage-parse what can't be parsed"

**What it is.** Compiled members (load modules, DBRMs, IMS DBD/PSB, maps) are **binary** —
not readable source. MIP detects them, inventories them, and *skips* parsing them, while
still noting they exist (and any relationship their name implies).

**Example.** A file in `LOADLIB/` full of null bytes → classified `binary`, line-count
left blank, size recorded, never parsed as COBOL.

**Outcome.** No nonsense extracted from binaries, and a big speed win on real estates where
many files are compiled output. (See [`MAINFRAME_ARTIFACTS.md`](MAINFRAME_ARTIFACTS.md).)

## 4. The grammar parser & AST — "read code like a compiler, not with find-and-replace"

**What it is.** MIP parses COBOL into a structured **AST** (abstract syntax tree) —
divisions, paragraphs, statements — so it understands *executable intent*, not just text.
It ships with two engines: a fast built-in **default** parser, and an **advanced** full
**ANTLR COBOL-85** grammar (opt-in) that adds complete language coverage and real
`COPY … REPLACING` expansion. Both produce identical results on the shared test suite.

**Example.** For `CRDPOST` the parser reports: 3 divisions, paragraph `0000-MAIN`,
2 `CALL`s, 1 `COPY`, complexity score 3.

**Outcome.** Accurate extraction (calls, copybooks, tables, data items) — and a clear path
to production-grade coverage by flipping `MIP_PARSER=advanced`.

## 5. Dynamic-call resolution — "catch the calls that hide at runtime"

**What it is.** COBOL can call a program whose name is in a variable
(`MOVE 'INTRATE1' TO WS-PGM … CALL WS-PGM`). Naive tools drop these and the call graph gets
holes. MIP follows the value and **resolves the target**, marking it *inferred* (not certain).

**Example.** `INTDRV` does `CALL WS-RATE-PGM` → MIP resolves it to **`INTRATE1`**, tagged
`inferred` (confidence 0.7) — kept and flagged, never silently dropped or asserted.

**Outcome.** A call graph with the dangerous, easy-to-miss edges *included and honest*.

## 6. Knowledge graph — "how the system actually fits together"

**What it is.** Every program, job, table, copybook, screen and queue becomes a node;
every CALL/EXECUTE/READ/WRITE/USE becomes an edge — a navigable map of the whole estate.

**Example.** `DAILYCRD (job) → CRDPOST → CRDVAL`, `CRDPOST → BALUPD → CARD_MASTER (table)`.

**Outcome.** You can traverse from any artifact to everything it touches and everything
that touches it — the basis for impact analysis, root detection, and lineage.

## 7. Root / driver detection — "where does work actually start?"

**What it is.** In a mainframe, execution starts in JCL jobs (`EXEC PGM=`) and CICS
transactions — not in random COBOL. MIP finds those true entry points, including **online**
ones, so nothing that's actually an entry gets mistaken for dead code.

**Example.**
```
$ mip roots
AUTHTRAN   (online — entered via CICS transaction AUTH)
CRDPOST, STMTDRV, PAYDRV, INTDRV   (batch — each run by a job)
```

**Outcome.** You know the handful of programs that kick everything off — the natural
starting points for understanding or modernising.

## 8. Dead-code detection — "what can we safely retire?"

**What it is.** Programs that no job runs and nothing calls are dead-code candidates —
flagged for review, never auto-deleted (they might still be triggered in ways static
analysis can't see).

**Example.**
```
$ mip dead
DEADPROG   (unreachable from any root — retirement candidate, needs_review)
```

**Outcome.** A shortlist of removal candidates with the honesty to say "verify before you
delete."

## 9. Impact analysis / blast radius — "what breaks if I change this?"

**What it is.** Pick any program, table, or field; MIP computes everything upstream that
would be affected and everything downstream it relies on, with a confidence-weighted score.

**Example.**
```
$ change CARD_MASTER (a DB2 table) →
impacted: BALUPD, STMTDRV, CRDPOST, DAILYCRD, STMTGEN     blast-radius score: 5.0
```

**Outcome.** Before touching anything, you see the true blast radius — change risk you can
estimate instead of discover in production.

## 10. Criticality ranking (PageRank) — "which programs matter most?"

**What it is.** Using the same algorithm Google used for web pages, MIP ranks programs by
how central they are to the estate — the most-depended-on, highest-leverage components.

**Example.** Top criticality in the sample: `AUTHVAL`, `AUTHTRAN`, `STMTFMT` …

**Outcome.** A prioritised list of "if this fails, a lot fails" — for risk reviews and
modernization sequencing.

## 11. Business capabilities & communities — "group the tech by what the business does"

**What it is.** MIP clusters the estate into business capabilities two ways: by naming +
call-closure (e.g. *Card Posting*), and by **Louvain community detection** on the
dependency graph (groups that are tightly coupled). Both are **inferred** and
confidence-scored.

**Example.** Communities found: *Card / Statement* (CRDPOST, CRDVAL, STMTDRV…),
*Interest / Balance* (BALUPD, INTCOMP, INTDRV), *Payment* (PAYDRV, PAYUPD) — with a
modularity score (~0.37) measuring how clean the split is. A nice honesty moment: `BALUPD`
landed with *Interest* (not *Card*) because it shares the `ACCTREC` copybook — real hidden
coupling MIP exists to reveal.

**Outcome.** Modernization can be organised around business outcomes, not technical
guesswork — every grouping marked "inferred, review me."

## 12. Data lineage — "where does this data come from and go?"

**What it is.** MIP traces data flow at two levels: **table-level** (which programs read/
write a table) and **field-level** (which COBOL field maps to which DB2 column, via SQL
host variables, `MOVE`, and `COMPUTE`).

**Example.**
```
STMTDRV : CARD_MASTER.CURRENT_BALANCE → CARD-BALANCE   [reads from DB]   (COBOL/STMTDRV:12)
PAYUPD  : PAY-AMOUNT → PAYMENT.PAY_AMOUNT               [writes to DB]    (COBOL/PAYUPD:11)
INTCOMP : ACCT-BALANCE derives from ACCT-BALANCE        [COMPUTE]
```

**Outcome.** Answer "where is X updated?" and trace a value end-to-end — essential for
compliance, audits, and safe change.

## 13. Business-rule extraction — "pull the policy out of the code"

**What it is.** MIP finds decision logic (`IF`/`EVALUATE`) and calculations (`COMPUTE`) and
presents them as readable rule cards — the *condition* with its source line (confirmed) and
a plain-English rendering (inferred, so a human verifies the meaning).

**Example.**
```
CRDVAL · validation · "When CARD-STATUS = 'A', then move 0 to lk-return-code."
        evidence: COBOL/CRDVAL:13   (inferred, confidence 0.6)
```

**Outcome.** Decades of buried business policy becomes a reviewable list — the highest-value
knowledge to recover before a rewrite.

## 14. Online layer (CICS) + transaction mapping — "see the screens and online calls too"

**What it is.** Many estates aren't just batch. MIP reads `EXEC CICS` commands (online
program LINKs, file/queue access, screen maps) and CICS **CSD** definitions that map a
transaction to its entry program — so the *online* world appears in the graph, not just batch.

**Example.**
```
CSD: transaction AUTH → starts program AUTHTRAN
AUTHTRAN: LINK→AUTHVAL (online call), READ FILE CARDFILE, SEND MAP AUTHMAP
AUTHVAL : WRITEQ AUTHLOG (queue)
```

**Outcome.** Online transaction flows — invisible to batch-only tools — become first-class
in the graph, lineage, and impact analysis.

## 15. Runtime-evidence correlation — "cross-check the code against what actually ran"

**What it is.** Feed MIP operational data (how often each program/transaction ran) and it
reconciles *static* analysis with *runtime* reality.

**Example.**
```
DEADPROG  : 0 runs  → confirmed dead (static + runtime agree → confidence raised)
INTRATE1  : ran 480k× → confirms the dynamic CALL really fires (a "static miss" caught)
AUTHVAL   : busiest program → highest runtime-weighted criticality
```

**Outcome.** Higher-confidence dead-code and criticality, and proof that resolved dynamic
calls are real — static guesses validated by fact (and gaps marked "unknown" when no data).

## 16. Natural-language Query Console — "just ask, in English, and see the reasoning"

**What it is.** Ask questions in plain English; MIP answers from the graph (facts, not a
chatbot's imagination) and **shows its work** — the steps it took and the evidence — and
logs every Q&A to an audit file.

**Example.**
```
Q: "which jobs execute CRDPOST"
A: DAILYCRD
Why: intent = jobs-executing → found CRDPOST in EXEC PGM= of DAILYCRD (JCL/DAILYCRD:5, confirmed)
```

**Outcome.** Anyone — analyst, auditor, new joiner — gets trustworthy answers with a
transparent, logged rationale (`question_log.md`).

## 17. Global search — "find anything across the estate"

**What it is.** One search box over programs, jobs, tables, copybooks, transactions, and
capabilities, ranked by relevance.

**Example.** `search "AUTH"` → transaction `AUTH` (exact), capability *Authorization*,
programs `AUTHTRAN`/`AUTHVAL`.

**Outcome.** Instant navigation to any artifact — no more grepping a 180k-file tree.

## 18. Sequence diagrams — "auto-draw how a transaction flows"

**What it is.** From the call/SQL/CICS order in the code, MIP generates a **Mermaid sequence
diagram** of a program's runtime interactions — evidence-backed documentation, drawn for you.

**Example.** `AUTHTRAN` → participants `AUTHTRAN, AUTHMAP (screen), CARDFILE (file),
AUTHVAL` rendered as a sequence diagram in the web app.

**Outcome.** Living documentation that matches the code (because it's derived from it) —
directly countering the "our diagrams are 10 years stale" problem.

## 19. Export — "own your data; open it anywhere"

**What it is.** Export the inventory and graph as **JSON, CSV, or GraphML** with one click
or call.

**Example.** `GET /api/export?format=graphml` → opens directly in Gephi or imports into Neo4j;
`format=csv&kind=programs` → a spreadsheet of every program.

**Outcome.** No lock-in — feed MIP's knowledge into whatever tool the team already uses.

## 20. Scale & performance — "built for 180,000 files"

**What it is.** Real estates are huge. MIP reads only a small header of each file to
classify it, skips binaries fast, writes to its database in **batched transactions**
(≈4.6× faster), and **parses across all CPU cores** in parallel (with identical results to
single-threaded).

**Example.** `MIP_WORKERS=8 mip scan <big-estate>` — parsing fans out across 8 cores; the
database load that used to be the bottleneck is now a fraction of a second.

**Outcome.** Enterprise-scale scanning that finishes in reasonable time — with the honest
scale plan (when to move from SQLite/NetworkX to a graph DB) written down.

## 21. The web application — "all of the above, beautifully, in a browser"

**What it is.** A clean, Apple-style React app over the engine: **Dashboard** (the numbers),
**Programs** (search/sort/filter), **Capabilities**, **Jobs**, an interactive **Call Graph**
(zoom/pan, confidence slider, edge filters, keyboard + screen-reader friendly), **Roots**,
**Dead Code**, **Query Console**, and a **Q&A Log** — plus per-program **profile, AST,
impact, field-lineage diagram, sequence diagram, and business rules**, with **click-to-
evidence** everywhere and one-click **export**.

**Example.** Open `http://localhost:8000`, click a node in the Call Graph → its full profile
+ structure load on the right; click an edge → its evidence and confidence.

**Outcome.** A product an analyst can use without training — every screen leads with value
and shows its evidence.

## 22. The evidence & confidence model — "the thread running through all of it"

**What it is.** Not a feature you click — the discipline behind every other one. Each fact
carries: *source* (file:line), *method* (how found), *confidence*, *validation status*,
*timestamp*. Uncertainty is shown, never hidden; partial/missing input degrades gracefully
instead of failing.

**Example.** The same INTDRV→INTRATE1 call appears as `inferred · 0.7 · resolved from
WS-RATE-PGM` — you can see *exactly* how much to trust it.

**Outcome.** Trust. A bank can make decisions on MIP's output because MIP is honest about
what it knows and what it's guessing.

---

# Part 2 — How Claude / Copilot skills and agents are used

"Agents and skills" show up in **two senses** here: (A) skills/agents that are part of the
MIP product, and (B) the Claude Code agents that *built* MIP. Both are explained with
examples.

## A. MIP skills — the "job descriptions" the AI follows

**What they are.** In [`03-skills/`](../03-skills/) there are **12 skills**, each a folder
with a `SKILL.md` written to the open **Agent Skills standard**
([agentskills.io](https://agentskills.io/specification)). A skill is a *persona with a
charter*: what it does, its inputs/outputs, its rules. They make the AI behave
consistently — like giving each role on a team a clear job description.

The 12 skills and, in plain terms, what each is for:

| Skill | In plain words |
|-------|----------------|
| `mainframe-code-analyst` | Reads the raw code and extracts the facts (calls, copybooks, tables, AST). |
| `metadata-modeler` | Defines the common vocabulary (what a "Program" or "Job" is). |
| `sqlite-engineer` | Designs how facts are stored and queried. |
| `graph-engineer` | Builds the dependency graph and runs the graph maths (impact, PageRank, communities). |
| `business-capability-analyst` | Groups technical assets into business capabilities. |
| `resilience-engineer` | Finds single points of failure, dead code, operational risk. |
| `security-compliance-analyst` | Flags sensitive data (PII, financial) and compliance impact. |
| `mainframe-modernization-architect` | Turns the understanding into a safe, staged modernization plan. |
| `test-engineer` | Makes sure everything is tested and trustworthy. |
| `code-reviewer` | Critiques designs/code for correctness and honesty. |
| `documentation-writer` | Writes the docs (like this one). |
| `repository-engineer` | Keeps the repo and the skills/prompts organised. |

**Example of usage.** When MIP analyses a program, it acts as the `mainframe-code-analyst`
(extract facts) → hands them to `metadata-modeler` (normalise) → `graph-engineer` (connect)
→ `business-capability-analyst` (group). Each skill names exactly which prompts invoke it
and which code implements it.

**The registry & guarantee.** [`skills.catalog.json`](../03-skills/skills.catalog.json)
maps every skill → its prompts → its code, with a `status` (built / partial / planned). A
checker, `python 03-skills/validate_catalog.py`, fails if a skill and the catalog ever drift
apart — so this stays accurate.

**Outcome.** Consistent, predictable AI behaviour, and a clear line from "who's responsible"
(skill) to "what they're told to do" (prompt) to "the code that does it" (tool).

## B. The prompt library — the "questions" that drive the skills

**What it is.** [`04-prompts/`](../04-prompts/) holds a curated set of prompts (discovery,
parsing, metadata, graph, plus community modernization prompts like "explain this program",
"extract business rules", "draft the Java", "plan the strangler migration"). Each prompt
names the skill that owns it and bakes in the evidence-and-confidence rule.

**Example.** The "explain a program in plain English" prompt is owned by
`mainframe-code-analyst` and instructs: *cite source lines; mark anything uncertain as an
assumption.*

**Outcome.** Anyone on the team gets consistent, safe results from Copilot/Claude instead of
ad-hoc prompting.

## C. Project agents — Claude Code helpers that ship with the repo

**What they are.** [`.claude/agents/`](../.claude/agents/) defines two ready-to-use agents
(and `.claude/skills/` mirrors the 12 skills so Claude Code auto-discovers them):

- **`mip-discovery`** — *Example:* "Analyse `source_mf_code`." → it runs the engine and
  reports inventory, roots (batch + online), dead code, the capability map, and a couple of
  blast-radius examples, each with evidence + confidence.
- **`mip-modernization-architect`** — *Example:* "What should we modernise first?" → it uses
  the evidence to recommend extracting the lowest-blast-radius capability first (e.g.
  *Authorization*), and sequences the rest, citing the numbers.

**Outcome.** A teammate using Claude Code in this repo gets MIP-aware help immediately, no
setup.

## D. How agents *built* MIP — multi-agent orchestration (with examples)

MIP itself was built by **fanning out parallel Claude Code subagents**, each owning a
non-overlapping set of files, then integrating and verifying centrally. Examples:

- **Parallel feature pairs.** Business-rule extraction (backend) ‖ router + search
  (frontend); ANTLR parser ‖ runtime correlation; scan-performance ‖ binary classification.
  Each agent got the exact API contracts so the halves matched on first integration.
  *Outcome:* two features delivered per wave, no conflicts.
- **An adversarial code-review agent.** *Example:* it audited the new parser and found a
  real bug — arithmetic like `ADD A TO B GIVING C` was inventing a phantom data field from
  the keyword `TO`. *Outcome:* 4 such correctness/honesty bugs were caught and fixed with
  regression tests *before* shipping.
- **A documentation agent.** *Example:* it generated the [`docs/showcase/`](showcase/)
  management pack from **real** captured engine output — no invented numbers.
- **Guardrails on every agent.** Don't fabricate; keep the default parser the verified
  reference; keep the test suite green; commit only verified work.

**Outcome.** Faster delivery *and* higher quality — independent agents build in parallel, an
independent agent tries to break the result, and only verified work lands.

## E. How it all connects

```
04-prompts  (what to ask)  →  03-skills  (who does it, by what rules)  →  reference-implementation  (the code that runs)
                                   ↑ registry + validator keep these in sync ↑
.claude/agents + .claude/skills  →  make all of the above usable from Claude Code in this repo
```

---

# Part 3 — A day in the life (one worked story)

> A developer is asked: *"We need to change how the credit-card balance is stored in
> `CARD_MASTER`. Is that safe?"*

1. **Search** `CARD_MASTER` → it's a DB2 table used across the estate.
2. **Impact** on `CARD_MASTER` → impacted: `BALUPD`, `STMTDRV`, `CRDPOST`, `DAILYCRD`,
   `STMTGEN` (blast-radius 5.0). Now they know the change isn't local.
3. **Field lineage** → `BALUPD` writes `ACCT-BALANCE → CARD_MASTER.CURRENT_BALANCE`;
   `STMTDRV` reads `CURRENT_BALANCE → CARD-BALANCE`. They see exactly which fields move.
4. **Business rules** on those programs → the balance-update conditions, with source lines.
5. **Runtime** → all five impacted programs actually run in production (not dead) — so the
   change must be coordinated.
6. **Sequence diagram** of the posting flow → a picture to share in the change review.

What was three weeks and two SMEs is now **fifteen minutes, with evidence for every claim.**
That is MIP.

---

# Part 4 — Honest limits & what's next

- The built-in parser is a focused grammar; the **advanced ANTLR COBOL-85** backend
  (`MIP_PARSER=advanced`) adds full coverage + `COPY REPLACING`.
- Inferred outputs (capabilities, communities, business-rule meaning, resolved dynamic
  calls) are **confidence-scored and flagged** — by design.
- **Roadmap:** IMS/MQ extraction, a graph-database/scale backend, and multi-tenant. See
  [`../COMPARISON_AND_ROADMAP.md`](../COMPARISON_AND_ROADMAP.md).

# Part 5 — Quick reference

```bash
# setup
cd reference-implementation && uv venv --python 3.13 && uv pip install -e ".[dev,api]"

# engine
uv run mip scan ../source_mf_code
uv run mip query "which jobs execute CRDPOST"
uv run mip roots ; uv run mip dead

# web app
cd app/frontend && npm install && npm run build
cd ../../reference-implementation && uv run uvicorn mip.api:app --port 8000   # http://localhost:8000

# test everything
uv run pytest -q                          # 84 passing
python ../03-skills/validate_catalog.py   # skills ⇄ catalog in sync

# knobs
MIP_SOURCE=/path   MIP_PARSER=advanced   MIP_WORKERS=8   MIP_BINARY_LIBS=ACMELOAD
```

*For deeper detail: [`README.md`](../README.md) (run/test), [`app/USER_MANUAL.md`](../app/USER_MANUAL.md)
(every screen), [`docs/showcase/`](showcase/) (sample outputs for management),
[`00-foundation/`](../00-foundation/) (philosophy, principles, architecture).*
