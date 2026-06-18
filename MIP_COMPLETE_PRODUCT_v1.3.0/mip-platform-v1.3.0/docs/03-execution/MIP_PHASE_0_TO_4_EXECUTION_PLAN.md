# MIP Phase 0–4 Execution Plan

## Phase 0: Workspace and Governance

Deliver:

- repository structure
- operating instructions
- skill validation
- source protection
- empty ledgers
- test and lint configuration

Exit criteria:

- a new engineer can identify the canonical files
- source code is mounted read-only
- skills pass format validation
- todo claiming works

## Phase 1: Repository Inventory

Deliver:

- recursive file inventory
- content-based artifact classification
- source hashes
- unknown-artifact report
- initial todo ledger

Exit criteria:

- every file has one inventory record
- no file is silently ignored
- file counts reconcile with filesystem counts

## Phase 2: Identity and Basic Metadata

Extract:

- program IDs
- job names and steps
- executed program names
- copybook names and COPY references
- datasets and tables
- transactions and entry programs where available

Exit criteria:

- canonical catalog exists
- duplicate identities are resolved or flagged
- facts include source evidence

## Phase 3: Relationships and Workflow

Build:

- program calls
- job execution
- copybook usage
- table and dataset reads/writes
- job sequencing
- daily batch workflow diagrams

Exit criteria:

- relationship index validates
- unresolved targets are reported
- graph can answer root, caller, callee, producer, and consumer questions

## Phase 4: Documentation and Queryable Knowledge

Generate:

- program documentation
- copybook data dictionaries
- JCL/job documentation
- workflow documentation
- Mermaid diagrams
- natural-language query layer grounded in metadata

Exit criteria:

- documentation coverage is measured
- every generated page links to evidence
- questions are answered from metadata/graph, not unrestricted source guessing

## Translation Gate

COBOL-to-Java migration starts only after the selected scope passes Phases 1–4 and has executable characterization tests.
