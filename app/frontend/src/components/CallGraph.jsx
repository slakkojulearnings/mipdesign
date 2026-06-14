import React, { useEffect, useMemo, useState } from "react";
import { api } from "../api.js";
import { useData } from "../hooks.js";
import ProfileCard from "./ProfileCard.jsx";
import Structure from "./Structure.jsx";

// Layered left→right layout: entry nodes (no incoming) on the left, BFS depth as columns.
function layout(nodes, edges) {
  const out = {}, indeg = {};
  nodes.forEach((n) => { out[n.id] = []; indeg[n.id] = 0; });
  edges.forEach((e) => { if (out[e.source]) out[e.source].push(e.target); if (e.target in indeg) indeg[e.target]++; });
  const depth = {}, q = [];
  nodes.forEach((n) => { if (indeg[n.id] === 0) { depth[n.id] = 0; q.push(n.id); } });
  if (!q.length && nodes.length) { depth[nodes[0].id] = 0; q.push(nodes[0].id); }
  const cap = nodes.length;
  while (q.length) {
    const u = q.shift();
    for (const v of out[u] || []) {
      const d = depth[u] + 1;
      if (d <= cap && (depth[v] === undefined || d > depth[v])) { depth[v] = d; q.push(v); }
    }
  }
  nodes.forEach((n) => { if (depth[n.id] === undefined) depth[n.id] = 0; });
  const cols = {};
  nodes.forEach((n) => { (cols[depth[n.id]] ||= []).push(n); });
  const colW = 190, rowH = 56, padX = 24, padY = 24;
  const pos = {};
  let maxRows = 0;
  Object.entries(cols).forEach(([d, list]) => {
    maxRows = Math.max(maxRows, list.length);
    list.forEach((n, i) => { pos[n.id] = { x: padX + d * colW, y: padY + i * rowH }; });
  });
  const width = padX * 2 + (Math.max(0, ...Object.keys(cols).map(Number)) + 1) * colW;
  const height = padY * 2 + maxRows * rowH;
  return { pos, width, height };
}

const colorOf = (n) =>
  n.type === "job" ? "var(--accent)" : n.is_dead ? "var(--red)" : n.is_root ? "var(--green)" : "var(--purple)";

function Insight({ l, v, cls }) {
  return <div className={`insight ${cls || ""}`}><div className="l">{l}</div><div className="v">{v}</div></div>;
}

