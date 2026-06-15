# 4. Field-Level Data Lineage

**Business value.** "Where does this number come from, and where does it go?" is one of
the hardest questions on a mainframe — and one regulators, auditors and migration teams
ask constantly. MIP traces individual data fields from database columns into program
variables and back out again, with the exact source line as proof. That makes data
flows auditable instead of mysterious.

## What MIP does

MIP reads each program's data movements and produces field-to-field flows:

- **SQL reads** — a database column flows into a program variable.
- **SQL writes** — a program variable flows out into a database column.
- **COMPUTE** — a calculated value derived inside the program.

Every flow records its kind and the precise file:line of evidence.

## Real sample output

**`STMTDRV` — reading from the database (`/api/program/STMTDRV/lineage`):**

```json
"flows": [
  { "src": "CARD_MASTER.CARD_NUMBER",     "dst": "CARD-NUMBER",  "kind": "sql-read", "evidence": "COBOL/STMTDRV:12" },
  { "src": "CARD_MASTER.CURRENT_BALANCE", "dst": "CARD-BALANCE", "kind": "sql-read", "evidence": "COBOL/STMTDRV:12" }
]
```

**`PAYUPD` — writing to the database (`/api/program/PAYUPD/lineage`):**

```json
"flows": [
  { "src": "PAY-CARD-NUMBER", "dst": "PAYMENT.CARD_NUMBER", "kind": "sql-write", "evidence": "COBOL/PAYUPD:11" },
  { "src": "PAY-AMOUNT",      "dst": "PAYMENT.PAY_AMOUNT",   "kind": "sql-write", "evidence": "COBOL/PAYUPD:11" }
]
```

**`INTCOMP` — a computed value (`/api/program/INTCOMP/lineage`):**

```json
"flows": [
  { "src": "ACCT-BALANCE", "dst": "ACCT-BALANCE", "kind": "compute", "evidence": "COBOL/INTCOMP:11" }
]
```

## What this means

- You can answer **"which programs read or write the `PAYMENT` table, and through which
  fields?"** directly — vital for data governance, sensitive-data tracing, and planning
  which programs must move together in a migration.
- Each flow points to the **exact source line** (`COBOL/PAYUPD:11`), so the claim is
  verifiable by anyone, not taken on trust.
- The `compute` flow on `INTCOMP` shows MIP captures not just I/O but **where values are
  transformed** — the seed of the business-rule extraction in
  [05-business-rules.md](05-business-rules.md).
