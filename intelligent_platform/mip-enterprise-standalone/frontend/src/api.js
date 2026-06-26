const parse = async (response) => {
  if (!response.ok) throw new Error(await response.text());
  return response.json();
};

const query = (params) => new URLSearchParams(params).toString();

export const api = {
  demo: () => fetch("/api/demo", { method: "POST" }).then(parse),
  analyze: ({ sourceRoot, demo = false } = {}) =>
    fetch(`/api/analyze?${query({ ...(sourceRoot ? { source_root: sourceRoot } : {}), demo })}`, {
      method: "POST",
    }).then(parse),
  stats: (runId = "") => fetch(`/api/stats${runId ? `?${query({ run_id: runId })}` : ""}`).then(parse),
  runStatus: (runId) => fetch(`/api/runs/${encodeURIComponent(runId)}/status`).then(parse),
  validate: (runId = "") => fetch(`/api/validate${runId ? `?${query({ run_id: runId })}` : ""}`).then(parse),
  enrich: ({ runId = "", topN = 100, timeout = 20, maxWorkers = 1, priority = "roots", changedOnly = false, force = false } = {}) =>
    fetch(
      `/api/enrich?${query({
        top_n: topN,
        timeout,
        max_workers: maxWorkers,
        priority,
        changed_only: changedOnly,
        force,
        ...(runId ? { run_id: runId } : {}),
      })}`,
      { method: "POST" }
    ).then(parse),
  enrichmentCoverage: (runId = "") =>
    fetch(`/api/enrichment/coverage${runId ? `?${query({ run_id: runId })}` : ""}`).then(parse),
  parseStatus: (asset, runId = "") =>
    fetch(`/api/parser/status/${encodeURIComponent(asset)}${runId ? `?${query({ run_id: runId })}` : ""}`).then(parse),
  performance: ({ runId = "", limit = 25 } = {}) =>
    fetch(`/api/performance?${query({ limit, ...(runId ? { run_id: runId } : {}) })}`).then(parse),
  corrections: ({ runId = "", entityKind = "", activeOnly = true } = {}) =>
    fetch(`/api/corrections?${query({ active_only: activeOnly, ...(runId ? { run_id: runId } : {}), ...(entityKind ? { entity_kind: entityKind } : {}) })}`).then(parse),
  scorecards: ({ runId = "", limit = 50 } = {}) =>
    fetch(`/api/scorecards?${query({ limit, ...(runId ? { run_id: runId } : {}) })}`).then(parse),
  roots: ({ limit = 100, runId = "" } = {}) =>
    fetch(`/api/roots?${query({ limit, ...(runId ? { run_id: runId } : {}) })}`).then(parse),
  clusters: ({ limit = 100, runId = "" } = {}) =>
    fetch(`/api/clusters?${query({ limit, ...(runId ? { run_id: runId } : {}) })}`).then(parse),
  domainContexts: ({ limit = 50, runId = "" } = {}) =>
    fetch(`/api/architecture/contexts?${query({ limit, ...(runId ? { run_id: runId } : {}) })}`).then(parse),
  serviceCandidates: ({ limit = 50, runId = "" } = {}) =>
    fetch(`/api/architecture/services?${query({ limit, ...(runId ? { run_id: runId } : {}) })}`).then(parse),
  modernizationRoadmap: ({ limit = 50, runId = "" } = {}) =>
    fetch(`/api/architecture/roadmap?${query({ limit, ...(runId ? { run_id: runId } : {}) })}`).then(parse),
  insights: ({ limit = 50, runId = "" } = {}) =>
    fetch(`/api/insights?${query({ limit, ...(runId ? { run_id: runId } : {}) })}`).then(parse),
  search: (q, { limit = 50, runId = "" } = {}) =>
    fetch(`/api/search?${query({ q, limit, ...(runId ? { run_id: runId } : {}) })}`).then(parse),
  nodes: ({ scope = "programs", q = "", limit = 200, offset = 0, runId = "" } = {}) =>
    fetch(`/api/nodes?${query({ scope, q, limit, offset, ...(runId ? { run_id: runId } : {}) })}`).then(parse),
  graphSlice: ({
    rootAssetId,
    depth = 1,
    limit = 500,
    relationshipTypes = "",
    confidenceMin = 0,
    mode = "neighborhood",
    direction = "both",
    runId = "",
  }) =>
    fetch(
      `/api/graph/slice?${query({
        root_asset_id: rootAssetId,
        depth,
        limit,
        mode,
        direction,
        relationship_types: relationshipTypes,
        confidence_min: confidenceMin,
        ...(runId ? { run_id: runId } : {}),
      })}`
    ).then(parse),
  node: (id, runId = "") =>
    fetch(`/api/nodes/${encodeURIComponent(id)}${runId ? `?${query({ run_id: runId })}` : ""}`).then(parse),
  edge: (id, runId = "") =>
    fetch(`/api/edges/${encodeURIComponent(id)}${runId ? `?${query({ run_id: runId })}` : ""}`).then(parse),
  heatmap: ({ left = "PROGRAM", right = "TABLE", relationship = "READS_TABLE", runId = "" } = {}) =>
    fetch(
      `/api/heatmap?${query({
        left_type: left,
        right_type: right,
        relationship_type: relationship,
        ...(runId ? { run_id: runId } : {}),
      })}`
    ).then(parse),
  callGraph: ({ asset, direction = "both", depth = 8, limit = 1500, runId = "" }) =>
    fetch(
      `/api/graphs/call?${query({
        asset,
        direction,
        depth,
        limit,
        ...(runId ? { run_id: runId } : {}),
      })}`
    ).then(parse),
  dependencyGraph: ({ asset, direction = "both", depth = 4, limit = 1500, runId = "" }) =>
    fetch(
      `/api/graphs/dependencies?${query({
        asset,
        direction,
        depth,
        limit,
        ...(runId ? { run_id: runId } : {}),
      })}`
    ).then(parse),
  requiredFiles: ({ asset, depth = 8, limit = 5000, runId = "" }) =>
    fetch(
      `/api/reverse/files?${query({
        asset,
        depth,
        limit,
        ...(runId ? { run_id: runId } : {}),
      })}`
    ).then(parse),
  astTree: ({ asset, runId = "" }) =>
    fetch(`/api/ast?${query({ asset, ...(runId ? { run_id: runId } : {}) })}`).then(parse),
  exportData: ({ format = "json", limit = 50000, runId = "" } = {}) =>
    fetch(`/api/export?${query({ format, limit, ...(runId ? { run_id: runId } : {}) })}`).then(parse),
};