export default function CallGraph({ onOpenProgram }) {
  const { data, err, loading } = useData(() => api.graph());
  const [sel, setSel] = useState(null);        // {type:'node'|'edge', ...}
  const [profile, setProfile] = useState(null);
  const lay = useMemo(() => (data ? layout(data.nodes, data.edges) : null), [data]);

  useEffect(() => {
    if (sel?.type === "node" && sel.node.type === "program") {
      setProfile(null);
      api.profile(sel.node.id).then(setProfile).catch(() => setProfile(null));
    } else { setProfile(null); }
  }, [sel]);

  if (loading) return <div className="loading">Loading…</div>;
  if (err) return <div className="error">{err}</div>;

  const { pos, width, height } = lay;
  const ins = data.insights || {};
  const NW = 130, NH = 28;

  return (
    <div>
      <h1 className="page-title">Call &amp; Execution Graph</h1>
      <p className="page-sub">Jobs → programs (EXECUTES) and program → program (CALLS). Click a node or an edge for complete details.</p>

      <div className="insights">
        <Insight l="Nodes / Edges" v={`${ins.node_count ?? "—"} / ${ins.edge_count ?? "—"}`} />
        <Insight l="Root drivers" cls="green" v={(ins.roots || []).length} />
        <Insight l="Dead code" cls="red" v={(ins.dead || []).length} />
        <Insight l="Dynamic / needs-review" cls="amber" v={(ins.dynamic_edges || []).length} />
        <Insight l="Most depended-on" v={ins.most_depended_on?.[0]
          ? <>{ins.most_depended_on[0].program} <small>×{ins.most_depended_on[0].called_by}</small></> : "—"} />
      </div>

      <div className="legend">
        <span><i className="dot" style={{ background: "var(--accent)" }} /> Job</span>
        <span><i className="dot" style={{ background: "var(--green)" }} /> Root</span>
        <span><i className="dot" style={{ background: "var(--purple)" }} /> Program</span>
        <span><i className="dot" style={{ background: "var(--red)" }} /> Dead</span>
        <span><svg width="26" height="10"><line x1="0" y1="5" x2="26" y2="5" stroke="var(--amber)" strokeWidth="2" strokeDasharray="4 3" /></svg> dynamic</span>
      </div>

      <div className="graph-layout">
        <div className="graph-wrap">
          <svg width={Math.max(width, 400)} height={Math.max(height, 200)}>
            <defs>
              <marker id="arrow" markerWidth="8" markerHeight="8" refX="7" refY="3" orient="auto">
                <path d="M0,0 L7,3 L0,6 Z" fill="#5b6b7d" /></marker>
              <marker id="arrow-rev" markerWidth="8" markerHeight="8" refX="7" refY="3" orient="auto">
                <path d="M0,0 L7,3 L0,6 Z" fill="var(--amber)" /></marker>
            </defs>

            {data.edges.map((e, i) => {
              const a = pos[e.source], b = pos[e.target];
              if (!a || !b) return null;
              const review = e.validation_status !== "confirmed";
              const on = sel?.type === "edge" && sel.i === i;
              return (
                <line key={i} x1={a.x + NW} y1={a.y + NH / 2} x2={b.x} y2={b.y + NH / 2}
                  stroke={on ? "var(--text)" : review ? "var(--amber)" : "#5b6b7d"}
                  strokeWidth={on ? 3 : 1.6} strokeDasharray={review ? "4 3" : "0"}
                  markerEnd={review ? "url(#arrow-rev)" : "url(#arrow)"}
                  style={{ cursor: "pointer" }} onClick={() => setSel({ type: "edge", edge: e, i })} />
              );
            })}

            {data.nodes.map((n) => {
              const p = pos[n.id]; if (!p) return null;
              const on = sel?.type === "node" && sel.node.id === n.id;
              return (
                <g key={n.id} transform={`translate(${p.x},${p.y})`} style={{ cursor: "pointer" }}
                   onClick={() => setSel({ type: "node", node: n })}>
                  <rect width={NW} height={NH} rx="7" fill={on ? "var(--panel)" : "var(--panel-2)"}
                        stroke={colorOf(n)} strokeWidth={on ? 3 : 2} />
                  <circle cx="11" cy={NH / 2} r="4" fill={colorOf(n)} />
                  <text x="22" y={NH / 2 + 4} fill="var(--text)" fontSize="11.5"
                        fontFamily="ui-monospace, Consolas, monospace">{n.id}</text>
                </g>
              );
            })}
          </svg>
        </div>

        <div className="detail-panel">
          {!sel && <div className="hint">Select a <strong>node</strong> for its full profile &amp; structure, or an <strong>edge</strong> for its evidence.</div>}

          {sel?.type === "edge" && (
            <div className="edge-card">
              <h3>Relationship</h3>
              <p className="rel" style={{ fontSize: 14 }}>
                {sel.edge.source} <span className="t">{sel.edge.rel_type}</span> {sel.edge.target}
              </p>
              <div className="kv">
                <div><span>Type</span>{sel.edge.rel_type}</div>
                <div><span>Confidence</span>{sel.edge.confidence}</div>
                <div><span>Status</span>
                  {sel.edge.validation_status === "confirmed"
                    ? <span className="badge ok">confirmed</span>
                    : <span className="badge review">{sel.edge.validation_status}</span>}</div>
              </div>
              {sel.edge.validation_status !== "confirmed" &&
                <p className="muted" style={{ fontSize: 12 }}>Dynamic/unresolved target — kept and flagged, not asserted.</p>}
            </div>
          )}

          {sel?.type === "node" && (
            <div>
              <h3>{sel.node.id}</h3>
              <div style={{ marginBottom: 10 }}>
                <span className="tag">{sel.node.type}</span>{" "}
                {sel.node.is_root && <span className="badge root">root</span>}{" "}
                {sel.node.is_dead && <span className="badge dead">dead</span>}
              </div>
              {sel.node.type === "program" ? (
                profile ? (
                  <>
                    <ProfileCard profile={profile} onOpenProgram={onOpenProgram} />
                    <div className="cap-sec">
                      <div className="l">Structure / AST</div>
                      <Structure structure={profile.structure} />
                    </div>
                    <button className="btn secondary" style={{ marginTop: 12 }}
                            onClick={() => onOpenProgram(sel.node.id)}>Open full page →</button>
                  </>
                ) : <div className="loading">Loading profile…</div>
              ) : (
                <p className="hint">Job entry point. It executes the program it points to (an EXECUTES edge).</p>
              )}
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
