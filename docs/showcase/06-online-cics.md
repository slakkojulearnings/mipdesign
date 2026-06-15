# 6. The Online (CICS) Layer

**Business value.** Mainframes do more than overnight batch — they run real-time
customer transactions through CICS (think the screen that approves a card swipe in
under a second). These online paths are often the most business-critical and the least
documented. MIP discovers them too: which terminal transaction launches which program,
and what that program reads, links to and sends back.

## What MIP does

MIP parses CICS programs to capture their online interactions — `RECEIVE`/`SEND` screen
maps, `READ` file access, `LINK` to other programs, `WRITEQ` queue writes — and reads
the CICS resource definition (CSD) to map **terminal transactions to their entry
programs**. The result: the online estate is modelled with the same evidence + confidence
discipline as the batch estate.

## Real sample output

**Transaction-to-program mapping** comes from the CSD (`CICS/AUTHCSD`):

```
program,AUTH,STARTS,program,AUTHTRAN,confirmed,1.0,CICS/AUTHCSD:5
```

i.e. terminal transaction **AUTH → AUTHTRAN**, confirmed from the CICS definition.

**`AUTHTRAN` profile** (`/api/program/AUTHTRAN/profile`) shows it is an **online root**
(started by a transaction, run by no batch job):

```json
"callers": [ { "source_id": "AUTH", "rel_type": "STARTS", "validation_status": "confirmed", "confidence": 1.0 } ],
"direct_jobs": [], "executing_jobs": [],
"dependencies": [
  { "rel_type": "CALLS", "target_id": "AUTHVAL",  "target_type": "program", "confidence": 1.0 },
  { "rel_type": "READS", "target_id": "CARDFILE", "target_type": "dataset", "confidence": 1.0 },
  { "rel_type": "USES",  "target_id": "AUTHMAP",  "target_type": "screen",  "confidence": 1.0 }
]
```

**Online interaction sequence** (`/api/program/AUTHTRAN/sequence`), in source order —
this renders as a sequence diagram in the app:

```
AUTHTRAN ->> AUTHMAP : CICS USES   (receive the screen)
AUTHTRAN ->> CARDFILE: CICS READS  (read the card record)
AUTHTRAN ->> AUTHVAL : CICS LINK   (validate the authorization)
AUTHTRAN ->> AUTHMAP : CICS USES   (send the screen back)
```

## What this means

- The real-time **card-authorization path is fully mapped**: terminal transaction
  `AUTH` starts `AUTHTRAN`, which reads the card file, links to `AUTHVAL` to validate,
  and returns a screen — all confirmed from source.
- Online roots are distinguished from batch roots (no job runs `AUTHTRAN`), so leadership
  sees the **customer-facing entry points** as clearly as the overnight ones.
- This online path turns out to be the **single busiest thing in the estate** (millions
  of executions/month) — see [07-runtime-correlation.md](07-runtime-correlation.md).
