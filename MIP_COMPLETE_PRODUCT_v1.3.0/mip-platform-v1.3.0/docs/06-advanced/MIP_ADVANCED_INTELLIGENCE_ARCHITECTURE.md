# MIP Advanced Intelligence Architecture

## Release

MIP v1.3.0

## Purpose

MIP v1.3 adds deterministic, evidence-oriented implementations for seven advanced capabilities:

1. Compiler-oriented COBOL understanding
2. Enterprise JCL expansion
3. Business Rule Extraction Engine
4. Domain Model Discovery
5. Event Discovery
6. Service Boundary Discovery
7. Modernization Simulator

## Processing Architecture

```text
Repository
  ├─ Standard scanner/parsers → SQLite metadata and relationships
  ├─ COBOL semantic analyzer → expanded source, symbol table, CFG, calls, rules
  ├─ JCL expander → resolved PROCs, INCLUDEs, symbolics, overrides
  └─ Intelligence suite
       ├─ structured business rules
       ├─ candidate domain model
       ├─ candidate business events
       ├─ candidate service boundaries
       └─ modernization scenarios
```

## Trust Model

Every result is one of:

- **Observed**: explicitly present in source or metadata
- **Resolved**: deterministically derived from symbols, replacement rules, or graph edges
- **Candidate**: a scored hypothesis requiring review
- **Simulated**: a predicted consequence based on current graph coverage

Candidate and simulated results must not be treated as production truth without review.

## COBOL Semantic Analyzer

Implemented:

- fixed-format and free-format logical-line normalization
- continuation handling
- nested `COPY`
- pseudo-text and identifier `COPY REPLACING`
- copybook cycle detection
- conditional compilation with `>>DEFINE`, `>>IF`, `>>ELSE`, and `>>END-IF`
- data symbol table
- PIC, USAGE, VALUE, REDEFINES, RENAMES
- OCCURS and OCCURS DEPENDING ON
- level-88 condition identification
- paragraph inventory
- PERFORM, GO TO, GO TO DEPENDING ON, and ALTER control-flow edges
- static CALL extraction
- dynamic CALL candidate resolution from VALUE, MOVE, and SET evidence
- IF, EVALUATE/WHEN, COMPUTE, and arithmetic rule extraction
- source and copybook-expansion traceability

This is compiler-oriented static understanding. It does not claim binary equivalence with every proprietary COBOL compiler. Compiler conformance must be verified with the actual compiler, options, copy libraries, and generated listings used by the application.

## Enterprise JCL Expander

Implemented:

- inline and cataloged PROC loading
- nested PROC expansion
- INCLUDE member expansion
- SET processing
- recursive symbolic substitution
- default PROC parameters
- invocation parameter overrides
- cycle and maximum-depth protection
- selected DD override handling
- expansion stack and source trace
- resolved EXEC PGM inventory

Scheduler-specific runtime substitutions and exits remain adapter concerns and require real exports from the target environment.

## Business Rules

Rules are extracted into structured records with:

- kind
- expression
- target when applicable
- implementing program
- source path and line
- evidence text
- confidence

Supported categories include validation, eligibility, authorization, thresholds, calculations, decision tables, branches, and state transitions.

## Domain Model Discovery

The engine combines:

- table names
- files and datasets
- copybooks and fields
- attributes
- graph co-occurrence

It proposes candidate entities, attributes, and associations. These are hypotheses—not automatically approved canonical domain models.

## Event Discovery

Candidate events are derived from:

- table/file/dataset writes
- MQ message production
- transaction starts
- state/status transitions

Candidate consumers are proposed from matching read/GET relationships.

## Service Boundary Discovery

The engine uses:

- program call relationships
- shared data dependencies
- graph communities
- internal/external relationship counts

Outputs include cohesion, coupling, fitness, confidence, shared data, programs, and a recommended extraction pattern.

## Modernization Simulator

Scenarios:

- modify
- retire
- extract-service
- replatform

Outputs:

- blast radius
- required dependencies
- impact paths
- predicted breakages
- risk score
- readiness score
- mitigations
- recommendation

Simulation quality is limited by metadata and relationship coverage.
