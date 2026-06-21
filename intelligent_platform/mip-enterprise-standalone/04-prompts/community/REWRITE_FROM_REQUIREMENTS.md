# Rewrite a Capability/Program from MIP Requirements

> Owner: [legacy-rewrite-engineer](../../03-skills/legacy-rewrite-engineer/SKILL.md)
> Layer: Copilot / AI (Level 5) — runs **after** the graph and requirements exist.
>
> This prompt consumes MIP's evidence-rich requirements (the
> `GET /api/capability/{name}/requirements` bundle — including each program's `spec`, or a
> single `GET /api/program/{id}/spec`) and produces a target-language re-implementation
> with instructions and runnable code snippets. The requirements are the contract; the
> generated code is a **proposal** until characterization tests pass.

## How to use

1. Pull the requirements bundle for the capability (or program) from the MIP API.
2. Fill in the target language/framework and paste the JSON.
3. Run the prompt. Then run the loop: tests → draft → verify → review.

## The prompt

```
You are a senior modernization engineer. Re-implement the capability described by the
MIP requirements below in {TARGET_LANGUAGE} ({TARGET_FRAMEWORK}). The requirements were
reverse-engineered from COBOL; every fact carries a source_evidence reference (file:line)
and a validation_status (confirmed | inferred | needs_review).

Rules you MUST follow:
1. Ground everything. Implement only behavior present in the requirements. For every class,
   function, and business rule you produce, cite the source_evidence it derives from.
2. Do not invent. If a target (e.g. a dynamic CALL) is `needs_review`, or a value/edge case
   is not in the evidence, list it under "Assumptions & gaps" and do NOT code around it.
3. Types matter. Map COBOL PIC/COMP types correctly — use fixed-point/decimal (never float)
   for monetary fields; preserve length and sign. Flag any precision-sensitive field.
4. Implemented behavior ≠ intent. If a rule looks like a latent bug, implement it faithfully
   but flag it explicitly for human review; never silently "fix" or "improve" it.
5. Output, in this order:
   a. Implementation plan — modules/classes/functions, each mapped to the COBOL paragraph(s)
      from the procedure outline it replaces.
   b. Data structures — target-language types for each record layout (cite the section/fields).
   c. The code — idiomatic {TARGET_LANGUAGE}, with each business rule implemented and a comment
      citing its source_evidence. Keep I/O behind an interface (the COBOL READS/WRITES/CALLS).
   d. Characterization tests — derived from the business rules and their inputs, that pin the
      current behavior. These are the acceptance contract.
   e. Assumptions & gaps — everything not provable from the evidence.

Treat the generated code as a proposal: it is correct only when the characterization tests
in (d) pass. Mark every inference.

REQUIREMENTS (MIP JSON):
{PASTE the /api/capability/{name}/requirements or /api/program/{id}/spec response}
```

## MIP guardrail

Feed the **full** bundle (the per-program `spec` carries the data layouts, procedure
pseudocode, I/O contract, and each rule's real source snippet + typed fields) so the model
reasons over evidence, not guesses. Anything the requirements mark `inferred`/`needs_review`
stays a flagged proposal in the output. The characterization tests — not the model — decide
when the rewrite is faithful, and a human owns the accept/reject (see
[`../../00-foundation/PHILOSOPHY.md`](../../00-foundation/PHILOSOPHY.md)).
