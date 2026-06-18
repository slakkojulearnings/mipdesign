# MIP Testing Strategy

## Required layers

- classifier tests for extensionless and misleading files
- parser unit tests per statement/construct
- malformed-source and missing-reference tests
- SQLite repository tests
- graph direction and traversal tests
- pipeline integration tests
- FastAPI contract tests
- CLI smoke tests
- memory-index validation
- migration equivalence tests for translated workloads

## Fixture policy

Use synthetic, license-safe fixtures. Every production defect produces a minimized fixture with confidential identifiers removed.

## Coverage philosophy

Coverage is a signal, not proof. Critical semantic paths—fixed columns, continuations, PIC/USAGE, JCL symbolic processing, SQL operations, encoding, and graph direction—must have explicit assertions.
