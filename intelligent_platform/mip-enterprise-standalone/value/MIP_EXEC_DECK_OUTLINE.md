# MIP — Executive / Investor Deck Outline (10 slides)

*A presentation arc that moves a room from "another AI tool" to "the backbone of modernization."
Each slide: the **key message** (say it out loud), the **content**, the **visual**, and a **speaker
note**. ~15–20 minutes.*

---

### Slide 1 — The trap
- **Key message:** *Mainframe modernization fails in the dark.*
- **Content:** Decades of COBOL/JCL/DB2/CICS; authors retired; docs wrong or gone; hidden
  dependencies. Teams scope, sequence, and rewrite *blind* → overruns, stalls, broken production.
- **Visual:** A tangled mainframe estate fading into fog; one program with question-mark arrows.
- **Say:** "The bottleneck was never writing new code. It's understanding the old code — and proving
  the new code behaves the same."

### Slide 2 — Why now: the AI paradox
- **Key message:** *AI made generating code cheap — which makes understanding and verification the
  new bottleneck.*
- **Content:** When anyone can generate Java, the only questions that matter are *is it correct?* and
  *did we cover everything?* Ungoverned AI on a mainframe = confident hallucination at scale.
- **Visual:** A scale — "Generate code" (cheap, light) vs "Prove it's correct" (heavy, the bottleneck).
- **Say:** "Everyone's racing to generate. Almost no one can prove. That gap is the opportunity."

### Slide 3 — What MIP is (the reframe)
- **Key message:** *MIP isn't a code generator. It's the system-of-record and verification backbone
  the whole program runs on.*
- **Content:** It *knows* what the estate is, and *proves* anything built from it is correct. A
  control plane / digital twin of the mainframe — not a code assistant.
- **Visual:** MIP as a backbone/spine; every other activity branching off it.
- **Say:** "AI tools generate. MIP knows, and verifies. Different category."

### Slide 4 — How it works (the value chain)
- **Key message:** *MIP covers the entire modernization lifecycle — See → Understand → Capture →
  Decide → Rebuild → Prove.*
- **Content:** the six-phase table (inventory/graphs → roots/journeys/capabilities → business rules +
  evidence → service candidates/roadmap → grounded Java → equivalence).
- **Visual:** Horizontal 6-stage pipeline, MIP underlining all of it.
- **Say:** "Breadth isn't feature creep — it's that MIP is the connective tissue across every stage."

### Slide 5 — The thing that makes it real: evidence
- **Key message:** *Every fact carries its source, a confidence score, and an honest status.*
- **Content:** `confirmed / inferred / needs_review`; inference is never shown as fact; unknowns are
  kept and flagged, not dropped.
- **Visual:** A fact card: claim + cited file:line + confidence 0.95 + status pill.
- **Say:** "This is the honesty contract. It's why you can trust the map enough to bet a program on it."

### Slide 6 — The demo moment (the proof)
- **Key message:** *We don't ask you to trust the output — we prove it.*
- **Content:** Live: click an edge → see the cited source line + confidence. Then a **dual-run**: same
  input to the mainframe and the new Java → **identical to the penny** (the rounding/COMP-3 test).
- **Visual:** Split screen: COBOL golden-master output `50.00` == Java output `50.00` → green ✓.
- **Say:** "This is the moment that separates us from every AI demo you've seen. Proof, not magic."

### Slide 7 — It covers what others skip
- **Key message:** *MIP captures the parts that actually break modernizations.*
- **Content:** Dynamic calls kept+flagged (blast radius), customer journeys reconstructed, business
  rules recovered, data lineage, and the **SME knowledge captured before they retire.**
- **Visual:** A "captured vs dropped" comparison; competitors' blind spots in red.
- **Say:** "The 5% of edge cases everyone ignores is the 95% of the risk."

### Slide 8 — The moat
- **Key message:** *Four things an AI tool structurally cannot claim.*
- **Content:** (1) cited, confidence-scored evidence; (2) a durable, compounding knowledge graph;
  (3) verifiable equivalence; (4) it's the integration point — codegen/LLMs/SIs are interchangeable
  workers on MIP's rails.
- **Visual:** Ecosystem diagram — MIP center; SIs, AI codegen, test tools, SME, roadmap plugging in.
- **Say:** "Models will change every six months. The backbone they plug into is the durable asset."

### Slide 9 — Value & ROI by stakeholder
- **Key message:** *Every decision-maker gets a reason that matters to them.*
- **Content:** CIO/Board → de-risk + capture retiring-SME knowledge + spend on evidence; EA → vendor-
  neutral control plane; SI → discovery in weeks, safe strangler sequence; Risk → full traceability +
  proven equivalence.
- **Visual:** 2×2 stakeholder grid, each with one outcome.
- **Say:** "The board cares about continuity and risk. Your SMEs are retiring — that knowledge is your
  biggest unhedged risk, and MIP captures it while they're still here."

### Slide 10 — The vision / the ask
- **Key message:** *MIP is the backbone of mainframe modernization — and the reason AI is finally
  safe to use on it.*
- **Content:** Recap: see → prove. The one-liner. The ask (pilot on one capability / journey, with a
  measurable equivalence-pass target).
- **Visual:** The backbone spine again, now lit end-to-end; a single clear call to action.
- **Say:** "Pick one customer journey. We'll discover it, rebuild it, and prove it equivalent. That's
  the whole thesis in one slice."

---

### Appendix slides (have ready, don't present unless asked)
- **A. Proof metrics** — extraction precision/recall, coverage %, journeys SME-confirmed, equivalence
  pass-rate. *(Numbers say platform.)*
- **B. The honesty model** — how confidence/validation work; why partial enrichment is flagged, not hidden.
- **C. The modernization loop** — discover → requirements (BR/FR, cited) → Java → dual-run → cut over.
- **D. Architecture** — SQLite/graph system of record, bounded slices, vendor-neutral integration.

### Delivery tips
- **Open on the problem, not the product.** Earn the reframe on Slide 3.
- **Slide 6 is the whole pitch** — rehearse the dual-run "penny" moment until it's flawless.
- **Never demo "AI explains COBOL"** — that's the commodity framing that gets you filed under *toy*.
- **Lead with metrics, close on one slice** — ask for a single-journey pilot with an equivalence target.
