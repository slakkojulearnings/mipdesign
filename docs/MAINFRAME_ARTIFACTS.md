# Mainframe Artifacts — what MIP parses, what it inventories, and the IMS/MQ roadmap

A real mainframe estate is not just COBOL and JCL. A single shop can hold ~180,000
PDS members, and a large share of them are **compiled/binary** library members
(load modules, DBRMs, compiled maps, IMS control blocks). MIP's first job (Level 1 —
Inventory) is to tell *source we can parse* apart from *binary we can only inventory*,
quickly and without ever garbage-parsing a binary as if it were text.

This document covers:
1. The artifact taxonomy — source/text vs binary/compiled, and what MIP does with each.
2. How MIP handles binaries today (classify, inventory, skip parse) and how a binary's
   *name* can still yield low-confidence relationships.
3. **IMS support** — purpose and scope (roadmap).
4. **MQ support** — purpose and scope (roadmap).

---

## 1. Artifact taxonomy

MIP classifies each member by **content first** (real PDS members are extension-less),
then by **library/folder name**, then by **extension**. Classification reads only a
**capped header** of each file (`scanner.HEADER_CAP`, 64 KB) — every text signature
appears at the top of a member, so the header is enough and we never read a
multi-thousand-line program in full just to classify it.

### Source / text — MIP **parses** these

| Artifact | What it is | MIP action | Signature / hint MIP uses |
|---|---|---|---|
| **COBOL** | Application program source | Parse: PROGRAM-ID, CALLs, COPY, EXEC SQL, EXEC CICS | `IDENTIFICATION DIVISION` + `PROGRAM-ID` |
| **JCL** | Batch job control | Parse: job, steps, `EXEC PGM=` → program | `//NAME JOB`, `EXEC PGM=` |
| **PROC** | Cataloged JCL procedure | Parse as JCL (steps/programs) | `PROCLIB` folder |
| **Copybook** | Shared COBOL data layout (no PROGRAM-ID) | Parse: record/field layout; `USES` edges | level number + `PIC` |
| **DB2 DDL** | `CREATE TABLE` / DDL | Parse: tables, columns | `CREATE TABLE` |
| **BMS / MFS source** | CICS (BMS) / IMS (MFS) screen map *source* | Parse as source (maps to screens) — text macro source | folder/ext hints |
| **CICS CSD / RDO** | Resource definitions: transaction → entry program | Parse: `STARTS` edges (txn → program) | `DEFINE TRANSACTION`, `DEFINE PROGRAM`, `DFHCSDUP` |

> Note: **BMS/MFS *source*** is text and parseable. The **compiled** map (the assembled
> map load member) is binary — see below. Same family, two forms.

### Binary / compiled — MIP **inventories and skips** these

These are the kinds the field reported. MIP classifies each as `artifact_type = "binary"`
(simple, single value — sub-kind is recorded as a name hint, not a new type), records it
in the inventory with its size and evidence, and **does not parse it as source**.

| Artifact | What it is | Relationship it still implies (low confidence, from name) |
|---|---|---|
| **LOADLIB** | Executable load module (link-edited program) | member name = a **program** (the compiled form of a COBOL/PLI/ASM source) |
| **CICSLOAD** | CICS-resident load library | member = a CICS program / compiled map |
| **LSM** | Load/storage member (compiled module) | member = a program/module |
| **DBRMLIB / DBRM** | DB2 *Database Request Module* (bound SQL) | DBRM name ↔ **program**; bound into a DB2 **package/plan** (program ↔ DB2 access) |
| **DBDLIB / DBD** | IMS *Database Descriptor* (DB definition) | DBD = an **IMS database**; programs that use it ↔ that database |
| **PSBLIB / PSB** | IMS *Program Specification Block* (program's DB/TM view) | PSB ↔ **program**; its PCBs ↔ the IMS databases the program touches |
| **MAP** | Compiled BMS/MFS screen map | map = a **screen** used by online program(s) |
| **LDV** | Logical-device / compiled view member | inventory-only; name retained |
| **VOG** | Vendor/object-generated binary member | inventory-only; name retained |

**Why "binary" is one value, not many:** the metadata model stays small. The *kind*
(LOADLIB vs DBRM vs DBD …) is captured by the **library name** the member lives in and
kept in the evidence, so downstream consumers can recover it without a combinatorial
explosion of artifact types.

---

## 2. How MIP handles binaries today

Implemented in `reference-implementation/src/mip/scanner.py`:

1. **Header-only read.** The scanner opens each file and reads at most
   `HEADER_CAP` (64 KB) bytes — never the whole file. Size comes from `os.stat`
   (free). This is the main scan speedup at 180k-member scale.

2. **Binary detection (header-only), checked FIRST.** A header is treated as binary if
   it contains **NUL bytes** or a **high ratio (>30%) of non-text/undecodable bytes**.
   Load modules, DBRMs and compiled maps trip this immediately. Doing this check *before*
   any text classification guarantees a binary is never misread as COBOL/JCL.

3. **Binary library-name hint.** A member that lives in a known compiled library
   (`LOADLIB`, `CICSLOAD`, `LSM`, `DBRMLIB`, `DBDLIB`, `PSBLIB`, `MAP`, `LDV`, `VOG`, …)
   is classified `binary` even if its bytes happen to look like text. This catches
   binaries that decode cleanly but are not source.

4. **Inventory, then skip parse.** A `binary` artifact is recorded in the inventory
   (path, size, evidence) but is **not** handed to the COBOL/JCL/CICS parsers. It is
   never line-counted (`line_count = None`) and never garbage-parsed.

5. **Header-capped text classification.** Non-binary members are classified from the
   decoded header using the existing signatures (COBOL / JCL / DB2 / CICS / copybook),
   then folder, then extension. `line_count` is counted from the header bytes; if the
   file exceeded the cap, `line_count` is left `None` (unknown) rather than triggering a
   second full read.

This is **evidence-based and honest**: a binary is reported as exactly that, with its
evidence, and is never presented as parsed source.

### Optional: recovering low-confidence relationships from binary names

Because a binary's *name* still carries meaning (a LOADLIB member is a program; a DBRM
maps a program to its DB2 access; a DBD/PSB maps a program to IMS databases), MIP can
**propose** relationships from binary names alone. Per MIP principles these are emitted
as `inferred` / `needs_review` with **confidence < 1.0** — useful for filling graph gaps
where no source survives, but never asserted as `confirmed` and always flagged for
review. This is roadmap, not yet implemented; the scanner already preserves the name and
library so the data is there when we build it.

