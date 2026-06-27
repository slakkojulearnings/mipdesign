# MIP, explained simply
### From a wall of 1980s COBOL to an understood system — and a verified Java/Python rebuild

*Read this and you'll be able to (1) read enough COBOL to follow along, (2) see exactly what MIP
pulls out of it, (3) understand how that becomes a Java or Python app you can trust. One example is
carried the whole way. A "For leadership" box closes each part.*

---

## Part 0 — The problem, in one breath
The systems that run banks, insurers, and governments are written in COBOL and assembler from decades
ago. The people who wrote them have retired. The documentation is wrong or missing. So when a team is
asked to "move this to Java," **they can't even tell what the code does, what it touches, or what will
break.** MIP fixes exactly that: it reads the old code and turns it into a clear, evidence-backed map —
and then helps rebuild it *and prove the rebuild behaves the same.*

---

## Part 1 — What COBOL even looks like (and why it scares people)

Here is a small, realistic COBOL program. Don't panic — we'll read it line by line.

```cobol
       IDENTIFICATION DIVISION.
       PROGRAM-ID. CRDPOST.                         *> the program's name
       DATA DIVISION.
       WORKING-STORAGE SECTION.                     *> the program's variables
       01  WS-ACCOUNT.
           05  WS-BALANCE   PIC S9(7)V99 COMP-3.     *> a number: 7 digits + 2 decimals, "packed"
           05  WS-STATUS    PIC X.                   *> one character
               88  ACCOUNT-OVERDUE  VALUE 'O'.       *> a named flag: status = 'O' means OVERDUE
           05  WS-LATE-FEE  PIC S9(5)V99 COMP-3.
       COPY CARDREC.                                 *> paste in a shared record layout ("copybook")
       LINKAGE SECTION.
       01  LK-CARD-NO       PIC X(16).               *> data passed IN from the caller
       PROCEDURE DIVISION USING LK-CARD-NO.          *> the logic starts; it receives a card number
           EXEC SQL
               SELECT BALANCE, STATUS INTO :WS-BALANCE, :WS-STATUS
               FROM   CARD_MASTER WHERE CARD_NO = :LK-CARD-NO
           END-EXEC.                                 *> read this card's row from the DB2 table
           IF ACCOUNT-OVERDUE
               COMPUTE WS-LATE-FEE = WS-BALANCE * 0.05   *> a business rule: 5% late fee
               CALL 'FEEPOST' USING WS-LATE-FEE          *> hand the fee to another program
           END-IF.
           GOBACK.
```

**The plain-English translation:** *"This program (CRDPOST) takes a card number, looks up that card's
balance and status in the CARD_MASTER table, and if the account is overdue, charges a 5% late fee and
sends it to the FEEPOST program."*

The few things worth knowing to read any COBOL:
- **It's organized in DIVISIONS.** `DATA DIVISION` = the variables; `PROCEDURE DIVISION` = the logic.
- **`PIC` = the shape of a value.** `PIC X(16)` = 16 characters. `PIC S9(7)V99` = a signed number with
  7 digits and 2 decimals. `COMP-3` = stored "packed" (this matters for money — getting the rounding
  wrong is a real bug).
- **`88` levels are business flags.** `88 ACCOUNT-OVERDUE VALUE 'O'` means "the word ACCOUNT-OVERDUE
  is true when status = 'O'." These are pure business meaning.
- **`COPY` pastes in a shared layout** (a "copybook"). One copybook is used by hundreds of programs.
- **`CALL 'X' USING ...`** runs another program and passes data to it — that's a dependency.
- **`EXEC SQL ... END-EXEC`** talks to the DB2 database.

Why it scares people: a real program is **thousands** of lines of this, full of `GO TO`s, dynamic
calls, and copybooks-inside-copybooks. No one can hold it in their head. That's the wall MIP knocks
down.

> **For leadership:** the barrier isn't talent — it's that the code is unreadable at scale and the
> experts are gone. Every modernization starts blind. MIP removes the blindness.

---

## Part 2 — Put that code into MIP. Here's what comes out.

MIP reads the program and turns those lines into **facts** — and every fact carries *where it came
from*, *how sure MIP is*, and a *status*. From the 20 lines above, MIP records:

