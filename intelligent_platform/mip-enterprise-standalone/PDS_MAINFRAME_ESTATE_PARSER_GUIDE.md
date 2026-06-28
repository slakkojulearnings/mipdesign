# PDS Mainframe Estate Parser Guide

Purpose: this document defines the parser and metadata approach for a PDS/PDSE-based mainframe estate. It is written so another system can reuse the same strategy without assuming file extensions or a local folder naming convention.

## 1. Core Principle

Mainframe source normally lives in partitioned datasets:

```text
HLQ.APPLICATION.COBOL(MEMBER)
HLQ.APPLICATION.COPYBOOK(MEMBER)
HLQ.APPLICATION.JCL(MEMBER)
HLQ.APPLICATION.PROCLIB(MEMBER)
```

Do not identify source type only from local file extensions. In many real exports, members have no extension. The parser must use:

- PDS dataset name
- PDS library role
- member name
- content signals
- cross-reference evidence
- optional catalog/CMDB metadata

Every discovered fact must carry:

```text
source dataset / member / line
discovery method
confidence
validation status: confirmed / inferred / needs_review
```

Before parsing, read each member correctly — this is where many tools silently corrupt facts:

```text
- Encoding: try UTF-8, then EBCDIC cp037 (then other codepages cp1047/cp273/cp500), then latin-1;
  record which decode won and lower confidence on a guessed codepage.
- Fixed-format columns: sequence area cols 1-6, indicator col 7 (* or / = comment, - = continuation,
  D = debug line), code cols 8-72, identification cols 73-80 are IGNORED. Never read 73-80 as code.
- Record format (RECFM/LRECL): fixed-block (FB) members may contain no newlines; split by LRECL.
- Binary members (load modules, object decks, DBRM): inventory and flag, never force-parse.
```

## 2. PDS Identity Model

Preserve mainframe identity even after files are exported to Windows/Linux.

Minimum identity fields:

```json
{
  "system": "CARDPROD",
  "lpar": "SYSA",
  "subsystem": "CICS1",
  "dataset_name": "BANK.CARD.COBOL",
  "member_name": "CUST001",
  "member_type": "COBOL",
  "library_role": "application_source",
  "relative_path": "BANK.CARD.COBOL/CUST001",
  "encoding": "IBM-037 or UTF-8",
  "record_format": "FB",
  "lrecl": 80,
  "sha256": "content hash"
}
```

Recommended graph nodes:

```text
PDS_LIBRARY
PDS_MEMBER
PROGRAM
COPYBOOK
JOB
PROC
TABLE
DATASET
DATASET_IDENTITY
TRANSACTION
MAP
MQ_QUEUE
IMS_DATABASE
IMS_SEGMENT
IMS_FIELD
IMS_PSB
DB2_CURSOR
DB2_COLUMN
HOST_VARIABLE
INTERFACE_CONTRACT
CICS_CONTRACT
BUSINESS_RULE
TRANSFORMATION
COPYBOOK_FIELD
COPY_SITE
FIELD
ASSEMBLER_MODULE
PLI_PROGRAM
CONTROL_CARD
SCHEDULER_OBJECT
```

Recommended relationships:

```text
PDS_LIBRARY CONTAINS_MEMBER PDS_MEMBER
PDS_MEMBER DEFINES_PROGRAM PROGRAM
PDS_MEMBER DEFINES_COPYBOOK COPYBOOK
PDS_MEMBER DEFINES_JOB JOB
PROGRAM USES_COPYBOOK COPYBOOK
PROGRAM CALLS PROGRAM
JOB EXECUTES PROGRAM
JOB INVOKES_PROC PROC
PROGRAM READS_TABLE TABLE
PROGRAM WRITES_TABLE TABLE
PROGRAM READS_DATASET DATASET
PROGRAM WRITES_DATASET DATASET
DATASET NORMALIZES_TO_DATASET_IDENTITY DATASET_IDENTITY
PROGRAM DEFINES_BUSINESS_RULE BUSINESS_RULE
PROGRAM DECLARES_CALL_CONTRACT INTERFACE_CONTRACT
INTERFACE_CONTRACT CALL_PASSES_FIELD FIELD
PROGRAM HAS_COPY_SITE COPY_SITE
PROGRAM USES_COPYBOOK_FIELD COPYBOOK_FIELD
FIELD FLOWS_TO FIELD
PROGRAM PERFORMS PARAGRAPH
PROGRAM DEFINES_CICS_CONTRACT CICS_CONTRACT
PROGRAM WRITES_QUEUE MQ_QUEUE
MQ_QUEUE TRIGGERS PROGRAM
HOST_VARIABLE HOST_VARIABLE_BINDS_COLUMN DB2_COLUMN
```

