# 5. Business-Rule Extraction

**Business value.** Decades of business policy are buried inside COBOL `IF`,
`EVALUATE` and `COMPUTE` statements — the real rules that decide whether a card is
approved or how interest is charged. MIP surfaces these as readable "rule cards" so
business analysts can review what the system actually does, and so nothing is lost when
the logic is rebuilt.

## What MIP does

MIP scans each program for decision and calculation logic and emits a rule card per
rule: a stable ID, the exact condition, the action, a plain-English statement, the
fields involved, and the source evidence line.

**An important honesty boundary:** the *condition* MIP quotes is a **confirmed fact** —
it is the real source line. The *kind* label ("validation", "calculation") and the
*plain-English statement* are MIP's **interpretation**, so each rule is flagged
`validation_status: "inferred"` with confidence below 1.0. The machine reads the code;
a human confirms the meaning.

## Real sample output

**`CRDVAL` — a validation rule (`/api/program/CRDVAL/rules`):**

```json
{
  "id": "CRDVAL-R001",
  "kind": "validation",
  "condition": "CARD-STATUS = 'A'",
  "action": "MOVE 0 TO LK-RETURN-CODE",
  "statement": "When CARD-STATUS is equal to 'A', then move 0 to lk-return-code.",
  "fields": ["CARD-STATUS"],
  "source_evidence": "COBOL/CRDVAL:13",
  "confidence": 0.6,
  "validation_status": "inferred"
}
```

**`INTCOMP` — a calculation rule (`/api/program/INTCOMP/rules`):**

```json
{
  "id": "INTCOMP-R001",
  "kind": "calculation",
  "condition": "ACCT-BALANCE = ACCT-BALANCE * 1.015",
  "statement": "Set ACCT-BALANCE to ACCT-BALANCE * 1.015.",
  "fields": ["ACCT-BALANCE"],
  "source_evidence": "COBOL/INTCOMP:11",
  "confidence": 0.6,
  "validation_status": "inferred"
}
```

## What this means

- The card-validation rule tells the business, in plain language, that **a card status
  of `'A'` means approved** (return code 0) — recovered straight from the code.
- The interest rule reveals a **1.5% monthly factor** (`* 1.015`) applied to the account
  balance — exactly the kind of embedded policy that must be preserved and re-approved
  during modernization.
- Both are marked **`inferred`, confidence 0.6**, with the precise source line. MIP
  hands analysts a verifiable draft, never a silent assertion — the interpretation is a
  *proposal* to confirm, the underlying condition is *fact*.
