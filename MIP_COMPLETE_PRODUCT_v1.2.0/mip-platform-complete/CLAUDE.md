# MIP Agent Operating Contract

These instructions apply to all repository work.

## 1. Think Before Coding

- State material assumptions before implementation.
- Read the nearest architecture, skill, and test files before changing code.
- Present materially different interpretations instead of silently choosing one.
- Prefer evidence from source files, metadata, tests, and indexes over inference.
- When information is missing, record the unknown explicitly. Do not invent facts.

## 2. Simplicity First

- Implement the smallest design that satisfies the verified goal.
- Do not create speculative abstractions, plug-in systems, services, or configuration.
- Prefer deterministic parsing before LLM interpretation.
- Prefer SQLite and NetworkX locally until scale measurements justify migration.
- Split a component only when responsibilities or tests show a real boundary.

## 3. Surgical Changes

- Change only files required by the active specification.
- Match the repository's existing style and naming.
- Do not refactor adjacent code unless the requested change makes it necessary.
- Remove only artifacts made obsolete by the current change.
- Every changed line must trace to a requirement, defect, test, or documented decision.

## 4. Goal-Driven Execution

For non-trivial work:

```text
1. State the goal and success criteria.
2. Create or update tests that prove the goal.
3. Implement the minimum solution.
4. Run validation.
5. Continue until success criteria pass or a concrete blocker is documented.
```

Do not stop after producing a plan when implementation is requested.
Do not ask for permission to perform the next obvious in-scope step.
Do not defer solvable issues to future work.

## 5. Evidence Before Conclusions

Every discovered fact must include:

- source file
- source line or range when available
- extraction method
- confidence
- validation status

Every inferred capability or modernization recommendation must distinguish:

- observed fact
- deterministic derivation
- probabilistic inference
- human-approved conclusion

## 6. Work Ledger Discipline

Before processing an artifact:

1. Check `memory/catalog.txt`.
2. Check `memory/todo.list`.
3. Atomically mark the item `IN_PROGRESS`.
4. Process it once.
5. Write generated knowledge.
6. Append relationships.
7. Mark it `DONE` or `BLOCKED`.
8. Record the outcome in `memory/processed.log`.

Never process a `DONE` item again unless its content hash changed.

## 7. Source Protection

- Treat `mfcode/` as read-only.
- Never rename, reformat, or translate source in place.
- Generated material belongs under `knowledge/`, `output/`, or a language-specific migration directory.
- Preserve fixed-width records, encoding, numeric semantics, truncation, rounding, ordering, and error behavior.

## 8. Modernization Verification

A migration is incomplete until:

- original behavior is executable or characterized
- representative fixtures exist
- output is compared byte-for-byte where applicable
- numeric and encoding semantics are verified
- edge cases and failure paths pass
- deviations are documented and approved

## 9. Documentation Rules

- Use clear business names while preserving original technical identifiers.
- Do not claim business meaning without evidence.
- Use Mermaid for generated diagrams.
- Keep canonical facts in indexes; do not create conflicting copies.
- Update `docs/00-governance/MIP_CANONICAL_FILE_INDEX.md` when adding authoritative documents.
