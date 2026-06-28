# Scan Gaps Spec — close the discovery/scan gaps (build target)

> Target tree: `mip-enterprise-standalone`. Fixes the six verified gaps in the **scan/discovery**
> layer (see `PDS_MAINFRAME_ESTATE_PARSER_GUIDE.md` §16.1 and `FEATURE_INVENTORY.md` §19). Same
> buildable style as `ENRICHMENT_SPEC.md` / `REQUIREMENTS_PIPELINE_SPEC.md`. Status: **NOT implemented.**
> Date: 2026-06-28.

## Governing principle
The scan is the foundation — every downstream fact inherits its recall and its mistakes. So: **read
each member correctly (encoding + format), preserve its full mainframe identity, never collapse a
member that is really several things, and keep every uncertain decode/classification flagged with
confidence — never silently corrupt.**

## Where it lives today (anchors)
- Encoding/read: `ingestion._read_text` (~line 1446) — `for encoding in ("utf-8","cp037","latin-1")`.
- Classification: `ingestion._classify_path` / `_classify` (folder → content → referenced-promotion).
- `source_member` table (schema.sql) — has path/member/sha/encoding/is_binary/text_status/
  artifact_type/classification_basis/confidence/validation_status; **lacks** dataset/recfm/lrecl/etc.
- COBOL parse: `cobol_ast.parse` → `Unit` with a **single** `program_id`.

---

## Gap 1 — Rich PDS identity + manifest ingestion *(do first — foundational)*
**Problem:** the scan keeps only relative-path/member/sha/encoding/artifact_type. It does not capture
`system / lpar / dataset_name / library_role / recfm / lrecl`, and it reads no manifest — so the
identity model in the guide §2/§4 is not realized.

**Schema:**
```sql
ALTER TABLE source_member ADD COLUMN system TEXT;
ALTER TABLE source_member ADD COLUMN lpar TEXT;
ALTER TABLE source_member ADD COLUMN subsystem TEXT;
ALTER TABLE source_member ADD COLUMN dataset_name TEXT;        -- e.g. BANK.CARD.COBOL
ALTER TABLE source_member ADD COLUMN library_role TEXT;        -- application_source|copylib|jcllib|proclib|loadlib|dclgen|...
ALTER TABLE source_member ADD COLUMN recfm TEXT;               -- FB|FBA|VB|U|...
ALTER TABLE source_member ADD COLUMN lrecl INTEGER;
ALTER TABLE source_member ADD COLUMN detected_codepage TEXT;   -- which codepage actually decoded it
ALTER TABLE source_member ADD COLUMN codepage_confident INTEGER NOT NULL DEFAULT 1;
```
(Optionally also model a `PDS_LIBRARY` asset with `CONTAINS_MEMBER` edges, keyed by `dataset_name`.)

**Manifest:** `analyze <root> [--manifest manifest.csv]`. CSV columns
`system,lpar,dataset_name,member_name,library_role,encoding,recfm,lrecl,relative_path`. Match each
member by `relative_path` (fallback: `dataset_name`+`member_name`). When a manifest row exists, it is
the **highest-precedence classification signal** (library_role → artifact_type) at confidence 0.97;
its recfm/lrecl/encoding seed the read step (Gap 2/3).

**Acceptance:** scanning an estate with a manifest populates all identity columns and classifies by
`library_role`; without a manifest, the columns are inferred from the dataset/folder name where
possible and left null otherwise (never fabricated).

## Gap 2 — Codepage breadth + honest decode confidence *(do first)*
**Problem:** `_read_text` tries only `utf-8 → cp037 → latin-1`; cp1047/cp273/cp500 and DBCS/mixed
(SOSI) members decode wrong **silently**.

**Fix:** widen the candidate list and pick the best decode, recording it:
```
candidates = [manifest.encoding (if given), "utf-8", "cp037", "cp1047", "cp500", "cp273", "latin-1"]
score each successful decode by: printable-ratio + COBOL/JCL token hit-rate (PROGRAM-ID, //, level numbers)
pick the highest-scoring; set source_member.detected_codepage.
if the winner is not utf-8 AND the score margin over the runner-up is small  -> codepage_confident=0
   and cap the member's confidence (<=0.7) / status='needs_review' on encoding.
detect SOSI (shift-out 0x0E / shift-in 0x0F) -> flag DBCS/mixed; do not assume single-byte.
```
**Acceptance:** a cp1047/cp500 member decodes correctly and records its codepage; an ambiguous decode
is flagged `codepage_confident=0` and surfaced in `scan_issue`, not silently accepted.

## Gap 3 — Fixed-format column precision *(parser correctness)*
**Problem:** columns are handled heuristically (leading-space tolerant), not by exact position;
sequence numbers (cols 1-6), the identification area (cols 73-80), and col-7 continuation can perturb
parsing.

**Fix:** add a `normalize_fixed_format(raw, recfm, lrecl)` step **before** classify/parse:
```
- If RECFM is fixed (F/FB...) and lrecl known and the text has no/few newlines -> split into records of length lrecl.
- For fixed-format source: drop cols 1-6 (sequence) and cols 73-80 (identification) from each record.
- Honor col-7 indicator: '*' or '/' = comment line; '-' = continuation of the previous literal/word; 'D' = debug line.
- Record source_format = fixed | free | unknown on the member.
- Free-format (no card columns) is passed through unchanged.
```
Apply in `_read_text`/preprocess so both `cobol_ast` and the deep parser see clean code.

**Acceptance:** a member with sequence numbers in 1-6 and text in 73-80 parses identically to one
without them; a literal continued across col-72 is joined correctly.

