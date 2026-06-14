# Mainframe Discovery Platform Roadmap

## Vision

Build a platform that can analyze a largeMainframe codebase (15000+ COBOL programs) and answer questions such as:

* Which job executes a program?
* Which programs update a DB2 table?
* Which copybooks are used by a module?
* What is the batch flow for a business process?
* What programs are impacted by a table change?
* Explain a COBOL module in plain English.
* Generate modernization documentation.

The platform should become a reusable capability for development, support, testing, architecture, modernization, and onboarding teams.

---

# Guiding Principles

## DO NOT start by reading COBOL

The goal is not:

"What does this program do?"

The goal is:

"How is this system organized?"

---

## Build a map before reading code

Think of the application as:

Business Capability
↓
Job / Transaction
↓
Program
↓
Table / File
↓
Business Rule

---

## Graph First, AI Later

Incorrect approach:

COBOL → LLM

Correct approach:

COBOL
↓
Metadata
↓
Knowledge Graph
↓
AI

The graph becomes the source of truth.

---

# Workspace Setup

Create a VS Code workspace.

Structure:

mainframe-discovery/
│
├── mfcode/
│
├── discovery/
│   ├── backend/
│   ├── parsers/
│   ├── graph/
│   ├── knowledge/
│   ├── prompts/
│   ├── tests/
│   └── docs/
│
├── .github/
│
└── README.md

Important:

Treat mfcode as READ ONLY.

Never modify source artifacts.

---

# Phase 1 — Create the Copilot Foundation

Goal:

Create a reusable AI engineering assistant.

File:

.github/copilot-instructions.md

Suggested contents:

You are a principal engineer specializing in:

* Mainframe modernization
* COBOL
* JCL
* DB2
* CICS
* T-SYS card systems
* Knowledge Graphs
* Python 3.13
* FastAPI
* Pydantic v2
* NetworkX
* Neo4j

Rules:

1. Prefer architecture before implementation.
2. Always explain assumptions.
3. Produce production-grade code only.
4. Every component must include:

   * models
   * tests
   * logging
   * error handling
5. Design for 9000+ programs.
6. Support future AI integration.
7. Prefer incremental extraction.
8. Never generate throwaway code.

---

# Phase 2 — Repository Inventory

Goal:

Understand what exists.

Do not parse business logic.

Extract:

* File name
* File type
* Location
* Size
* Last modified date

Expected Output:

Inventory Database

Examples:

COBOL
JCL
COPYBOOK
DB2
CICS

---

# Copilot Prompt

Act as a principal modernization architect.

Design a repository inventory service for a large mainframe codebase.

Requirements:

* 200,000+ files
* Python 3.13
* FastAPI
* Pydantic v2
* Structured logging
* Async architecture

Output:

1. Architecture
2. Folder structure
3. Domain models
4. Data flow
5. Testing strategy

Do not generate code yet.

---

# Phase 3 — Repository Discovery

Goal:

Understand mainframe codebase folder structure.

Questions:

* Where are COBOL programs?
* Where are copybooks?
* Where are JCLs?
* Where are DB2 definitions?
* Where are CICS definitions?

Create metadata.

Output:

Artifact Catalog

---

# Copilot Prompt

Analyze the repository structure.

Create a discovery strategy.

Identify:

* COBOL artifacts
* JCL artifacts
* Copybooks
* DB2 definitions
* CICS definitions

Generate:

1. Discovery workflow
2. Metadata schema
3. Inventory schema
4. Extraction order

Explain reasoning.

---

# Phase 4 — COBOL Parser

Goal:

Extract metadata.

Do not interpret business rules yet.

Extract:

* PROGRAM-ID
* CALL statements
* COPY statements
* EXEC SQL blocks
* File definitions

Expected Result:

Program Catalog

---

# Copilot Prompt

Act as a compiler engineer.

Design a COBOL parser.

Extract:

* PROGRAM-ID
* CALL
* COPY
* EXEC SQL
* FILE references

