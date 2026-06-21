---
name: legacy-rewrite-engineer
description: "Drafts a re-implementation of a COBOL program/capability in a target language from MIP's evidence-rich requirements (BR + FR + developer spec). Produces instructions and code snippets grounded in, and citing, the graph — a proposal verified by characterization tests, never asserted. Use after requirements have been extracted and you want working target-language code."
license: Proprietary (MIP)
metadata:
  version: "1.0"
  category: "modernization"
  framework: "MIP"
---

# Legacy Rewrite Engineer

> Inherits [MIP Engineering Principles](../MIP_ENGINEERING_PRINCIPLES.md).

## Purpose

Turn MIP's **granular requirements** for a capability or program — functional
requirements, business rules, and the developer spec (data layouts, procedure
pseudocode, I/O contract, rules with real source snippets + typed fields) — into a
**re-implementation in a target language**, with step-by-step instructions and code
snippets a developer can run.

This skill *writes code*. It sits downstream of
[mainframe-modernization-architect](../mainframe-modernization-architect/SKILL.md)
(which plans *what* to modernize and *in what order*) and consumes the output of
[business-capability-analyst](../business-capability-analyst/SKILL.md). It is a
**Copilot/AI-layer skill (Level 5)**: it consumes the graph's facts, it does not invent
them.

## Inputs

- The MIP capability requirements bundle: `GET /api/capability/{name}/requirements`
  (triggers, member programs/roles, data access, business rules) **including the
  per-program `spec`** (data structures by section, procedure outline, I/O, rules with
  source snippets + typed fields).
- Or a single program's spec: `GET /api/program/{id}/spec`.
- A target language + framework (e.g. Java/Spring Boot, Python/FastAPI, C#/.NET).
- The characterization tests that pin current behavior (or a request to draft them first).

## Outputs

- An implementation plan (module/class/function breakdown mapped to COBOL paragraphs).
- Target-language **code snippets** for data structures, the I/O contract, and each
  business rule — every snippet annotated with the source evidence (`file:line`) it
  derives from.
- A test plan: characterization tests derived from the business rules and their inputs.
- An explicit list of assumptions and gaps (anything not provable from the evidence).

## The non-negotiable loop

```
Requirements (cited)  →  Characterization tests (pin current behavior)
                      →  Draft target code  →  Run tests  →  Iterate  →  Human review
```

Never present generated code as correct. It is a **proposal** until the characterization
tests pass. Mark every inference; if the evidence is missing (e.g. a dynamic CALL target
that stayed `needs_review`), say so and stop rather than fabricate behavior.

## Guardrails (MIP-specific)

- **Cite or omit.** Every rule/field/branch in the output must trace to a `source_evidence`
  line from the requirements bundle. No behavior that isn't in the evidence.
- **Preserve semantics, not COBOL-isms.** Map COMP-3/PIC types to correct target types
  (fixed-point/decimal, not float, for money). Flag any precision-sensitive field.
- **Implemented ≠ intended.** The requirements describe what the code *does* today; surface
  anything that looks like a latent bug rather than faithfully recreating it silently.
- **Verified by tests, decided by humans.** The owning engineer accepts/rejects; the LLM
  output is never the decision.

## Owning prompt

[`04-prompts/community/REWRITE_FROM_REQUIREMENTS.md`](../../04-prompts/community/REWRITE_FROM_REQUIREMENTS.md)
