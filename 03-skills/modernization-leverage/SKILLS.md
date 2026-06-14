# Leverage-able Skills & Roles (Common Practice)

> Beyond MIP's 12 core skills, these are reusable *roles/skills* that legacy-
> modernization teams (and AI-assisted workflows) commonly lean on. They are framed as
> personas you can invoke — pair each with the [common modernization prompts](../../04-prompts/community/COMMON_MODERNIZATION_PROMPTS.md)
> and the MIP skill that owns the underlying capability. All inherit
> [MIP Engineering Principles](../MIP_ENGINEERING_PRINCIPLES.md) (evidence + confidence + resilience).

## Engineering-discipline skill

### `karpathy-guidelines` — disciplined AI-assisted engineering
*Adapted from the community "Andrej Karpathy guidelines" skill
(github.com/multica-ai/andrej-karpathy-skills). Also encoded for tooling in
[`../../CLAUDE.md`](../../CLAUDE.md).*

Four rules every implementation task in MIP should follow:
1. **Think before coding** — don't assume, don't hide confusion, surface tradeoffs;
   state assumptions and ask when uncertain.
2. **Simplicity first** — minimum code that solves the stated problem; nothing
   speculative; "if 200 lines could be 50, rewrite it."
3. **Surgical changes** — touch only what the request requires; match existing style;
   don't refactor working code or do drive-by cleanups; remove only what your change
   orphaned.
4. **Goal-driven execution** — convert tasks into verifiable success criteria; write
   tests that reproduce a bug before fixing; loop until verified.

> Why it belongs in MIP: the original repo's biggest risk was *design sprawl with no
> running code*. These rules are the antidote — they keep the build lean, verified, and
> honest, which is the same value MIP sells to its users.

## Modernization roles (personas to invoke)

| Skill / role | Use it for | Pairs with prompt | MIP owner skill |
|---|---|---|---|
| **Legacy Code Explainer** | turn COBOL into plain-English intent for new joiners | §1 Explain | mainframe-code-analyst → documentation-writer |
| **Business-Rule Archaeologist** | extract & catalog embedded business rules with evidence | §2 Extract rules | mainframe-code-analyst |
| **Characterization-Test Author** | pin current behavior before any rewrite (golden master) | §3 Char. tests | test-engineer |
| **Data-Type Fidelity Specialist** | COMP-3/packed-decimal, signs, rounding, EBCDIC correctness in translation | §5 Translate | mainframe-modernization-architect |
| **Strangler-Fig Planner** | sequence incremental extraction by blast radius & data ownership | §6 Strangler | modernization-architect + business-capability-analyst |
| **Impact Analyst** | "what breaks if I change X" over the graph | §7 Impact | graph-engineer |
| **Diagram Generator** | sequence/flow diagrams from real graph edges | §4 Diagram | graph-engineer → documentation-writer |

## How to leverage them

1. Build the graph first (Levels 1–4). These roles operate on graph facts, not raw guesses.
2. Invoke a role with its paired prompt, handing it the **resolved** context from MIP
   (copybooks, called-program summaries, dependency neighborhood).
3. Treat all output as a **proposal** carrying confidence; verify with characterization
   tests and human review before it becomes a decision.
4. Apply `karpathy-guidelines` to any code the roles produce: simplest thing that
   passes the tests, surgical, verified.