Requirements:

* Incremental parsing
* Large repositories
* Pydantic models
* Testability

Output architecture only.

Do not generate code yet.

After review:

Generate implementation.

Include:

* models
* parser
* services
* tests
* examples

---

# Phase 5 — JCL Parser

Goal:

Find execution entry points.

Extract:

* JOB
* EXEC PGM
* PROC
* DD statements
* Datasets

Expected Result:

Job Catalog

---

# Copilot Prompt

Design a JCL parser.

Extract:

* JOB
* PROC
* EXEC PGM
* DD
* Dataset references

Create relationships:

JOB → PROGRAM

Output:

1. Models
2. Architecture
3. Parsing strategy
4. Edge cases

---

# Phase 6 — Copybook Parser

Goal:

Understand shared structures.

Extract:

COPY statements.

Create:

PROGRAM → COPYBOOK

relationships.

---

# Phase 7 — DB2 Analysis

Goal:

Understand data lineage.

Extract:

* SELECT
* INSERT
* UPDATE
* DELETE

Identify tables.

Expected Output:

PROGRAM → TABLE

relationships.

---

# Copilot Prompt

Design a DB2 extraction service.

Extract:

* SQL operation
* Table names
* Column names

Create metadata models.

Output architecture only.

---

# Phase 8 — Dependency Graph

Goal:

Create system map.

Nodes:

* Program
* Copybook
* Table
* Job
* Dataset

Edges:

* CALLS
* USES
* EXECUTES
* READS
* WRITES
* UPDATES

---

# Copilot Prompt

Design a graph service.

Support:

* impact analysis
* lineage
* root discovery
* dependency tracing

Output:

1. Architecture
2. Models
3. Storage strategy
4. Query strategy

---

# Phase 9 — Root Program Discovery

Goal:

Answer:

Which jobs execute which programs?

Build:

JOB
↓
PROGRAM
↓
CALLED PROGRAMS

Questions:

* What is the root program?
* What jobs execute this program?
* Which programs are not called by others?

---

# Phase 10 — Natural Language Queries

Goal:

Ask questions.

Examples:

Which programs update CARD_ACCOUNT?

Which jobs call PAYMENT posting modules?

Show call hierarchy for XYZ.

Trace transaction flow.

---

# Copilot Prompt

Design a question-answering system on top of a knowledge graph.

Questions include:

* Trace program flow
* Impact analysis
* Table lineage
* Root discovery

Design:

* retrieval
* graph queries
* context assembly
* hallucination prevention

No implementation yet.

---

# Phase 11 — Business Rule Extraction

Goal:

Explain COBOL.

Example:

IF BALANCE > LIMIT

Explain:

Decline transaction when balance exceeds credit limit.

---

# Phase 12 — Documentation Generator

Generate:

* Program documentation
* Job documentation
* Table documentation
* Call hierarchy diagrams

Output:

Markdown

---

# Phase 13 — Impact Analysis

Questions:

If CARD_ACCOUNT changes:

* Which programs break?
* Which jobs are impacted?
* Which copybooks are affected?

---

# Phase 14 — Modernization Assistant

Future Phase

Capabilities:

* COBOL → Java
* COBOL → Spring Boot
* Batch decomposition
* Service identification
* API generation

---

# Success Criteria

Version 1 is complete when the platform can answer:

1. Which jobs execute program X?
2. Which programs call program X?
3. Which copybooks does program X use?
4. Which tables does program X update?
5. Show end-to-end flow for a job.
6. Identify root programs.
7. Generate dependency diagrams.
8. Explain a COBOL program in plain English.

Only after these work should AI chat and modernization features be added.


A practical suggestion: spend building only Inventory + COBOL Parser + JCL Parser. Resist the temptation to jump to LLMs. Once you can answer "Who calls this program?", "Which job executes it?", and "Which tables does it touch?", the rest of the platform becomes much easier to build.
