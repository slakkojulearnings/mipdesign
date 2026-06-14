# Common Legacy-Modernization Prompts (Community Patterns)

> These are the prompt patterns that recur across legacy-modernization talks,
> tutorials, and practitioner write-ups (the "explain → extract → test → translate →
> verify" loop and friends). They are **community/common-practice patterns**, not
> verbatim quotes from any one source. Each is mapped to the MIP skill that owns it and
> annotated with the MIP-specific guardrail that makes it safe (evidence + confidence +
> human verification).
>
> Use these for the **Copilot / AI layer** (Level 5) — *after* the graph exists. They
> consume facts; they do not replace them (see [`../../00-foundation/PHILOSOPHY.md`](../../00-foundation/PHILOSOPHY.md)).

## How to use these well (the loop)

```
Explain  →  Extract business rules  →  Write characterization tests
        →  Translate  →  Verify against the tests  →  Review
```
Never translate before you have tests that pin the current behavior. The tests are the
contract; the LLM output is a proposal until they pass.

---

### 1. Explain a program in plain English
*Owner: [mainframe-code-analyst](../../03-skills/mainframe-code-analyst/SKILL.md) → documentation-writer*

```
You are a senior mainframe analyst. Explain what this COBOL program does in plain
business English. Cover: its purpose, inputs, outputs, the files/tables it touches,
the main processing steps, and any business rules you can see.
Do NOT guess. If something is ambiguous or depends on data not shown (copybooks,
called programs), say so explicitly and mark it as an assumption.
[PASTE PROGRAM + its copybooks]
```
**MIP guardrail:** feed it the *resolved* copybooks/called-program summaries from the
graph so it isn't guessing; label any inference `needs_review`.

---

### 2. Extract business rules
*Owner: [mainframe-code-analyst](../../03-skills/mainframe-code-analyst/SKILL.md)*

```
Extract the business rules implemented in this program as a numbered list.
For each rule give: (a) a plain-English statement, (b) the exact source lines it comes
from, (c) the variables/tables involved. Separate genuine business rules from
technical plumbing (file status checks, paragraph navigation, housekeeping).
If a rule's intent is unclear, mark it "UNCLEAR — needs SME review".
[PASTE PROGRAM]
```
**MIP guardrail:** every rule must cite source lines (evidence envelope). Rules with no
clear evidence are `needs_review`, never asserted.

---

### 3. Generate characterization (golden-master) tests *before* changing anything
*Owner: [test-engineer](../../03-skills/test-engineer/SKILL.md)*

```
Act as a QA lead. Based on this program's logic, generate characterization tests that
capture its CURRENT behavior (not ideal behavior): for representative and edge-case
inputs, state the expected outputs/decisions. Include boundary values and error paths.
Goal: a safety net so a rewrite can be proven behavior-equivalent.
[PASTE PROGRAM + record layouts]
```
**MIP guardrail:** these tests are the contract for §5; translation isn't "done" until
they pass against the new code.

---

### 4. Generate a sequence / flow diagram
*Owner: [graph-engineer](../../03-skills/graph-engineer/SKILL.md) → documentation-writer*

```
Produce a Mermaid sequence diagram of the runtime flow for [business process], using
this call chain and data access. Show programs as participants and DB2/file
reads/writes as messages. Mark any dynamic or unresolved call as "??".
[PASTE call chain + READS/WRITES from the graph]
```
**MIP guardrail:** drive this from the graph's actual edges, not the model's
imagination; dynamic calls shown as `??` (mirrors `needs_review`).

---

### 5. Translate COBOL → Java/Spring Boot (behavior-preserving)
*Owner: [mainframe-modernization-architect](../../03-skills/mainframe-modernization-architect/SKILL.md)*

```
Translate this COBOL program to idiomatic Java (Spring Boot). Requirements:
- Preserve exact business behavior — match the characterization tests in [§3].
- Map COBOL data types precisely (COMP-3 packed decimal → BigDecimal with correct
  scale; PIC X → String with length; signs; rounding).
- Replace GO TO / PERFORM-THRU control flow with structured methods; keep names
  traceable to the original paragraphs.
- Flag anything you cannot translate faithfully (e.g. EBCDIC collation, ALTER,
  arithmetic edge cases) instead of silently approximating.
Output the Java plus a mapping table: COBOL paragraph → Java method.
[PASTE PROGRAM + characterization tests]
```
**MIP guardrail:** translation is a *proposal* until §3 tests pass. Data-type fidelity
(packed decimal, rounding, signs) is where most automated conversions silently break —
demand it explicitly.

---

### 6. Strangler-fig migration plan
*Owner: [mainframe-modernization-architect](../../03-skills/mainframe-modernization-architect/SKILL.md) + [business-capability-analyst](../../03-skills/business-capability-analyst/SKILL.md)*

```
Given this capability map and dependency graph, propose a strangler-fig migration plan:
identify the lowest-risk capability to extract first (low blast radius, clear data
ownership, few inbound dependencies), the façade/interception point, the data strategy
(read-replica vs dual-write), and the sequence for subsequent slices.
Justify the ordering with the dependency/blast-radius evidence.
[PASTE capability map + critical-asset + blast-radius output]
```
**MIP guardrail:** ordering must cite blast-radius/criticality evidence
([`../../02-algorithms/CORE_ALGORITHMS.md`](../../02-algorithms/CORE_ALGORITHMS.md) §2), not intuition.

---

### 7. Impact / "what breaks if I change this?"
*Owner: [graph-engineer](../../03-skills/graph-engineer/SKILL.md)*

```
Given this field/table/program and the dependency graph, list everything affected by a
change to it: upstream callers, downstream consumers, jobs, reports, capabilities.
Rank by blast radius and flag anything reached only through a dynamic/unresolved edge
as lower-confidence "verify manually".
[PASTE target + graph neighborhood]
```
**MIP guardrail:** this is a graph query first; the LLM only narrates the computed
result (Principle: AI consumes knowledge).

---

### 8. The role-shift workflow (design → critique → implement → test → review)
*A meta-pattern, not a single prompt — owner: all skills*

Ask the same model to play different roles in sequence on one task:
1. **Architect:** "Design the approach. Don't write code."
2. **Skeptic:** "Review that design. Find scalability, correctness, and data-fidelity flaws."
3. **Engineer:** "Implement the agreed design."
4. **QA:** "Generate tests, including edge cases."
5. **Reviewer:** "Critique the implementation against the design and tests."

**MIP guardrail:** this is the workflow the original `plan.txt` already advocated;
keep it — it materially improves output quality and catches the data-fidelity errors
single-shot translation misses.

---

## Honest caveats (say these out loud to stakeholders)
- LLM COBOL→Java output is a **draft requiring verification**, not a migration. The
  characterization tests, not the model's confidence, decide correctness.
- The hard, error-prone parts are **data types** (packed decimal, signs, rounding,
  EBCDIC), **implicit control flow** (`GO TO`, `ALTER`, fall-through `PERFORM`), and
  **environmental behavior** (file status, abends, restart) — demand explicit handling
  and review for each.
- These prompts are most powerful **on top of MIP's graph**, where the model is handed
  resolved dependencies and rules instead of guessing from a single file.
