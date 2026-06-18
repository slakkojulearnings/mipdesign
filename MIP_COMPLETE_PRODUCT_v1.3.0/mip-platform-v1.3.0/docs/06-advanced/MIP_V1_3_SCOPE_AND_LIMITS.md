# MIP v1.3 Scope and Limits

## What Is Complete

The release provides runnable implementations, CLI commands, API endpoints, persistence, reports, and automated tests for all seven requested capability areas.

## What “Compiler-Grade” Would Strictly Require

A strict compiler-grade claim requires conformance against:

- a named COBOL language standard and vendor dialect
- the actual compiler and version
- all compiler options
- copybook search order
- conditional compilation definitions
- source encoding and code page
- preprocessors and compiler exits
- generated compiler listings
- runtime libraries

MIP provides compiler-oriented static semantics, but it is not itself a certified IBM, Micro Focus, GnuCOBOL, or other vendor compiler. Production migration must validate semantic findings against the original compiler/runtime.

## Known Extension Areas

- complete vendor-specific preprocessor grammars
- every COBOL 2002/2014 object-oriented construct
- all dialect-specific intrinsic functions and directives
- full JCL JES/runtime exits and scheduler variable languages
- symbolic values known only at runtime
- complete CICS/IMS transactional runtime simulation
- workload history and production telemetry correlation
- probabilistic domain naming across organization-specific vocabularies

## Safety Rule

MIP may generate candidates and simulations. Human approval and behavioral tests remain mandatory before changing or retiring production assets.