> These lists are the portable minimum. The **complete set this build actually emits** (~150
> relationship types and all node types) is enumerated in `FEATURE_INVENTORY.md`. Node/edge IDs are
> content-addressed (`stable_id`), so a re-scan **upserts rather than duplicates**, and
> `enrich --changed-only` skips unchanged members (a per-member status ledger tracks stale vs done).

## 3. PDS Library Types To Support

The parser should recognize these PDS/PDSE library roles.

| Library Role | Common Dataset Names | Parser Treatment |
|---|---|---|
| COBOL source | `*.COBOL`, `*.COB`, `*.CBL`, `*.SRCLIB` | Parse `PROGRAM-ID`, `CALL`, `COPY`, SQL, CICS, data division |
| Copybooks | `*.COPY`, `*.COPYBOOK`, `*.CPY`, `*.MACLIB` | Parse layouts, fields, `REDEFINES`, `OCCURS`, condition names |
| JCL | `*.JCL`, `*.JOBLIB` | Parse jobs, steps, `EXEC`, DD datasets, condition codes |
| PROC | `*.PROC`, `*.PROCLIB` | Parse PROC parameters, steps, symbolic substitution |
| DB2 DCLGEN | `*.DCLGEN`, `*.DB2COPY` | Parse table/column declarations and host variables |
| DB2 DDL | `*.DDL`, `*.SQL`, `*.DB2` | Parse tables, indexes, views, tablespaces, databases |
| BMS maps | `*.BMS`, `*.MAPLIB` | Parse mapsets, maps, fields |
| CICS CSD | `*.CSD`, `*.CICSDEF` | Parse transaction/program/resource definitions |
| IMS DBD | `*.DBD`, `*.DBDLIB` | Parse databases, segments, keys |
| IMS PSB | `*.PSB`, `*.PSBLIB` | Parse PSB, PCB, database access |
| Assembler | `*.ASM`, `*.ASSEMBLE`, `*.MACLIB` | Parse CSECT, DSECT, macros, copy/include |
| PL/I | `*.PLI`, `*.PL1`, `*.INCLUDE` | Parse procedure, include, calls, SQL |
| REXX/CLIST | `*.REXX`, `*.CLIST`, `*.EXEC` | **Inventory + flag today** (full exec parse planned) |
| Easytrieve | `*.EZT`, `*.EASY` | **Inventory + flag today** (full parse planned) |
| SORT/ICETOOL | `*.SORT`, `*.CNTL`, `*.CONTROL` | Parse sort fields, input/output datasets |
| Scheduler | Control-M, CA7, OPC/TWS exports | Parse schedules, dependencies, calendars |
| MQ definitions | `*.MQ`, `*.MQSC` | Parse queues and channels |
| Load/DBRM/binary | `*.LOAD`, `*.DBRM`, binary PDS | Inventory only unless external metadata exists |

> **Support level in the current MIP build:** COBOL, Copybook, JCL, PROC, DCLGEN, DB2 DDL, BMS, CSD,
> IMS (DBD/PSB), PL/I, Assembler, SORT/ICETOOL, and **MQ** are **parsed into graph facts**.
> REXX/CLIST/Easytrieve and Load/DBRM/binary are **inventoried and flagged** (not yet grammar-parsed) —
> they land as recognizable members for review, never silently dropped. (Cross-check: `FEATURE_INVENTORY.md`.)

