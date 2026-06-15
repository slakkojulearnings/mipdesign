# MIP vs. AWS Mainframe Modernization — Comparison & Roadmap

> A read-only research report comparing the **Mainframe Intelligence Platform (MIP)** in
> this repo with **AWS Transform** and **AWS Mainframe Modernization**, with a concrete,
> prioritized list of buildable next features for the engine and the React app.
>
> Date: 2026-06-14.

---

## 0. Important sourcing caveat (read first)

The task allowed live web research via `WebSearch`/`WebFetch`, but **both tools were
denied by the sandbox in this session**, so I could not fetch AWS pages live. The AWS
descriptions below are written from model knowledge (training cutoff January 2026) and
should be treated as **needs_review** — exactly the discipline MIP itself enforces. I
have cited the canonical, stable AWS documentation URLs so the claims can be verified;
**please re-verify the AWS feature specifics against these URLs before quoting them
externally.** Where I am uncertain, I say so rather than asserting.

The MIP side, by contrast, is grounded directly in the source code in this repo
(file paths cited throughout) and is `confirmed`.

**Reference URLs to verify the AWS claims:**

- AWS Transform (overview): https://aws.amazon.com/transform/
- AWS Transform for mainframe: https://aws.amazon.com/transform/mainframe/
- AWS Mainframe Modernization (service): https://aws.amazon.com/mainframe-modernization/
- AWS Mainframe Modernization docs: https://docs.aws.amazon.com/m2/latest/userguide/what-is-m2.html
- Replatform (Rocket Software / formerly Micro Focus) pattern: https://docs.aws.amazon.com/m2/latest/userguide/migrating-runtime.html
- Refactor (AWS Blu Age) pattern: https://docs.aws.amazon.com/m2/latest/userguide/concept-blue.html
- AWS Blu Age product page: https://aws.amazon.com/mainframe-modernization/patterns/automated-refactor/
- AWS re:Post / Prescriptive Guidance for mainframe modernization: https://docs.aws.amazon.com/prescriptive-guidance/

---

## 1. What the AWS offerings actually do

### 1.1 AWS Transform (agentic modernization)

AWS Transform is AWS's agentic, AI-driven service for accelerating large migrations
(.NET, VMware, and **mainframe**). For mainframe specifically, the agentic workflow is
oriented around **transform-first** acceleration of a COBOL-to-Java refactor:

- **Code analysis & documentation.** Ingests COBOL/JCL/copybooks and produces
  human-readable documentation, technical specifications, and dependency/flow summaries
  using LLM agents. Aims to recover "what the code does" as prose and diagrams.
- **Decomposition / wave planning.** Proposes how to break a monolith into domains and
  sequence the migration into waves.
- **Code transformation (COBOL → Java).** Generates Java (typically Spring-based) from
  COBOL, including data access, with the goal of an automated-then-reviewed conversion.
- **Test generation & validation.** Generates tests and helps validate functional
  equivalence between legacy and transformed code.
- **Human-in-the-loop, project-managed.** Work is organized as jobs/waves inside the
  AWS console with reviewable artifacts.

**Strengths (as positioned):** end-to-end and agentic — it goes all the way to running
Java; deep AWS integration; LLM-generated documentation and tests; scales with AWS
compute; backed by AWS support and the broader Migration Acceleration Program.

**Limits / open questions (verify):** it is a **managed, cloud-hosted AWS service** —
your source and derived knowledge live in AWS; output Java is LLM-generated and requires
human review for correctness (the usual fidelity/verification gap); the "understanding"
layer is a means to transformation, not a durable, queryable knowledge graph you own;
pricing/commercial terms apply; coverage of CICS/IMS/MQ/assembler and exotic dialects
varies and should be confirmed for a given estate.

### 1.2 AWS Mainframe Modernization (the M2 service) — two patterns

A managed AWS service (M2) offering **two migration patterns** plus tooling:

**A. Replatform ("Rocket Software"/Micro Focus runtime; AWS calls it the runtime
migration pattern).** Recompile/rehost the COBOL essentially **as-is** onto a managed,
emulated mainframe runtime on AWS (Rocket Software Enterprise, formerly Micro Focus).
The application stays COBOL/CICS-like; you avoid a language rewrite. Best when speed and
low risk matter more than getting off COBOL.