## Gap 4 — Multi-artifact members *(completeness)*
**Problem:** one member is classified as exactly one `artifact_type`. But a JCL member can contain an
**instream PROC** (`//NAME PROC … // PEND`) and **instream SYSIN** control cards; a **DCLGEN** is both
a copybook **and** an SQL table contract.

**Schema:**
```sql
CREATE TABLE IF NOT EXISTS member_artifact (
    member_id     TEXT NOT NULL REFERENCES source_member(member_id) ON DELETE CASCADE,
    artifact_type TEXT NOT NULL,    -- JCL | PROC | CONTROL_CARD | DCLGEN | COPYBOOK | ...
    span_start    INTEGER, span_end INTEGER,
    classification_basis TEXT NOT NULL,
    confidence    REAL NOT NULL, validation_status TEXT NOT NULL,
    PRIMARY KEY(member_id, artifact_type, span_start)
);
```
Keep the member's **primary** `artifact_type`; emit a `member_artifact` row per embedded artifact and
run the matching extractor over its line span. DCLGEN members emit both `COPYBOOK` and `DCLGEN` facts.

**Acceptance:** a JCL member with an instream PROC yields both the JOB facts and the PROC facts; a
DCLGEN yields both copybook fields and `DECLARES_TABLE`.

## Gap 5 — Nested / contained COBOL programs *(completeness)*
**Problem:** `cobol_ast.Unit` holds one `program_id`; a member with multiple
`PROGRAM-ID … END PROGRAM` units captures only the first.

**Fix:** parse all program units in a member; emit one `PROGRAM` asset each, plus a
`CONTAINS_PROGRAM` edge from the outer to each nested program. Relationship extraction runs per
program unit (so each nested program's CALLs/COPYs/SQL are attributed correctly).

**Acceptance:** a member with `PROGRAM-ID. A.` … `PROGRAM-ID. B.` … `END PROGRAM B.` … `END PROGRAM A.`
yields two PROGRAM assets and `A CONTAINS_PROGRAM B`.

## Gap 6 — Sensitive-data (PII/PCI) classification *(compliance value)*
**Problem:** §11 lists sensitive-data classification as a target insight, but nothing extracts it.

**Schema / model:**
```sql
ALTER TABLE asset ADD COLUMN sensitivity TEXT;        -- none|pii|pci|phi|financial  (on FIELD/COLUMN/COPYBOOK_FIELD)
ALTER TABLE asset ADD COLUMN regulatory_scope TEXT;   -- e.g. PCI,GDPR  (csv)
-- edges: CLASSIFIED_AS_SENSITIVE (field->scope marker), SENSITIVE_FLOWS_TO (reuse FLOWS_TO + sensitivity)
```
Classifier = name patterns + PIC/usage + table/column hints (config-driven, not hardcoded card):
```
PAN / card-number  : name ~ CARD.*NO|PAN ; PIC X(16)/9(16)        -> pci
SSN                : name ~ SSN|SOC.*SEC                          -> pii
name/address/email : name ~ NAME|ADDR|EMAIL|DOB|PHONE             -> pii
balance/amount/acct: name ~ BAL|AMT|ACCT|SALARY                   -> financial
```
Each classification is **`inferred` + `needs_review`** with the matched signal cited; mark
**why** (the rule that fired). Then propagate along `FLOWS_TO` to produce **sensitive-data lineage**.

**Acceptance:** a `CARD-NO PIC X(16)` field is tagged `pci/needs_review` with its evidence; its
`FLOWS_TO` targets inherit a sensitivity trail; nothing is auto-`confirmed`.

## Gap 7 — Compiler/binder listing import *(optional)*
Add `import-listing <path>` to ingest compile/link listings that **resolve dynamic CALL targets and
COPY expansion**; persist as external evidence that turns `needs_review` dynamic edges into
`resolved` (origin=`listing`), never overwriting source facts. (Mirrors the existing
`import-runtime`/`import-catalog` pattern.)

---

## Honesty rules (apply to all of the above)
- A guessed codepage, an inferred identity field, a multi-artifact split, or a sensitivity tag is
  **`inferred`/`needs_review`** with its signal cited — never `confirmed`.
- Manifest-supplied facts are `confirmed` (operator-provided).
- Nothing is dropped: an undecodable or ambiguous member is kept and flagged in `scan_issue`.

## Test gate
| Test | Asserts |
|---|---|
| Manifest identity | members carry system/lpar/dataset_name/recfm/lrecl/library_role from the manifest |
| Manifest precedence | `library_role` classifies the member at high confidence over content signals |
| Codepage breadth | a cp1047/cp500 member decodes correctly; `detected_codepage` recorded |
| Codepage honesty | an ambiguous decode → `codepage_confident=0`, capped confidence, `scan_issue` |
| Fixed-format | sequence (1-6) + id-area (73-80) + col-7 continuation parse identically to clean code |
| RECFM split | an FB member with no newlines is split by lrecl |
| Multi-artifact | JCL+instream PROC yields both; DCLGEN yields copybook + DECLARES_TABLE |
| Nested programs | two PROGRAM-IDs in one member → two PROGRAM assets + CONTAINS_PROGRAM |
| Sensitive data | `CARD-NO PIC X(16)` → pci/needs_review with evidence; lineage propagates |
| No fabrication | absent manifest fields stay null; nothing forced to confirmed |

## Suggested sequence
1. **Gap 1 + Gap 2** (manifest/identity + codepage) — foundational; every later fact improves.
2. **Gap 3** (fixed-format precision) — parser correctness.
3. **Gap 4 + Gap 5** (multi-artifact + nested programs) — completeness.
4. **Gap 6** (sensitive-data) — compliance value.
5. **Gap 7** (listings) — optional dynamic-call resolution.