## 4. Export Format From Mainframe

Best option: export both source files and a manifest.

Manifest CSV example:

```csv
system,lpar,dataset_name,member_name,library_role,encoding,recfm,lrecl,relative_path
CARDPROD,SYSA,BANK.CARD.COBOL,CUST001,COBOL,IBM-037,FB,80,BANK.CARD.COBOL/CUST001
CARDPROD,SYSA,BANK.CARD.COPY,CUSTREC,COPYBOOK,IBM-037,FB,80,BANK.CARD.COPY/CUSTREC
CARDPROD,SYSA,BANK.CARD.JCL,CARDBAT,JCL,IBM-037,FB,80,BANK.CARD.JCL/CARDBAT
```

If no manifest exists, infer from folder/PDS name and content, but mark confidence lower.

Recommended local layout:

```text
estate_export/
  manifest.csv
  BANK.CARD.COBOL/
    CUST001
    CUSTVAL
  BANK.CARD.COPY/
    CUSTREC
    CARDREC
  BANK.CARD.JCL/
    CARDBAT
  BANK.CARD.PROCLIB/
    CARDPROC
```

## 5. Classification Rules

Classification order:

1. Manifest/library role if supplied.
2. PDS dataset name pattern.
3. Content signature.
4. Cross-reference promotion.
5. Unknown text or binary fallback.

Examples:

```text
PROGRAM-ID.             -> COBOL source
^\s*//\S+\s+JOB          -> JCL
^\s*//\S+\s+PROC         -> PROC
01/05/10 level numbers   -> COPYBOOK candidate
EXEC SQL                 -> COBOL with DB2 or SQL source
DFHMSD / DFHMDI          -> BMS map
DBDGEN / PSBGEN          -> IMS
CSECT / DSECT            -> Assembler
```

Cross-reference promotion:

```text
If program says COPY CUSTREC
and member CUSTREC exists in UNKNOWN_TEXT,
promote CUSTREC to COPYBOOK with inferred confidence.
```

## 6. Baseline Parser Approach

Run baseline parser for every text member. It must be fast, tolerant, and evidence-preserving.

For COBOL:

```text
1. Parse raw program with fast cobol_ast parser.
2. Resolve COPY and COPY REPLACING using copybook resolver.
3. Parse expanded text with fast parser.
4. Persist baseline facts.
5. Never fail the whole scan because one member failed.
```

Baseline COBOL facts:

```text
PROGRAM-ID
divisions
sections
paragraphs
data items
PIC / USAGE / VALUE
REDEFINES
OCCURS / DEPENDING ON
88-level condition names
PERFORM / GO TO control flow (paragraph & section flow graph)
COPY / COPY REPLACING
static CALL
dynamic CALL as needs_review (with the variable name + candidate targets)
CALL USING / RETURNING (interface contract: which fields cross the boundary)
LINKAGE SECTION
PROCEDURE DIVISION USING
EXEC SQL
DB2 cursors (DECLARE/OPEN/FETCH/CLOSE) + column-level reads
host variables -> column binding
CICS LINK/XCTL/START/READ/WRITE
COMMAREA / CHANNEL / CONTAINER contracts, TS/TD queues, HANDLE CONDITION
file-control SELECT
FD record layouts
VSAM file usage
MOVE / COMPUTE field flows
business-rule candidates
AST summary
complexity
```

For JCL/PROC:

```text
JOB
EXEC PGM
EXEC PROC
PROC symbolic parameters
DD datasets
GDG references
DISP read/write intent
COND / IF / THEN / ELSE
step ordering
utility programs
restart/recovery hints
```

For DB2/IMS/CICS/BMS/MQ:

```text
DB2 DDL tables, columns, indexes, views, tablespaces, databases, packages, plans
DCLGEN table + host-variable mapping; cursor column-level reads/joins/filters; host-var -> column binding
IMS DBD databases, segments, keys; DL/I CALL function codes (GU/GN/ISRT/REPL/DLET); PROCOPT
IMS PSB/PCB access and SENSEG sensitivity
CICS transactions, programs, files, maps; COMMAREA / CHANNEL / CONTAINER contracts; TS/TD queues; HANDLE CONDITION
BMS mapsets, maps, fields
MQ queues; MQPUT/MQGET (WRITES_QUEUE / READS_QUEUE); trigger -> started transaction/program
```

