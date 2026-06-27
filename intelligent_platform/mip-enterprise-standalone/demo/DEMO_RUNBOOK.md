# MIP — Live Demo Runbook
### A 20-minute "watch it understand a mainframe, then rebuild it" demo for the team

*Every step: the command to run, what appears, and the one line to say. Real commands, in order.*

---

## Before the session (do this 30 min early — don't make people watch a scan)
A full baseline scan of a real estate takes minutes (it builds a large graph), so **pre-scan once and
demo against the saved database.** Keep `init-demo` as an instant fallback.

```powershell
# install (once)
python -m mip_intel.cli --version 2>$null; python -m pip install -e ".[api,dev]"

# OPTION A (recommended): pre-scan a real sample estate into a DB you'll demo from
python -m mip_intel.cli --db data\demo-bank.db analyze "F:\path\to\sample_source"
python -m mip_intel.cli --db data\demo-bank.db validate      # confirm it's healthy

# OPTION B (instant fallback): a seeded demo graph, no scan needed
python -m mip_intel.cli --db data\demo.db init-demo

# start the UI for the visual part
python -m mip_intel.cli --db data\demo-bank.db serve --host 127.0.0.1 --port 8000   # terminal 1
cd frontend; npm install; npm run dev                                                # terminal 2  -> http://127.0.0.1:5174
```
Pick **one program** to be your hero (e.g. `CRDPOST` in the demo DB, or a real driver in your scan).
Have its raw source file open in a second window.

---

## Act 1 — The wall (1 min)
**Show:** the raw COBOL/assembler file in your editor. Scroll it fast.
**Say:** *"This is what we're asked to modernize. Thousands of lines like this, the authors retired, no
docs. Nobody in this room can tell me what it touches or what breaks if we change it. Watch."*

## Act 2 — The map (2 min)
**Run:**
```powershell
python -m mip_intel.cli --db data\demo-bank.db stats
```
**Show:** the counts — programs, jobs, tables, copybooks, relationships.
**Say:** *"From that folder of unreadable code, MIP built a connected map: every program, what it calls,
what data it touches — in one pass, with no SME."*

## Act 3 — Understand one program (5 min) — the core of the demo
**Run:**
```powershell
python -m mip_intel.cli --db data\demo-bank.db search CRDPOST
python -m mip_intel.cli --db data\demo-bank.db call-graph CRDPOST --direction both --depth 4
python -m mip_intel.cli --db data\demo-bank.db required-files CRDPOST
```
**Then switch to the UI:** search `CRDPOST` → click it → open the **call-graph** view → click an edge.
**Show:** who calls it / what it calls; the required-files set; the detail drawer with **evidence
(file:line) + confidence + status** on a relationship.
**Say:** *"In thirty seconds I know its blast radius, the exact files I'd need to rebuild it, and — click
— the proof behind every link. An analyst with zero COBOL can do this."*

## Act 4 — The honesty (2 min) — this is the differentiator
**Run:**
```powershell
python -m mip_intel.cli --db data\demo-bank.db validate
```
**Show:** the checks (every asset/relationship has evidence; confidence in range; statuses valid). Then
in the UI point at a `needs_review` / dynamic-call edge (orange).
**Say:** *"This is what separates MIP from an AI toy. It never guesses in disguise — proven facts are
'confirmed', reasoning is 'inferred', and the things it couldn't resolve are flagged in orange, not
hidden. That's why you can bet a program on this map."*

## Act 5 — From map to plan (4 min)
**Run:**
```powershell
python -m mip_intel.cli --db data\demo-bank.db roots --limit 5
python -m mip_intel.cli --db data\demo-bank.db clusters --limit 5
python -m mip_intel.cli --db data\demo-bank.db service-candidates --limit 3
python -m mip_intel.cli --db data\demo-bank.db roadmap --limit 3
```
**Show:** the entry-point programs ranked by risk; the capability clusters; a proposed Java service +
its data contracts; a risk-ordered modernization roadmap.
**Say:** *"It doesn't just describe the system — it proposes what to carve out into a service, and in
what order, lowest-risk first. Every proposal cites the code it came from."*

## Act 6 — The handoff to rebuild (3 min) — live today + the roadmap
**Run (live today):**
```powershell
python -m mip_intel.cli --db data\demo-bank.db export-bundle CRDPOST --output data\bundles\CRDPOST
```
**Show:** the bundle — source, dependencies, evidence, minimal context — *"everything a rebuild team or
an AI needs to recreate this one unit, with citations."*
**Say (the roadmap, narrate honestly):** *"From this bundle, the next phase generates the confirmed
business rule — 'overdue → 5% late fee' — then the Java or Python, grounded in that rule, and proves it
by running the same inputs through the mainframe and the new code. They match to the penny, or it
doesn't ship. That requirements-to-proof loop is specified and is our next build."*

---

## The one "aha" to land
> Click a relationship → the drawer shows the **source line + confidence**. Then say:
> *"Most AI tools give you a confident answer. MIP gives you the answer **and the proof** — and for the
> rebuild, it proves the new code behaves exactly like the old one. That's the difference between a demo
> and something you can run a bank on."*

---

## Honest caveats (have these ready — they build trust)
- **Scan time:** a baseline scan builds a large graph; pre-scan before the session. (Per-program deep
  ANTLR parsing is a slower *background* tier, run on a prioritized subset — not on the critical path.)
- **Deep enrichment** captures the richest facts but is slow per file; today's live capture is the fast
  baseline (calls, copybooks, tables, rules, lineage), which is enough to understand and plan.
- **Rebuild + proof** (Java/Python generation, dual-run equivalence) is specified and underway — present
  it as the funded roadmap, not as shipped.

## The 2-minute exec version (if someone senior drops in)
1. `stats` — *"unreadable folder → connected map, no SME."*
2. UI: click one edge → *"every fact is cited; unknowns are flagged, not hidden."*
3. `service-candidates` — *"and here's what to modernize first, with the evidence."*
4. One sentence: *"It makes the old system understandable today, and it's built to rebuild it in
   Java/Python and prove the result is correct — the only safe way to retire a 40-year-old core."*