- *Does:* managed runtime, deployment, data migration tooling, observability.
- *Strengths:* fastest, lowest functional risk (no rewrite), keeps existing logic.
- *Limits:* you still run COBOL (now on AWS); doesn't reduce the COBOL skills problem;
  licensed emulation runtime.

**B. Refactor (AWS Blu Age) — automated COBOL → Java/Angular transformation.** A
toolchain that **automatically converts** COBOL/JCL (and screens) into modern Java
(and a web UI), then runs it on a managed AWS runtime.

- *Does:* automated code transformation to Java, data layer conversion, generated UI,
  managed deployment, and validation tooling.
- *Strengths:* gets off COBOL entirely; high automation ratio for supported dialects.
- *Limits:* generated Java is machine-style and needs review/refactoring for
  long-term maintainability; dialect/feature coverage must be confirmed; managed/cloud
  and commercially licensed.

**Common to both:** AWS provides discovery/assessment tooling (inventory, dependency
analysis, complexity) to plan the migration, and the runtime is managed by AWS.

**Net positioning of AWS:** *transform-first and managed.* Understanding exists to
serve the transformation; the durable artifact is **running modern code on AWS**, not an
open, self-owned knowledge graph.

---

## 2. What MIP actually is (grounded in this repo)

MIP is an **understanding/intelligence platform**, not (yet) a code transformer. The
thesis is the inverse of AWS's: *understand the system before you transform it*, and
attach **evidence + confidence to every fact**. Concretely, the runnable engine
(`reference-implementation/src/mip/`) does:

- **Content-based inventory** of extension-less PDS-style members (`scanner.py`).
- **Grammar-based COBOL parser** with a real tokenizer + recursive-descent parser
  building an AST (`cobol_ast.py`): divisions, paragraphs, data items, MOVE/CALL/IF/
  PERFORM/COMPUTE/arith, COPY, embedded EXEC SQL and EXEC CICS.
- **Dynamic-call resolution** via constant propagation (`MOVE 'X' TO WS-P` then
  `CALL WS-P` → target `X`, labeled `inferred` conf 0.7); unresolved `CALL WS-VAR`
  kept and flagged `needs_review` conf 0.3 — never dropped (`cobol_ast.py` `_parse_procedure`).
- **Field-level data lineage** (`cobol_ast.py` `_sql_lineage`, field_flows): MOVE
  field-to-field flows (incl. group moves), COMPUTE/ADD/SUBTRACT/MULTIPLY/DIVIDE
  derivations, and **EXEC SQL host-variable ↔ column** mapping with read/write direction.
- **CICS online layer** (`cics_csd.py`, `cobol_ast.py` `_cics_edges`): LINK/XCTL as
  online CALLS, file/queue reads/writes, MAP usage, START transaction; plus CSD parsing.
- **JCL + DB2 + copybook** parsing; `EXEC PGM=` → EXECUTES edges (`jcl.py`, `pipeline.py`).
- **NetworkX graph layer** (`graphx.py`): blast radius / impact (ancestors = who's
  impacted, weakest-link confidence along paths), PageRank centrality (pure-Python power
  iteration), Louvain community detection (inferred application/domain boundaries with
  modularity).
- **Root/driver detection** (batch via JCL + online via CICS entry), **dead-code**
  (reachability complement), **inferred business capabilities** from root call-closures
  (`queries.py`).
- **NL query with explainable reasoning trace** (`queries.py` `answer_with_trace`):
  intent → thought-process steps → evidence rows → reason, **logged to
  `question_log.md`** (`qlog.py`). The LLM narrates; SQL/graph supplies the facts.
- **Evidence envelope on every fact** (source · method · confidence · validation_status
  · timestamp) in the model, schema, and code.
- **Pluggable parser backend** — default hand-written grammar or advanced ANTLR
  (`parser_backend.py`, `cobol_antlr.py`).
- **FastAPI** over the same engine (`api.py`) and a **React UI** (`app/frontend/`).

It is **stdlib-first, portable, runs offline, no AWS account, no network** — `git clone`
and go.

---

## 3. Capability matrix — MIP vs. AWS

Legend: **Ahead** = MIP stronger; **Comparable** = roughly equal / different shape;
**Behind** = AWS stronger. AWS column conflates Transform + M2/Blu Age where relevant.

