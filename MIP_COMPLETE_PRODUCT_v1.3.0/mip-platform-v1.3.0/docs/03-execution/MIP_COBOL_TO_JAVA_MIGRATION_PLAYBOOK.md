# MIP COBOL-to-Java Migration Playbook

## Goal

Migrate a selected COBOL capability to idiomatic Java while preserving externally observable behavior.

## Preconditions

- source scope is fully inventoried
- copybooks and files are documented
- call and execution dependencies are known
- representative input data exists or approved synthetic data is created
- original behavior can be executed or characterized
- acceptance criteria are approved

## Phase 1: Migration Specification

Create a compartmentalized specification covering:

- exact source programs
- copybooks
- JCL and runtime parameters
- files and record layouts
- external calls
- SQL/CICS/VSAM behavior
- numeric rules
- error behavior
- target directory
- excluded scope
- verification method

## Phase 2: Java Project Structure

Recommended:

```text
target/java/<workflow>/
├── pom.xml or build.gradle
├── src/main/java/<package>/
│   ├── model/
│   ├── io/
│   ├── service/
│   └── util/
└── src/test/
    ├── fixtures/
    ├── unit/
    ├── integration/
    └── equivalence/
```

Use JUnit 5 and AssertJ. Use a logging facade. Do not add frameworks unless required.

## Phase 3: Copybook-to-Model Translation

For every record:

- preserve total length
- preserve field order and offsets
- model PIC semantics
- use `BigDecimal` for decimal business values
- implement explicit codecs
- preserve spaces, signs, scale, padding, and truncation
- test round-trip serialization

Do not use Java object serialization for record interchange.

## Phase 4: File I/O Abstractions

Create only required interfaces:

- sequential fixed-record reader/writer
- indexed lookup abstraction
- record codec
- test fixture adapter

Keep production access mechanics separate from business logic.

## Phase 5: Business Logic Translation

Translate behavior into cohesive Java components:

- orchestrator
- control-break detector
- lookup/resolution services
- calculators
- identifier generation
- result/error mapping

Preserve operation order, intermediate precision, and final rounding.

## Phase 6: Executable Original Harness

Prefer compiling the original or minimally adapted program with GnuCOBOL.

The harness must:

- accept deterministic file locations and parameters
- use controlled fixtures
- produce stable outputs
- expose return code and diagnostics
- avoid changing business logic

When direct execution is impossible, create characterization tests from validated production examples and document the limitation.

## Phase 7: Equivalence Verification

Compare:

- output bytes
- record counts
- record order
- database/file mutations represented as snapshots
- return codes
- error outputs
- numeric calculations

Any approved difference must be recorded in an ADR.

## Phase 8: Performance and Operability

Measure equivalent workload. Do not set arbitrary targets without baseline evidence.

Capture:

- throughput
- memory
- latency
- restart behavior
- diagnostics
- idempotency

## Completion Criteria

Migration is complete only when equivalence tests pass, architecture decisions are documented, and unresolved differences are approved.