### 6.1 Asynchronous flow (MQ) — the hidden seam
Many programs are linked only through **messages**, not direct CALLs. A producer does `MQPUT` to a
queue and returns immediately; later, the message **triggers** a separate consumer (`MQGET`). Capture
it so the flow stays connected instead of looking like two unrelated islands:

```text
PRODUCER  WRITES_QUEUE  MQ_QUEUE      (MQPUT)
MQ_QUEUE  TRIGGERS      PROGRAM       (the consumer is a ROOT DRIVER — it has no caller in the code)
CONSUMER  READS_QUEUE   MQ_QUEUE      (MQGET)
```

A program that copies MQ structure copybooks (e.g. `CMQMDV`, `CMQODV`) is doing messaging — flag it.
Miss the queue+trigger link and a producer and consumer appear unrelated when one silently feeds the
other. (This is the same async hop a message arrival uses to start a CICS transaction or a batch job.)

## 7. Deep Parser Approach

ANTLR/deep parser should not be on the synchronous scan path for a 200K-file estate.

Use deep parser as persistent enrichment:

```text
baseline scan all members
select high-value programs/bundles
run ANTLR/deep parser with hard timeout
persist AST, diagnostics, and materialized facts
skip unchanged content on future runs
```

Store parse status:

```text
baseline parser: cobol_ast
deep parser: antlr4_deep_parser
deep parse status: completed / failed / timeout / not_requested
last deep parsed: timestamp
parser diagnostics: grammar errors, timeout, dialect warning
```

## 8. How To Select Deep Parser Targets

Use score-based priority.

```text
score =
  root_driver * 30
+ service_candidate * 25
+ dynamic_call_count * 10
+ db2_statement_count * 8
+ cics_contract_count * 8
+ copybook_complexity * 6
+ data_write_count * 6
+ sensitive_data_touch * 10
+ low_confidence_facts * 5
+ changed_since_last_scan * 20
```

Deep parser modes:

```text
roots              root driver programs first
degree             graph hubs first
changed            changed files only
service-candidates likely Java service boundaries
data-critical      data owners/writers first
user-selected      explicit program or bundle
validation-sample  representative parser-quality sample
```

Recommended order:

```text
1. Root drivers
2. Service candidates
3. High-risk data writers
4. Dynamic-call programs
5. Changed programs
6. Validation samples
```

## 9. Bundle Selection For Deep Parse

Do not deep parse only one program when the goal is modernization. Build a bundle.

For selected program `CUST001`, include:

```text
CUST001
called programs
caller programs
copybooks used by all included programs
programs receiving CALL USING arguments
CICS linked programs
JCL jobs that execute it
PROC steps around it
DB2 DCLGEN members
tables/files/datasets it reads or writes
BMS maps and CICS transaction definitions
IMS DBD/PSB/PCB if referenced
```

Output:

```text
bundle_id
root_program
included_members
included_pds_libraries
included_relationships
missing_or_unresolved_members
confidence
validation_status
```

## 10. Copybook And Record Layout Handling

Copybooks are central to modernization. Capture both source layout and materialized program-site layout.

Required facts:

```text
COPYBOOK declares COPYBOOK_FIELD
PROGRAM has COPY_SITE
COPY_SITE expands COPYBOOK
COPY_SITE declares materialized FIELD
FIELD materializes COPYBOOK_FIELD
FIELD derived from COPYBOOK_FIELD
```

For `COPY REPLACING`:

```text
COPY CARDCPY REPLACING ==CARD== BY ==AUTH==
```

Store:

```json
{
  "copybook": "CARDCPY",
  "copy_site": "CALLER line 25",
  "replacement_pairs": [{"from": "CARD", "to": "AUTH"}],
  "original_field": "CARD-NO",
  "materialized_field": "AUTH-NO"
}
```

