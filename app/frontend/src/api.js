// Thin API client. Same-origin "/api" (FastAPI serves the built app; Vite proxies in dev).
const j = async (res) => {
  if (!res.ok) throw new Error((await res.text()) || res.statusText);
  return res.json();
};

export const api = {
  health: () => fetch("/api/health").then(j),
  scan: (path) => fetch(`/api/scan${path ? `?path=${encodeURIComponent(path)}` : ""}`, { method: "POST" }).then(j),
  summary: () => fetch("/api/summary").then(j),
  programs: () => fetch("/api/programs").then(j),
  program: (pid) => fetch(`/api/program/${encodeURIComponent(pid)}`).then(j),
  profile: (pid) => fetch(`/api/program/${encodeURIComponent(pid)}/profile`).then(j),
  impact: (pid) => fetch(`/api/program/${encodeURIComponent(pid)}/impact`).then(j),
  jobs: () => fetch("/api/jobs").then(j),
  roots: () => fetch("/api/roots").then(j),
  deadcode: () => fetch("/api/deadcode").then(j),
  graph: () => fetch("/api/graph").then(j),
  capabilities: () => fetch("/api/capabilities").then(j),
  insights: () => fetch("/api/insights").then(j),
  query: (question) =>
    fetch("/api/query", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ question }),
    }).then(j),
  source: (path) => fetch(`/api/source?path=${encodeURIComponent(path)}`).then(j),
  log: (limit = 100) => fetch(`/api/log?limit=${limit}`).then(j),
  logRaw: () => fetch("/api/log/raw").then(j),
};
