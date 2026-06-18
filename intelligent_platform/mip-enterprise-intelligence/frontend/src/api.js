const parse = async (response) => {
  if (!response.ok) throw new Error(await response.text());
  return response.json();
};

const query = (params) => new URLSearchParams(params).toString();

export const api = {
  demo: () => fetch("/api/demo", { method: "POST" }).then(parse),
  stats: (runId = "") => fetch(`/api/stats${runId ? `?${query({ run_id: runId })}` : ""}`).then(parse),
  roots: ({ limit = 100, runId = "" } = {}) =>
    fetch(`/api/roots?${query({ limit, ...(runId ? { run_id: runId } : {}) })}`).then(parse),
  clusters: ({ limit = 100, runId = "" } = {}) =>
    fetch(`/api/clusters?${query({ limit, ...(runId ? { run_id: runId } : {}) })}`).then(parse),
  search: (q, { limit = 50, runId = "" } = {}) =>
    fetch(`/api/search?${query({ q, limit, ...(runId ? { run_id: runId } : {}) })}`).then(parse),
  graphSlice: ({
    rootAssetId,
    depth = 1,
    limit = 500,
    relationshipTypes = "",
    confidenceMin = 0,
    mode = "neighborhood",
    runId = "",
  }) =>
    fetch(
      `/api/graph/slice?${query({
        root_asset_id: rootAssetId,
        depth,
        limit,
        mode,
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
};