Scale rule:

```text
Small copybooks: materialize all fields.
Large copybooks: materialize used fields plus top-level context.
Always retain the full parser payload for documentation.
```

## 11. Data Insights Required For Modernization

The parser output must support these data insights:

```text
data inventory
field catalog
read/write matrix
CRUD by program/job/transaction
field-level lineage
copybook ownership
CALL/LINKAGE contracts
CICS COMMAREA contracts
DB2 host-variable to column binding
VSAM file layout and dataset binding
dataset identity normalization
sensitive-data classification
business-rule to field mapping
data ownership scoring
migration readiness scoring
test-data requirement extraction
dead-code / unreachable-program detection (no caller and no entry edge)
orphan members and dangling (unresolved) targets — kept and flagged, never dropped
deep-enrichment coverage rollup: baseline-only vs deep-enriched vs failed
static-vs-runtime reconciliation (graph-reachable but never scheduled/observed = suspect dead)
```

Card-domain examples:

```text
Customer
Account
Card
Authorization
Payment
Posting
Balance
Credit Limit
Statement
Interest
Fee
Delinquency
Dispute
Fraud
PCI / PAN
```

Do not hard-code domain names as final truth. Use graph-derived evidence:

```text
tables written
copybooks used
jobs and transactions
business rule fields
DB2/VSAM ownership
runtime observed calls
dataset/catalog metadata
```

## 12. External Evidence Imports

Static source is not enough. Import runtime and catalog evidence.

Runtime call evidence:

```json
[
  {
    "source_program": "CUST001",
    "target_program": "CUSTVAL",
    "count": 42,
    "environment": "PROD",
    "job": "CUSTJOB",
    "transaction": "CU01",
    "source_system": "SMF"
  }
]
```

Catalog dataset evidence:

```csv
raw_dataset,canonical_dataset,dataset_type,owner,application
CARD.AUTH.OUT(+1),CARD.AUTH.OUT,GDG,CARDS,CARD-AUTH
```

Persist separately:

```text
OBSERVED_CALLS
CATALOG_DESCRIBES_DATASET
CATALOG_ALIASES_DATASET
```

Do not overwrite static `CALLS`; runtime evidence should complement source evidence.

## 13. Parser Output Contract

Every parser should emit a common fact envelope.

```json
{
  "entity_kind": "RELATIONSHIP",
  "relationship_type": "CALLS",
  "source": "PROGRAM:CUST001",
  "target": "PROGRAM:CUSTVAL",
  "source_dataset": "BANK.CARD.COBOL",
  "source_member": "CUST001",
  "line_start": 125,
  "evidence_text": "CALL 'CUSTVAL' USING CUST-REC",
  "discovery_method": "baseline-cobol-parser",
  "confidence": 0.95,
  "validation_status": "confirmed"
}
```

Uncertain example:

```json
{
  "relationship_type": "DYNAMIC_CALL",
  "source": "PROGRAM:CUST001",
  "target": "UNRESOLVED:WS-PGM",
  "evidence_text": "CALL WS-PGM",
  "confidence": 0.40,
  "validation_status": "needs_review"
}
```

## 14. Commands In MIP Standalone

Analyze estate:

```powershell
python -m mip_intel.cli --db data\mip.db analyze F:\path\to\pds_export
```

Run deep enrichment:

```powershell
python -m mip_intel.cli --db data\mip.db enrich --priority roots --top-n 100 --timeout 120
python -m mip_intel.cli --db data\mip.db enrich --priority degree --top-n 100 --timeout 120
python -m mip_intel.cli --db data\mip.db enrich --priority changed --changed-only --top-n 100
```

Check parser status:

```powershell
python -m mip_intel.cli --db data\mip.db parse-status CUST001
```

Import external evidence:

```powershell
python -m mip_intel.cli --db data\mip.db import-runtime runtime_calls.json --source-system smf
python -m mip_intel.cli --db data\mip.db import-catalog catalog.csv --catalog-source idcams
python -m mip_intel.cli --db data\mip.db external-evidence
```