---

## 3. IMS support — purpose & scope (roadmap)

**What IMS is.** IMS has two halves:
- **IMS DB** — a *hierarchical* database. Structure is declared in a **DBD** (Database
  Descriptor); programs access segments via DL/I calls (`CBLTDLI` / `AIBTDLI`, function
  codes like `GU`, `GN`, `ISRT`, `REPL`, `DLET`).
- **IMS TM** — transaction management. A program's database/terminal view is declared in
  a **PSB** (Program Specification Block) made of **PCBs**; online screens are **MFS**.

**What MIP would extract** (mapping IMS onto layers MIP already has):
- **IMS DB access** — DL/I calls in COBOL → `READS` / `WRITES` edges to IMS segments
  /databases, exactly the way DB2 `EXEC SQL` is handled today.
- **IMS transactions / entry points** — IMS transaction → entry program, the same shape
  as the CICS CSD `STARTS` edge (transaction → program).
- **DBD / PSB definitions** — parse DBD to define **IMS databases**, parse PSB/PCB to map
  **programs ↔ the IMS databases** they are authorized to touch (and via which PCB).
- **MFS source** — screen maps, the IMS analogue of CICS BMS.

**Why it matters.** For an IMS shop, leaving IMS out is a graph/lineage/impact **blind
spot**: data lineage stops at the DL/I call, and impact analysis can't see which programs
hit a given segment. Adding IMS removes that blind spot.

**Where it slots in:** Inventory adds DBD/PSB recognition (today classified `binary` and
inventoried — the safe default). Metadata adds IMS database + segment + transaction
entities. Graph adds the `READS`/`WRITES`/`STARTS` edges, after which Reasoning, Copilot
and Modernization work over IMS with no new machinery. **Status: roadmap, not yet
implemented.**

---

## 4. MQ support — purpose & scope (roadmap)

**What MQ is.** IBM MQ is **asynchronous messaging**: programs `MQPUT` messages onto
queues and `MQGET` them off, decoupled in time. A queue can be **trigger**-enabled so
arrival of a message starts a program/transaction.

**What MIP would extract:**
- **Queue producers / consumers** — `MQPUT` → `WRITES queue`; `MQGET` → `READS queue`,
  yielding producer↔consumer edges through the named queue.
- **Trigger programs** — queue → triggered program/transaction (an async entry point,
  analogous to a CICS transaction or a job step as a root-driver).
- **Queue definitions** — queue and channel names as first-class entities.

**Why it matters.** MQ coupling is **hidden** from a pure call/EXEC graph: two programs
that never CALL each other can still be tightly coupled through a queue. Surfacing it:
- makes **impact analysis** correct (a change to the message layout or the consumer ripples
  through the producer even with no direct call), and
- gives modernization **event candidates** — existing MQ flows are the natural seams for
  an event-driven / async target architecture.

**Where it slots in:** Inventory recognizes MQ API usage in source; Metadata adds queue
entities; Graph adds producer/consumer/trigger edges; Modernization reads them as
event-decomposition candidates. **Status: roadmap, not yet implemented.**

---

## Summary

| Concern | Today | Roadmap |
|---|---|---|
| Binary/compiled members | Classified `binary`, inventoried, **skipped for parse** (header-only, fast) | Low-confidence relationship recovery from binary names |
| COBOL / JCL / DB2 / copybook / CICS CSD | Parsed (header-capped classification) | — |
| IMS (DBD/PSB/DL-I/MFS) | DBD/PSB inventoried as `binary` | DB access, transactions, program↔database mapping |
| MQ (MQPUT/MQGET/triggers) | — | Producers/consumers, trigger programs, event candidates |

MIP's rule holds throughout: **understand before transforming**, parse what is genuinely
source, inventory the rest honestly with evidence and confidence, and never present a
binary load module as parsed code.