| What MIP found | From the code | Evidence | Confidence |
|---|---|---|---|
| `PROGRAM` **CRDPOST** | `PROGRAM-ID. CRDPOST` | CRDPOST:2 | confirmed |
| **CALLS → FEEPOST** | `CALL 'FEEPOST'` | CRDPOST:19 | confirmed |
| **USES_COPYBOOK → CARDREC** | `COPY CARDREC` | CRDPOST:11 | confirmed |
| **READS_TABLE → CARD_MASTER** (cols BALANCE, STATUS) | the `EXEC SQL SELECT` | CRDPOST:15 | confirmed |
| **Interface contract**: receives `LK-CARD-NO` | `PROCEDURE DIVISION USING` | CRDPOST:14 | confirmed |
| **Business flag**: `ACCOUNT-OVERDUE` (status='O') | the `88` level | CRDPOST:9 | confirmed |
| **Business rule**: *"When account overdue, late fee = balance × 5%"* | `IF … COMPUTE …` | CRDPOST:17 | inferred |
| **Data lineage**: CARD_MASTER.BALANCE → WS-BALANCE → WS-LATE-FEE | the SELECT + COMPUTE | CRDPOST:15-18 | inferred |

The wall of code is now a small, labeled **map**:

```
        ┌── reads ──►  CARD_MASTER (table)   [BALANCE, STATUS]
 CRDPOST ┼── uses ───►  CARDREC (copybook)
        ├── calls ──►  FEEPOST (program)
        └── rule ───►  "5% late fee when overdue"   (cites CRDPOST:17)
   in:  LK-CARD-NO (16-char card number)
```

Notice the honesty: the things MIP *saw directly* (the CALL, the COPY, the table) are **confirmed**;
the things it *reasoned out* (the rule's meaning, the data flow) are **inferred** — never dressed up as
fact. The 5% rule's *condition and line* are confirmed (they're in the code); the plain-English
*statement* is a proposal a person confirms.

> **For leadership:** MIP converts unreadable code into a queryable, cited map. Every claim traces to a
> line of source. This is what lets you trust it enough to plan a migration around it.

---

## Part 3 — How a person actually *understands* the system in the app

You never read COBOL. You use the screens. A typical "understand this" session:

1. **Search** `CRDPOST` → its profile opens: type, confidence, the source file.
2. **Call graph** → a picture of *what calls CRDPOST* (upstream) and *what CRDPOST calls* (downstream:
   FEEPOST). Now you know its blast radius — what breaks if you change it.
3. **Required files** → the exact set of programs + copybooks + tables you'd need to rebuild it.
4. **Click any link** → a drawer shows the *evidence* (the source line) and *confidence* behind it.
5. **Business rules** → the plain-English rules recovered from the logic, each cited.
6. **Customer journey** → chain the entry points (a screen/transaction or a nightly job) through the
   programs they drive into the data they touch — e.g. *"Post daily card charges"*.

The magic isn't AI cleverness — it's that **everything you see is backed by evidence, and the unknowns
are flagged instead of hidden.** A dynamic call MIP couldn't resolve shows up as `needs_review`, not
silence.

> **For leadership:** an analyst with no COBOL background can map a system in days, not months — and
> defend every conclusion. That collapses the riskiest, slowest phase of any program.

---

## Part 4 — The same engine, on the *real* thing

Real estate code is messier. Here's an actual program from a real banking estate (Rocket BankDemo):

```cobol
       PROGRAM-ID.  BBANK10P.
         05  WS-INPUT-FLAG   PIC X(1).
           88  INPUT-OK      VALUE '0'.        *> real 88-level business flags
           88  INPUT-ERROR   VALUE '1'.
       COPY CBANKDAT.                          *> 5 copybooks pulled in
       COPY CBANKD01.
       COPY CPSWDD01.
       ...
           SET BANK-RETURN-MSG-OFF TO TRUE.
```
On this, MIP captures (verified on a real scan): the program, its **5 copybooks**, its **88-level
flags** (INPUT-OK / INPUT-ERROR — business states), its CICS screen/transaction flow, and the
fields each copybook contributes. A nightly job like `DAILYCRD` is traced
**job → CRDPOST → CRDVAL → BALUPD → CARD_MASTER**, and an unresolved dynamic call is *kept and flagged*
(`needs_review`) rather than dropped.

And **assembler** — the truly cryptic stuff:
```asm
UDATECNV CSECT
         SAVE  (14,12),,*          register save (housekeeping)
         BALR  R12,R0              establish addressability
         USING *,R12
```
Almost no one can read this. MIP **inventories it, classifies it as assembler, links who calls it, and
flags it for deeper review** — so it's on the map and accounted for, even where deep parsing is hard.
Nothing is silently skipped.

