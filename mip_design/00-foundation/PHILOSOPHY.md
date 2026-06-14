# MIP Philosophy

> The non-negotiable beliefs that shape every other decision in this design.

## The one idea everything rests on

**Understand the system before you transform it.**

Most mainframe-modernization efforts begin with *"convert COBOL to Java."* That is
the last step disguised as the first. You cannot safely transform what you do not
understand, and in a 10,000-program estate, no human understands the whole thing.

MIP therefore builds **understanding as a product** first, and treats transformation
as something that *consumes* that understanding later.

## The pipeline (never skip a layer)

```
Source Code
   ↓  scan + classify (no parsing yet)
Inventory
   ↓  deterministic parsers
Metadata          ← canonical, evidence-backed facts
   ↓  relationship extraction
Knowledge Graph   ← how the enterprise actually operates
   ↓  graph algorithms + reasoning
Reasoning         ← impact, root cause, lineage, capabilities
   ↓  LLM on top of facts
Copilot / Q&A
   ↓  decisions grounded in evidence
Modernization
```

Each layer is only as trustworthy as the one beneath it. A confident answer built on
a wrong graph is worse than no answer. So we build **bottom-up**, and we let nothing
in an upper layer that isn't traceable to the layer below.

## The maturity model (and the mistake to avoid)

| Level | Capability | Question it answers |
|------:|------------|---------------------|
| 1 | Inventory | What exists? |
| 2 | Metadata | What is each thing? |
| 3 | Knowledge Graph | How is it connected? |
| 4 | Reasoning | What happens if I change this? |
| 5 | Copilot | Can it explain itself in English? |
| 6 | Modernization | What do we change, in what order? |

**The classic failure is jumping straight to Level 5** (build the chatbot first).
The chatbot is only as good as Levels 1–4. We climb in order.

## The first thread to pull: the root / driver program

In a batch-driven mainframe, execution doesn't start in COBOL — it starts in **JCL**.
So the cheapest, highest-leverage first move is to find **entry points** (`EXEC PGM=`
in JCL, CICS transaction definitions) rather than opening random COBOL programs. From
a root, the call graph unrolls downward and the system becomes navigable.

> This is why the reference implementation's v0.1 is exactly: scan → COBOL catalog →
> **JCL `EXEC PGM=` catalog** → "which jobs execute program X?". That single answer is
> the first real step from *source code* to *enterprise knowledge*.

## AI consumes knowledge — it does not replace it

LLMs are used for **explanation, naming, and recommendation on top of facts**, never
as the source of facts. Parsing is deterministic. Relationships are evidence-based.
The graph is the source of truth. When the LLM reasons, it reasons over the graph and
must cite it. This is what keeps the platform from hallucinating its way into a
dangerous modernization decision.

## Honesty over impressiveness

Two rules that protect trust:
1. **Make uncertainty visible.** Every fact carries a confidence and a validation
   status. We never present an inference as a confirmed fact.
2. **Degrade gracefully.** Incomplete repositories, dynamic calls, undocumented
   interfaces are the *normal* case, not the exception. The platform produces the best
   evidence-based answer it can, flags the gap, and lowers confidence — it does not
   fail or fabricate.

See [ENGINEERING_PRINCIPLES.md](ENGINEERING_PRINCIPLES.md) for how these beliefs become
enforceable rules.