| Capability | MIP today | AWS (Transform / M2 / Blu Age) | Verdict for MIP |
|---|---|---|---|
| Discovery / inventory | Content-based scan of extension-less members; language classification | Discovery/assessment tooling, inventory, complexity | **Comparable** (MIP handles real PDS naming; AWS broader at scale) |
| Dependency / call graph | Static + dynamic CALLs, EXECUTES, CICS LINK/XCTL; kept+flagged dynamic edges | Dependency analysis as input to transformation | **Comparable**, MIP more explicit about *unresolved* edges |
| Data lineage (field level) | MOVE/COMPUTE/arith flows + SQL host-var↔column with direction | Data layer conversion; field lineage not the headline deliverable | **Ahead** as a queryable, evidence-backed artifact |
| Business-rule extraction | Not yet (AST + paragraphs are the substrate; no rule mining) | LLM-generated specs/documentation of logic | **Behind** |
| Impact / blast radius | NetworkX ancestors/descendants, weakest-link confidence, score | Implicit in wave planning; not a first-class queryable answer | **Ahead** (explicit, evidence-scored) |
| Capability / domain detection | Louvain communities + root-closure capabilities, all `inferred` | Decomposition/wave proposals via agents | **Comparable** (MIP open + confidence-scored; AWS more automated/opaque) |
| COBOL → Java transformation | **None** (community prompts only; no generator) | Core competency (Blu Age automated; Transform agentic) | **Behind** (the big gap) |
| Testing / validation | Ground-truth precision/recall on parser/graph (self-measuring) | Generated tests + equivalence validation for transformed code | **Comparable** in spirit; AWS validates *transformation*, MIP validates *understanding* |
| Explainability / evidence | Evidence+confidence on every fact; reasoning trace logged; nothing asserted | LLM docs; provenance/confidence not the contract | **Ahead** (this is MIP's signature) |
| Deployment / runtime | None (analysis only) | Managed AWS runtime for both patterns | **Behind** (by design — MIP isn't a runtime) |
| Scale | SQLite + NetworkX; honest named trigger/target for graph scaling | AWS-scale managed compute | **Behind** at very large estates (today) |
| Openness / cost / portability | Open, stdlib-first, offline, self-hosted, no lock-in | Managed AWS service, commercial licensing, cloud-resident data | **Ahead** (openness/portability/cost/sovereignty) |

---

## 4. MIP's genuine differentiator

Where the **"understand-before-transform, evidence+confidence, open/portable"** thesis
wins against AWS's transform-first, managed approach:

1. **Trust and auditability.** Every MIP fact carries source, method, confidence, and
   validation_status, and every NL answer ships a reasoning trace logged to
   `question_log.md`. In regulated industries (banking, insurance, government), an
   auditable "why" beats a black-box LLM conversion you must take on faith. AWS produces
   modern code; MIP produces **defensible knowledge**.

2. **Honesty about the unknown.** MIP keeps and flags dynamic/unresolved calls
   (`needs_review`, conf 0.3) rather than guessing. Transform-first tools must resolve
   or stub these to produce code, hiding exactly the risk that breaks migrations.

3. **Decision support before commitment.** MIP answers "what is this, what depends on
   it, what breaks if I change it, where are the domain boundaries" *before* you spend a
   transformation budget. It's the **due-diligence layer** AWS's pipeline assumes you've
   already done (or does opaquely inside the agent).

4. **Openness, portability, sovereignty, cost.** Stdlib-first, offline, self-hosted, no
   AWS account and no data egress. For organizations that can't or won't put mainframe
   source in a vendor cloud, MIP runs on a laptop. No lock-in: the knowledge graph is
   yours and is queryable forever, independent of any transformation decision.

5. **Vendor-neutral output.** MIP's graph can feed *any* downstream path — Blu Age,
   Transform, a hand-rewrite, or a strangler-fig — because it's a knowledge layer, not a
   transformation pipeline.

**Honest counterpoint:** AWS finishes the job (running modern code); MIP stops at
understanding. For a customer whose only goal is "get off the mainframe fast," AWS is
further along today. MIP's bet is that understanding is the scarce, reusable asset and
that transformation is safer (and cheaper) when it starts from an evidence graph.

---

## 5. Buildable next features (prioritized)

Effort: **S** ≈ ≤1 day, **M** ≈ a few days, **L** ≈ 1–2+ weeks. Each notes the existing
layer it builds on. Ordered by value-per-effort within tiers.

### Tier 1 — high value, low/medium effort (do first)

| # | Feature | Effort | Builds on | Notes |
|---|---|---|---|---|
| 1 | **Export (JSON / CSV / GraphML)** | S | `api.py`, `graphx.build_graph` | Add `/api/export?format=graphml\|json\|csv`. GraphML is one NetworkX call; JSON reuses `summary`/`graph`. Unlocks interop (Gephi, neo4j import) and "own your data" story. |
| 2 | **Sequence-diagram generation (Mermaid)** | M | AST paragraphs + CALL/PERFORM/CICS edges | Emit Mermaid `sequenceDiagram` per root from the call/EXEC order. Directly answers AWS's "documentation" pitch with an evidence-backed diagram, and renders free in the React app. |
| 3 | **Business-rule extraction (IF/EVALUATE → rule cards)** | M | `cobol_ast` (already tracks IF/EVALUATE/COMPUTE) | Extract conditional logic + arithmetic into structured "rule candidates" with source citation + confidence. The substrate (AST, complexity) exists; this is the highest-value understanding gap vs. AWS docs. |
| 4 | **Saved queries / query library** | S | `queries.answer_with_trace`, `qlog` | Persist named questions; one-click re-run; seed with the README examples. Pure additive over the existing NL router + log. |
| 5 | **Diff between scans** | M | `store.py` (snapshot two DBs), `queries.summary` | Compare two scans: added/removed programs, new dynamic edges, changed blast radius. Killer feature for ongoing change management; nothing in AWS surfaces this as a first-class artifact. |
| 6 | **Full-text search + filters in the React app** | S | `/api/programs`, client state | Search box + facet filters (root/dead/language/community). See §6. |
| 7 | **Lineage diagram view (React)** | M | `/api/program/{pid}/lineage` (already returns flows) | Render field flows as a left-to-right graph (reuse `CallGraph.jsx` layout). The data exists; only the view is missing. |

### Tier 2 — strategic, medium/large effort

| # | Feature | Effort | Builds on | Notes |
|---|---|---|---|---|
| 8 | **IMS + MQ support** | M | `cobol_ast` block parser (mirror EXEC CICS) | Parse `EXEC DLI`/`CBLTDLI` (IMS DB/DC) and `MQOPEN/MQPUT/MQGET` into READS/WRITES/USES edges. Extends coverage toward AWS-class estates. |
| 9 | **COBOL → Java draft (LLM via community prompts)** | L | `04-prompts/community`, AST, lineage, rules | Per-paragraph draft Java grounded in the AST + extracted rules + lineage, emitted as a **proposal** with citations and a confidence — explicitly *not* asserted equivalent. This is MIP's principled answer to Blu Age/Transform: transformation that cites the evidence graph and is test-gated. Pair with #11. |
| 10 | **neo4j / scalable graph backend** | L | `graphx.build_graph`, `store.py` | Optional backend behind a flag for estates beyond the NetworkX/SQLite honest-scale trigger documented in `ARCHITECTURE.md`. Keep SQLite default for portability. |
| 11 | **Transformation test harness (equivalence gating)** | L | `test-engineer` skill, ground-truth corpus | Golden I/O capture + comparison so any generated Java (#9) is verified before it's a decision — operationalizes "AI consumes knowledge, doesn't replace it." |
| 12 | **Runtime-evidence correlation** | L | evidence envelope, edges | Ingest SMF/CICS stats/job logs to upgrade `inferred` dynamic edges to `confirmed` from observed runtime, and to mark "dead code" actually exercised. Turns static guesses into observed facts — a differentiator AWS doesn't emphasize. |
| 13 | **Multi-tenant / workspaces** | L | `api.py` state, `store.py` | Per-estate DBs + auth (see §6) for a hosted offering; keep single-tenant offline mode intact. |

### Tier 3 — polish / breadth (opportunistic)

- **Copybook field-expansion in lineage** (S–M): resolve `COPY` members so lineage
  crosses copybook boundaries. Builds on `cobol_ast` copies + records.
- **Complexity/risk scoring per program & per capability** (S): aggregate existing
  cyclomatic proxy + fan-in/out + blast-radius into a single risk badge.
- **PII / sensitive-data tagging on lineage** (M): wire `security-compliance-analyst`
  skill to flag fields/columns; trace sensitive-data lineage end-to-end.

---

## 6. React app — functionality gaps for a credible product

Grounded in `app/frontend/src/` (App.jsx, hooks.js, components/, api.js). The app is a
clean, Apple-styled SPA with sidebar nav, dashboard, programs table, program detail,
SVG call graph, capabilities (Louvain), query console with reasoning trace, and Q&A log.
`useData` already gives per-view loading/error states and rescan refresh. Gaps:

**Navigation & deep-linking**
- **No router / no URL state.** Navigation is React `useState` in `App.jsx` (`view`,
  `selected`); reload resets to dashboard and **nothing is shareable/bookmarkable**.
  Add React Router so `/program/CRDPOST`, `/graph`, `/query?q=...` are deep-linkable.
  *(S–M)* This is the most visible product gap.

**Search, filters, sorting**
- **No global search** and **no table filtering/sorting** in `Programs.jsx`. For 1k+
  programs the flat table is unusable. Add a search box, column sort, and facet filters
  (root / dead / language / community / needs-review). *(S)*

**Export & sharing**
- **No export buttons.** Add "Export JSON/CSV/GraphML" on programs, graph, lineage, and
  capabilities once §5 #1 lands. Add "copy link" to any view. *(S)*

**Lineage visualization**
- **Lineage has data but no diagram.** `/api/program/{pid}/lineage` returns flows;
  the UI shows them as text at best. Add a flow diagram view (§5 #7). *(M)*

**Graph usability at scale**
- `CallGraph.jsx` is a hand-rolled SVG layered layout — elegant for ~15 nodes, but **no
  zoom/pan, no node search, no collapse, no filtering** by edge type/confidence. For
  real estates add pan/zoom, focus-on-node, and a confidence threshold slider. *(M)*

**Auth & multi-user**
- **No authentication/authorization at all** (CORS is `allow_origins=["*"]` in
  `api.py`). Fine for a local demo; a hosted product needs login, per-tenant data
  isolation, and source-path access control beyond the current sandbox check. *(M–L)*

**Loading / error / empty states**
- Per-view loading/error exist via `useData`, but they're minimal ("Loading…", raw
  error string). Add skeletons, retry buttons, and **empty/first-run states** (e.g.
  "no source scanned yet — scan to begin"). The top-level health error in `App.jsx`
  prints `String(e)`. *(S)*

**Scan UX**
- Rescan is fire-and-forget (`App.jsx` `rescan`); **no progress, no per-file status, no
  result toast**. Long scans look frozen. Add progress + a summary toast. *(S–M)*

**Accessibility**
- Nav and node clicks are mouse-oriented `<button>`/`<g onClick>`; SVG nodes aren't
  keyboard-focusable and lack ARIA labels; color is the only signal for
  root/dead/dynamic (red/green/amber) — **a colorblindness problem**. Add keyboard
  navigation, ARIA roles, focus styles, and non-color status cues (icons/text). *(M)*

**Responsive / mobile**
- Fixed sidebar + wide tables + fixed-width SVG graph — **not responsive**. Add a
  collapsible sidebar and horizontally scrollable/stacked tables for tablet/mobile. *(M)*

**Evidence drill-down consistency**
- The graph edge panel shows evidence/confidence well; make this consistent everywhere
  (every fact in tables/detail should be click-to-evidence, reusing the existing
  source viewer `/api/source`). *(S–M)*

---

## 7. Bottom line

- **AWS** is transform-first, managed, and finishes the job (running modern Java or a
  rehosted runtime on AWS). Its weakness is trust/auditability, openness, data
  sovereignty, and cost/lock-in. *(AWS specifics here are model knowledge —
  verify against the URLs in §0.)*
- **MIP** is understanding-first, open, portable, offline, and **evidence+confidence on
  every fact**. It is genuinely **ahead** on data lineage as a queryable artifact,
  explicit blast-radius, and explainability/openness; **comparable** on
  discovery/graph/capability detection; and **behind** on COBOL→Java transformation,
  managed runtime, and very-large-scale (today).
- **Best next moves** that widen MIP's moat without abandoning the thesis: **export +
  sequence diagrams + business-rule extraction + scan diff** (Tier 1), then a
  **test-gated, evidence-citing COBOL→Java draft** (Tier 2) so MIP can answer the
  transformation question on its own honest terms. In the app: **router/deep-links,
  search/filters, export, and a lineage diagram** are the highest-leverage product gaps.
