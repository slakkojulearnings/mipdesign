# Core Algorithms

> This file fills the biggest gap in the original design: the Reasoning layer was
> described by its *outputs*, not its *algorithms*. Here each core capability is given
> a concrete, implementable specification — inputs, method (pseudocode), confidence
> handling, and complexity.

All algorithms operate over the knowledge graph `G` — a directed multigraph whose
edges are the `relationship` rows ([`../01-metadata-model/schema.sql`](../01-metadata-model/schema.sql)).
Every edge `e` has `e.confidence ∈ [0,1]` and `e.validation_status`.

A shared principle: **confidence propagates**. A conclusion reached over a path is
never more confident than the weakest edge on that path.

---

## 0. Multi-hop confidence aggregation (used by all traversals)

```
def path_confidence(path_edges):
    # weakest-link, not product: a chain is as trustworthy as its least-trusted hop.
    # (product underweights long but solid chains; min is honest and stable.)
    return min(e.confidence for e in path_edges) if path_edges else 1.0

def node_confidence(paths_to_node):
    # a node reachable by several independent paths gains confidence (noisy-OR).
    # 1 - Π(1 - path_confidence(p))
    acc = 1.0
    for p in paths_to_node:
        acc *= (1.0 - path_confidence(p))
    return 1.0 - acc
```

Any result that depends on a `needs_review` edge inherits `needs_review` and is
surfaced as such — Principle 1.

---

## 1. Root / Driver Program Detection  *(Stage-1 capability)*

**Goal:** find true execution entry points — the programs that *start* business
processing.

**Inputs:** `EXECUTES` edges (Job→Program), `CALLS` edges (Program→Program), and
(optionally) CICS/MQ/scheduler entry edges.

**Method:** a root is a program that is *executed or triggered externally* but is
*not called by another program* (in-degree of `CALLS` ≈ 0), **or** is named directly
by a Job/transaction/scheduler.

```
def detect_roots(G):
    roots = []
    for p in programs(G):
        called_in = in_degree(G, p, rel_type="CALLS")
        executed  = in_degree(G, p, rel_type=("EXECUTES","STARTS","TRIGGERS"))
        if executed > 0 and called_in == 0:
            roots.append((p, kind="batch/online driver", confidence=high))
        elif executed > 0 and called_in > 0:
            roots.append((p, kind="entry+also-called", confidence=medium))  # flag
    # programs with no incoming edges at all = candidate roots OR dead code (see §4)
    for p in programs(G):
        if in_degree_total(G, p) == 0:
            roots.append((p, kind="unreferenced root candidate", confidence=low))  # needs_review
    rank_by(roots, key=downstream_reach)   # see §2
    return roots
```