Inspect modernization bundle:

```powershell
python -m mip_intel.cli --db data\mip.db required-files CUST001 --depth 8 --limit 5000
python -m mip_intel.cli --db data\mip.db export-bundle CUST001 --output out\CUST001
```

## 15. Quality Gates

Before using parser facts for modernization:

```text
evidence exists for every node and edge
confidence is between 0 and 1
dynamic calls are visible as needs_review
unresolved copybooks are visible as needs_review
COPY REPLACING materialization is tested
DB2 host-variable binding is tested
CICS COMMAREA fields are tested
JCL PROC expansion is tested
dataset identity normalization is tested
external runtime/catalog evidence is imported where available
scorecard precision/recall is measured against ground truth
```

Modernization output is decision-grade only when these are present:

```text
interface contracts
data ownership
field-level lineage
copybook layout mapping
dataset/table identity
runtime/catalog evidence for dynamic behavior
evidence and confidence on every conclusion
```

## 16. Known Limits

Be explicit about limits:

```text
ANTLR deep parse is dialect-dependent.
Static source cannot prove all runtime behavior.
Catalog reconciliation depends on external metadata quality.
PDS exports may lose encoding, sequence columns, or catalog context if manifest is missing.
Large copybooks must be bounded in graph projection.
Full AST payloads can become large; sidecar or compressed storage may be needed later.
```

### 16.1 Current scan gaps (verified against this build — improve these)

These are real gaps in the scanner today, listed honestly so they can be closed:

```text
- Rich PDS identity is NOT captured yet. The scan keeps relative-path / member / sha256 / encoding /
  artifact_type, but NOT system / lpar / dataset_name / recfm / lrecl / library_role, and it does not
  read a manifest.csv. (Sections 2 and 4 describe the target identity model.)
  -> add manifest ingestion + these SourceMember fields.
- Codepage breadth: only UTF-8, cp037, and latin-1 are tried. cp1047 / cp273 / cp500 and DBCS/mixed
  (SOSI) members can decode wrong, silently corrupting names and literals.
  -> widen codepages and flag low-confidence decodes.
- Fixed-format columns are handled heuristically (leading-space tolerant), not by exact column
  position. Sequence numbers (cols 1-6), the identification area (cols 73-80), and col-7 continuation
  can perturb parsing of some members.
  -> strip cols 1-6 and 73-80 and honor col-7 continuation precisely.
- One member = one artifact: an instream PROC inside a JCL member, or a DCLGEN that is both copybook
  and SQL, is classified as a single type.
  -> support multi-artifact members.
- Nested / contained COBOL programs: the baseline captures one PROGRAM-ID per member.
  -> split members that contain multiple programs.
- Sensitive-data (PII / PCI / PAN) classification is listed as a target insight (section 11) but is
  not extracted yet.
  -> add a name + PIC + usage classifier with regulatory tagging.
- Compiler / binder LISTINGS (which resolve dynamic CALL targets and COPY expansion) are not ingested.
  -> optional: add listing import to turn needs_review dynamic edges into resolved.
```

## 17. Implementation Summary

The production parser approach should be:

```text
PDS manifest + extensionless scan
-> baseline parser for every text member
-> deterministic resolvers for COPY, PROC, DB2, IMS, CICS, datasets
-> evidence-backed graph facts
-> score-based deep parser enrichment
-> runtime/catalog external evidence
-> validation, corrections, and scorecards
-> modernization insights and bundles
```

This approach supports PDS-based source libraries, extensionless exported members, massive estates, and evidence-backed modernization planning without pretending that parser inference is confirmed runtime truth.

## 18. Worked example — one PDS member, end to end

Walk a single member, `BANK.CARD.COBOL(CUST001)` (extensionless, fixed-format COBOL), from discovery
to a deep-enriched, bundled, modernization-ready unit.

**The source (excerpt):**

