# 3. The Knowledge Graph

**Business value.** Once MIP knows every program, job and data store and how they
connect, it can answer the questions that actually drive risk and cost: *If we change
this, what breaks? Which programs are the load-bearing ones? Which clusters of code
form natural applications we could modernize as a unit?* This turns a tangle of code
into a navigable map.

## What MIP does

MIP assembles all the discovered relationships into a directed graph of programs, jobs,
data tables, copybooks and screens. On that graph it runs proven algorithms:

- **Blast radius** — everything that would be impacted (or depended on) if an item changes.
- **PageRank criticality** — which programs are structurally most central.
- **Louvain community detection** — clusters of tightly-connected code that suggest
  natural application or domain boundaries.

## Real sample output

**Graph insights (`/api/graph`):**

```json
{
  "node_count": 17, "edge_count": 11,
  "roots": ["AUTHTRAN", "CRDPOST", "INTDRV", "PAYDRV", "STMTDRV"],
  "dead": ["DEADPROG"],
  "dynamic_edges": [ { "source": "INTDRV", "target": "INTRATE1" } ],
  "critical_by_pagerank": [
    { "program": "STMTFMT", "pagerank": 0.0969 },
    { "program": "PAYUPD",  "pagerank": 0.0969 },
    { "program": "CRDPOST", "pagerank": 0.0697 },
    { "program": "STMTDRV", "pagerank": 0.0697 },
    { "program": "AUTHVAL", "pagerank": 0.0697 }
  ],
  "community_count": 3,
  "modularity": 0.367
}
```

**Blast radius of the `CARD_MASTER` database table** (`graphx.blast_radius`):

```json
{
  "target": "CARD_MASTER", "target_kind": "db2_table",
  "impacted": [
    { "id": "BALUPD",   "kind": "program", "distance": 1, "confidence": 1.0 },
    { "id": "STMTDRV",  "kind": "program", "distance": 1, "confidence": 1.0 },
    { "id": "CRDPOST",  "kind": "program", "distance": 2, "confidence": 1.0 },
    { "id": "STMTGEN",  "kind": "job",     "distance": 2, "confidence": 1.0 },
    { "id": "DAILYCRD", "kind": "job",     "distance": 3, "confidence": 1.0 }
  ],
  "blast_radius_score": 5.0,
  "review": []
}
```

**Inferred communities (`/api/communities`):** 3 clusters, modularity 0.367 — e.g.
`Interest / Balance` = {BALUPD, INTCOMP, INTDRV, INTRATE1}; `Payment / Update` =
{PAYDRV, PAYUPD}. Each carries `"validation_status": "inferred", "confidence": 0.5`.

## What this means

- **Change impact is answered with evidence.** Touching the `CARD_MASTER` table affects
  3 programs and 2 batch jobs, traced by distance with full confidence (`review: []`
  means no uncertain links were in the path). This is the input to every "is this change
  safe?" conversation.
- **Criticality ranks where to be careful.** PageRank flags the structurally central
  programs (statement formatting and payment update here) — refined further by real
  runtime usage in [07-runtime-correlation.md](07-runtime-correlation.md).
- **Community clusters are a starting point, honestly labelled.** The 3 detected domains
  are explicitly **inferred** (confidence 0.5) with a modularity score of 0.367 — useful
  for proposing modernization boundaries, but flagged for human review, not asserted as
  truth.