> **For leadership:** it works on the real, ugly estate — including assembler — and it's honest about
> what it can and can't yet parse deeply, so you never over-trust the picture.

---

## Part 5 — How this *fills the gap* to a Java or Python app

Understanding is half the value. The other half is using that understanding to **rebuild safely.** The
path is a loop, and the same example flows straight through it:

```
  CRDPOST (COBOL)  →  MIP facts + business rule  →  confirmed requirement  →  Java / Python  →  PROVE
```

**1. The requirement (from the facts, confirmed by a person):**
> *BR-007 — When a card account is overdue, apply a late fee of 5% of the outstanding balance.*
> (cited to CRDPOST:17; an SME confirms the wording.)

**2. The rebuilt code — generated from that requirement, grounded in the facts:**

```java
// Java — implements: BR-007
BigDecimal lateFee(Account a) {
    if (!a.isOverdue()) return BigDecimal.ZERO;
    return a.balance().multiply(new BigDecimal("0.05"))
                      .setScale(2, RoundingMode.HALF_UP);   // money math, done right
}
```
```python
# Python — implements: BR-007
def late_fee(account):
    if not account.overdue:
        return Decimal("0.00")
    return (account.balance * Decimal("0.05")).quantize(Decimal("0.01"), ROUND_HALF_UP)
```
Notice the COBOL `COMP-3` packed number became a **`BigDecimal` / `Decimal`** — not a float — so the
rounding matches the mainframe to the penny. That kind of detail is where naive rewrites silently
corrupt money.

**3. The proof — the part that makes it safe:** run the same input through the *old mainframe* and the
*new code* and compare.
```
   balance = 1,000.00, status = OVERDUE
   Mainframe → 50.00      New Java/Python → 50.00      ✓ equal — safe to switch over
```
The new code is never trusted because the AI wrote it — it's trusted because **it produces the same
answer as the system it replaces.** *AI proposes; the tests decide.*

> **For leadership:** MIP doesn't just generate code — it lets you *prove* the replacement behaves
> identically before cutover. That converts "trust the AI" into "here's the evidence," which is the
> only basis on which you can responsibly retire a 40-year-old system.

---

## Part 6 — What we built to reach the target state (and where we are)

The engine works in layers, each feeding the next:

| Layer | What it gives you | Status today |
|---|---|---|
| **Inventory** | Every program, job, copybook, table found — even extensionless/EBCDIC files | ✅ live |
| **Parse & extract** | Calls, copybooks, tables, fields, business rules, data lineage, control flow | ✅ live |
| **Knowledge graph** | The connected, bounded, searchable map (with evidence + confidence) | ✅ live |
| **Understand** | Roots, clusters, capabilities, customer journeys | ✅ live (capability *naming* improving) |
| **Deep enrichment** | The full COBOL grammar for the richest facts, run as a background tier | ✅ architecture live; tuning speed |
| **Requirements (BR/FR)** | Confirmed, cited business + functional rules | ◻ specified, next |
| **Rebuild (Java/Python)** | Code generated from confirmed requirements | ◻ specified, next |
| **Prove (equivalence)** | Dual-run vs the mainframe — the safety net | ◻ specified, next |

**Honest status:** *understanding the system* is real and working today. *Rebuilding + proving* is
designed and specified, and is the next build phase. We are deliberately doing it in this order —
because you cannot safely rebuild what you have not first understood and proven.

---

## Part 7 — The message for leadership (one slide's worth)
1. **The bottleneck in mainframe modernization is understanding, not coding** — and MIP removes it.
2. **Every fact is evidence-backed and honest** — claims trace to a line of code; unknowns are flagged,
   not hidden. That's what makes the map trustworthy.
3. **It captures the knowledge of retiring SMEs** as durable, queryable facts — before it walks out the
   door. That's a risk most programs ignore.
4. **It closes the loop to Java/Python with proof** — the replacement is verified behavior-equivalent
   before cutover, so AI is finally safe to use on the systems you can't afford to break.
5. **It works on the real, ugly estate today** (COBOL, copybooks, DB2, CICS, even assembler), and the
   rebuild-and-prove phase is specified and underway.

*In one line: MIP turns a feared, unreadable mainframe into an understood, evidence-backed map — and
the engine that rebuilds it in Java/Python and proves the result is right.*