```cobol
       IDENTIFICATION DIVISION.
       PROGRAM-ID. CUST001.
       DATA DIVISION.
       WORKING-STORAGE SECTION.
       01  WS-STATUS   PIC X.
           88  CUST-ACTIVE   VALUE 'A'.
       COPY CUSTREC.
       LINKAGE SECTION.
       01  LK-CUST-NO  PIC X(10).
       PROCEDURE DIVISION USING LK-CUST-NO.
           EXEC SQL SELECT NAME, STATUS INTO :WS-NAME, :WS-STATUS
                    FROM CUSTOMER WHERE CUST_NO = :LK-CUST-NO END-EXEC.
           IF CUST-ACTIVE
               CALL 'CUSTVAL' USING LK-CUST-NO
           END-IF.
           GOBACK.
```

**Step 1 — Discover & classify.** The walker finds the member with no extension. Library role
`BANK.CARD.COBOL` (or the content signal `PROGRAM-ID.`) classifies it as `COBOL`:

```json
{"dataset":"BANK.CARD.COBOL","member":"CUST001","artifact_type":"COBOL",
 "classification_basis":"folder:*.COBOL","sha256":"…","confidence":0.95,"validation_status":"confirmed"}
```

**Step 2 — Baseline parse (fast `cobol_ast`).** The preprocessor expands `COPY CUSTREC`; the fast
parser emits facts, each cited to a source line:

| Fact | From | Evidence | Conf | Status |
|---|---|---|---|---|
| PROGRAM `CUST001` | PROGRAM-ID | CUST001:2 | 0.95 | confirmed |
| USES_COPYBOOK `CUSTREC` | `COPY` | :7 | 0.95 | confirmed |
| READS_TABLE `CUSTOMER` (NAME, STATUS) | `EXEC SQL` | :11 | 0.95 | confirmed |
| INTERFACE receives `LK-CUST-NO` | `PROCEDURE DIVISION USING` | :10 | 0.90 | confirmed |
| Business flag `CUST-ACTIVE` (='A') | `88` level | :6 | 0.95 | confirmed |
| CALLS `CUSTVAL` (USING `LK-CUST-NO`) | `CALL` | :13 | 0.95 | confirmed |
| BUSINESS_RULE "when customer active, validate" | `IF` | :12 | 0.60 | inferred |

**Step 3 — Cross-reference promotion.** Member `CUSTREC` had scored `UNKNOWN_TEXT`; because `CUST001`
does `COPY CUSTREC`, it is promoted to `COPYBOOK` (basis `referenced-by-copy-name`, 0.82, inferred).

**Step 4 — Persist.** Assets + relationships + one evidence row (file:line) per fact. Re-scan upserts
by content-addressed id — no duplicates.

**Step 5 — Bundle (for modernization).** `required-files CUST001` gathers the whole unit:

```text
CUST001  + CUSTVAL (called)  + CUSTREC (copybook)  + CUSTOMER (table + its DCLGEN)
         + the JCL job that EXECUTEs it  + datasets it touches
   -> bundle_id, included_members, included_relationships, missing_or_unresolved_members, confidence
```

**Step 6 — Deep enrich (out-of-band).** `CUST001` scores high (root / service-candidate), so the
deep ANTLR parser (hard timeout) adds the full data-division layout, field-level lineage
(`CUSTOMER.NAME → WS-NAME`), and the precise `CALL USING` contract — written back by **supersession**
(replaces the baseline edge, same id, no duplicate). `parse-status CUST001` then shows
`deep parser: completed`.

**Commands:**

```powershell
python -m mip_intel.cli --db data\mip.db analyze F:\estate_export
python -m mip_intel.cli --db data\mip.db node CUST001
python -m mip_intel.cli --db data\mip.db required-files CUST001
python -m mip_intel.cli --db data\mip.db enrich --priority roots --top-n 100 --timeout 120
python -m mip_intel.cli --db data\mip.db export-bundle CUST001 --output out\CUST001
```

**Result:** a cryptic, extensionless PDS member is now an evidence-cited, bundled, deep-parsed unit —
proven facts `confirmed`, reasoning `inferred`, unknowns `needs_review` — ready for the
requirements + rebuild phase.