**Confidence:** Job-named roots are `confirmed`; "unreferenced" roots are
`needs_review` (could be dead code, or the caller's source is simply missing).
**Complexity:** O(V + E).

---

## 2. Impact Analysis / Blast Radius  *(highest-value capability)*

**Goal:** given a target node (program, table, copybook, field), find everything that
could be affected by changing it, with a confidence-weighted blast radius.

**Method:** reverse reachability (who depends on the target) + forward reachability
(what the target depends on), over the relevant edge types.

```
def blast_radius(G, target, max_depth=None):
    upstream = reverse_bfs(G, target, edges=("CALLS","USES","READS","WRITES","EXECUTES"))
    downstream = forward_bfs(G, target, edges=("CALLS","READS","WRITES"))
    affected = {}
    for node, paths in upstream.items():       # paths = all simple paths target←…←node
        affected[node] = {
            "direction": "upstream",
            "min_distance": min(len(p) for p in paths),
            "confidence": node_confidence(paths),     # §0
        }
    # ... same for downstream ...
    radius_score = weighted_count(affected, by="confidence")
    return ImpactReport(target, affected, radius_score,
                        review=[n for n,a in affected.items() if any_needs_review(a)])
```

**Outputs:** affected programs/jobs/tables/capabilities, blast-radius score,
confidence per affected node, and the subset needing review.
**Complexity:** O(V + E) per query with BFS; cache reverse-reachability for hot nodes.
**Resilience:** unresolved/dynamic edges are *included* with `needs_review` so impact
is never silently under-reported (the dangerous failure mode).

---

## 3. Data Lineage (constrained-edge path discovery)

**Goal:** trace how data flows producer → … → consumer at dataset/table/field level.

**Method:** path search restricted to *data* edge types, preserving direction.

```
def lineage(G, source_node, target_node=None, edges=("READS","WRITES","PRODUCES","CONSUMES","TRANSFORMS","DERIVES_FROM")):
    # forward flow from a source; or full source→target paths if target given
    subgraph = edge_filtered_view(G, edges)
    if target_node:
        paths = all_simple_paths(subgraph, source_node, target_node)
    else:
        paths = dfs_tree(subgraph, source_node)
    for p in paths:
        annotate(p, confidence=path_confidence(p))   # §0
    return LineageModel(paths, field_level=resolve_fields(paths))
```

**Cycle handling:** detect via DFS back-edges; report cycles explicitly (common in
read-modify-write batch flows) rather than looping. **Complexity:** path enumeration is
worst-case exponential — bound by `max_depth` and by pruning at low-confidence edges;
for "does data reach X?" use reachability (O(V+E)) instead of path enumeration.

---

## 4. Dead-Code / Orphan Detection

**Goal:** find unreachable programs, unused copybooks, orphan tables.

**Method:** reachability from the confirmed root set (§1).

```
def dead_code(G, roots_confirmed):
    reachable = multi_source_bfs(G, roots_confirmed, edges=("EXECUTES","CALLS"))
    dead = [p for p in programs(G) if p not in reachable]
    for p in dead:
        # absence of runtime evidence ⇒ lower confidence: may be rarely-but-legitimately used
        conf = 0.5 if no_runtime_evidence(p) else 0.85
        emit(p, candidate="retirement", confidence=conf, validation_status="needs_review")
    return dead
```

**Critical rule:** never recommend retirement at high confidence without runtime
evidence — a program unreachable in static analysis may still be invoked dynamically or
by an external scheduler. Always `needs_review`.
**Complexity:** O(V + E).

---

## 5. Business-Capability & Application-Boundary Detection (clustering)

**Goal:** recover logical applications/domains/capabilities from the graph.

**Method:** community detection on the dependency graph, blended with semantic signals.

```
def detect_capabilities(G):
    # 1. structural communities
    communities = louvain(undirected_weighted(G))          # or Leiden for stability
    # 2. semantic cohesion: naming patterns, shared tables/transactions, embeddings
    for c in communities:
        c.label, c.label_conf = name_from_signals(c)        # semantic ⇒ inferred
        c.cohesion = modularity_contribution(c)
    # 3. confidence: structural support × semantic agreement
    for c in communities:
        c.confidence = combine(c.cohesion, c.label_conf)
        if c.confidence < THRESHOLD:
            c.validation_status = "needs_review"            # flag low-confidence groupings
    return communities
```

**Outputs:** capability catalog, capability→application→program mapping, dependency
graph between capabilities, confidence per assignment.
**Resilience:** clustering is inherently inferential — *every* capability assignment is
`inferred` at best, and low-cohesion clusters are flagged for human review. Never
present a discovered capability as ground truth.
**Algorithms:** Louvain/Leiden (community), PageRank (criticality), SCC/Tarjan (cycles &
tight coupling), betweenness centrality (integration hubs).

---

## Where these run in v0.1 vs later

| Algorithm | v0.1 (reference impl) | Later |
|-----------|----------------------|-------|
| Root detection (§1) | ✅ over SQLite edges | + CICS/MQ/scheduler entries |
| Blast radius (§2) | ✅ basic reverse/forward BFS | + capability/field level |
| Lineage (§3) | partial (table level) | + field-level via data-flow AST |
| Dead code (§4) | ✅ | + runtime evidence |
| Capability clustering (§5) | spec only | needs NetworkX + embeddings |
