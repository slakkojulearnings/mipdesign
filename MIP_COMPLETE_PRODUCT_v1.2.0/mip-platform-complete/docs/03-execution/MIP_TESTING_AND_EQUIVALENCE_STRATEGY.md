# MIP Testing and Equivalence Strategy

## Test Layers

1. Parser unit tests
2. Metadata validation tests
3. Relationship/graph tests
4. Documentation golden tests
5. Original-program characterization tests
6. Java unit and integration tests
7. Cross-runtime equivalence tests
8. Performance and restart tests

## Byte Equivalence

For fixed-length records compare raw byte arrays, not trimmed strings.

Verify:

- exact length
- encoding
- padding
- signed numeric representation
- packed/binary formats when applicable
- decimal scale
- record ordering
- newline behavior

## Numeric Equivalence

Test:

- positive and negative values
- zero
- maximum field values
- fractional values
- intermediate rounding
- truncation
- overflow behavior
- invalid numeric data

## Sequential Processing

Test:

- empty file
- single record
- first/last control break
- repeated keys
- unsorted input when sorting is assumed
- premature EOF
- malformed length

## Golden Fixtures

Every fixture includes:

```text
input/
expected-original/
expected-target/
metadata.json
```

`metadata.json` records source program hash, compiler/runtime version, encoding, parameters, and creation method.

## Decision Rule

No target implementation is accepted solely because business-level totals match. Interface-level bytes and observable side effects must match unless an approved specification changes them.
