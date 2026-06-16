import React, { useEffect, useMemo, useRef, useState } from "react";
import { useNavigate } from "react-router-dom";
import { api } from "../api.js";
import { useData } from "../hooks.js";
import ProfileCard from "./ProfileCard.jsx";
import Structure from "./Structure.jsx";
import "./CallGraph.css";

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

// Non-color status cue: a small glyph so root/dead/dynamic are distinguishable without color.
const glyphOf = (n) =>
  n.type === "job" ? "▸" : n.is_dynamic ? "?" : n.is_dead ? "✕" : n.is_root ? "R" : "";

const ZMIN = 0.25, ZMAX = 4;

function Insight({ l, v, cls }) {
  return <div className={`insight ${cls || ""}`}><div className="l">{l}</div><div className="v">{v}</div></div>;
}

export default function CallGraph({ onOpenProgram }) {
  const navigate = useNavigate();
  const { data, err, loading } = useData(() => api.graph());
  const [sel, setSel] = useState(null);        // {type:'node'|'edge', ...}
  const [profile, setProfile] = useState(null);
  const lay = useMemo(() => (data ? layout(data.nodes, data.edges) : null), [data]);

  // --- controls state ---
  const [view, setView] = useState(null);      // viewBox {x,y,w,h}
  const [find, setFind] = useState("");
  const [hitId, setHitId] = useState(null);    // search-focused node id
  const [findMiss, setFindMiss] = useState(false);
  const [threshold, setThreshold] = useState(0);
  const [enabledTypes, setEnabledTypes] = useState(null); // {CALLS:true,...} or null=all

  const svgRef = useRef(null);
  const drag = useRef(null);   // {x,y, vx,vy} active pan
  const moved = useRef(false); // suppress click after a pan-drag

  // rel types present in the data
  const relTypes = useMemo(() => {
    const s = new Set();
    (data?.edges || []).forEach((e) => e.rel_type && s.add(e.rel_type));
    return Array.from(s).sort();
  }, [data]);

  // nodes whose only inbound evidence is non-confirmed → "dynamic / unresolved" cue
  const dynamicSet = useMemo(() => {
    const confirmed = new Set(), seen = new Set();
    (data?.edges || []).forEach((e) => {
      seen.add(e.target);
      if (e.validation_status === "confirmed") confirmed.add(e.target);
    });
    const s = new Set();
    seen.forEach((t) => { if (!confirmed.has(t)) s.add(t); });
    return s;
  }, [data]);

  // initialize viewBox once the layout is known
  useEffect(() => {
    if (lay) setView({ x: 0, y: 0, w: Math.max(lay.width, 400), h: Math.max(lay.height, 200) });
  }, [lay]);

  useEffect(() => {
    if (sel?.type === "node" && sel.node.type === "program") {
      setProfile(null);
      api.profile(sel.node.id).then(setProfile).catch(() => setProfile(null));
    } else { setProfile(null); }
  }, [sel]);

  if (loading) return <div className="loading">Loading…</div>;
  if (err) return <div className="error">{err}</div>;

  const { pos, width, height } = lay;
  const baseW = Math.max(width, 400), baseH = Math.max(height, 200);
  const vb = view || { x: 0, y: 0, w: baseW, h: baseH };
  const ins = data.insights || {};
  const NW = 130, NH = 28;

  const typeOn = (t) => !enabledTypes || enabledTypes[t];

  // visible edges = type enabled AND confidence at/above threshold
  let hiddenByConf = 0;
  const visibleEdges = data.edges
    .map((e, i) => ({ e, i }))
    .filter(({ e }) => {
      if (!typeOn(e.rel_type)) return false;
      const c = e.confidence == null ? 1 : e.confidence;
      if (c < threshold) { hiddenByConf++; return false; }
      return true;
    });
  // show per-edge labels only when the graph is small enough to stay legible
  const showEdgeLabels = visibleEdges.length <= 160;

  // --- zoom / pan helpers ---
  const clientToSvg = (clientX, clientY) => {
    const r = svgRef.current.getBoundingClientRect();
    return {
      x: vb.x + ((clientX - r.left) / r.width) * vb.w,
      y: vb.y + ((clientY - r.top) / r.height) * vb.h,
    };
  };
  const zoomBy = (factor, cx, cy) => {
    setView((v) => {
      const cur = v || { x: 0, y: 0, w: baseW, h: baseH };
      const nw = Math.min(baseW / ZMIN, Math.max(baseW / ZMAX, cur.w * factor));
      const nh = nw * (baseH / baseW);
      // keep the point under the cursor stable
      const ax = cx == null ? cur.x + cur.w / 2 : cx;
      const ay = cy == null ? cur.y + cur.h / 2 : cy;
      const rx = (ax - cur.x) / cur.w, ry = (ay - cur.y) / cur.h;
      return { x: ax - rx * nw, y: ay - ry * nh, w: nw, h: nh };
    });
  };
  const onWheel = (ev) => {
    ev.preventDefault();
    const p = clientToSvg(ev.clientX, ev.clientY);
    zoomBy(ev.deltaY > 0 ? 1.12 : 1 / 1.12, p.x, p.y);
  };
  const onPointerDown = (ev) => {
    if (ev.button !== 0) return;
    moved.current = false;
    // Do NOT capture the pointer here. Capturing on pointerdown makes the browser
    // retarget the following `click` to the <svg> (Pointer Events L3), so node/edge
    // onClick never fires. We capture lazily once a real drag begins (see onPointerMove).
    drag.current = { x: ev.clientX, y: ev.clientY, vx: vb.x, vy: vb.y, id: ev.pointerId, captured: false };
  };
  const onPointerMove = (ev) => {
    if (!drag.current) return;
    const r = svgRef.current.getBoundingClientRect();
    const dxPix = ev.clientX - drag.current.x, dyPix = ev.clientY - drag.current.y;
    if (!moved.current && Math.abs(dxPix) + Math.abs(dyPix) > 4) {
      moved.current = true;                       // crossed threshold → this is a pan, not a click
      svgRef.current.setPointerCapture?.(drag.current.id);  // capture now so dragging stays smooth
      drag.current.captured = true;
    }
    if (!moved.current) return;                   // below threshold → keep node/edge clicks intact
    const dx = (dxPix / r.width) * vb.w, dy = (dyPix / r.height) * vb.h;
    setView((v) => ({ ...(v || vb), x: drag.current.vx - dx, y: drag.current.vy - dy }));
  };
  const endPan = (ev) => {
    if (drag.current?.captured) svgRef.current.releasePointerCapture?.(ev.pointerId);
    drag.current = null;
  };
  const reset = () => setView({ x: 0, y: 0, w: baseW, h: baseH });

  // center the viewBox on a node and highlight it
  const focusNode = (id) => {
    const p = pos[id];
    if (!p) return;
    setView((v) => {
      const cur = v || vb;
      const cx = p.x + NW / 2, cy = p.y + NH / 2;
      return { x: cx - cur.w / 2, y: cy - cur.h / 2, w: cur.w, h: cur.h };
    });
    setHitId(id);
  };

  const runFind = () => {
    const q = find.trim().toLowerCase();
    if (!q) { setHitId(null); setFindMiss(false); return; }
    const match = data.nodes.find((n) => n.id.toLowerCase() === q)
      || data.nodes.find((n) => n.id.toLowerCase().includes(q));
    if (match) { focusNode(match.id); setFindMiss(false); }
    else { setHitId(null); setFindMiss(true); }
  };

  const activateNode = (n) => setSel({ type: "node", node: n });

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
        <span><i className="dot" style={{ background: "var(--accent)" }} /> ▸ Job</span>
        <span><i className="dot" style={{ background: "var(--green)" }} /> R Root</span>
        <span><i className="dot" style={{ background: "var(--purple)" }} /> Program</span>
        <span><i className="dot" style={{ background: "var(--red)" }} /> ✕ Dead</span>
        <span><i className="dot" style={{ background: "var(--amber)" }} /> ? Dynamic / unresolved</span>
        <span><svg width="26" height="10"><line x1="0" y1="5" x2="26" y2="5" stroke="var(--amber)" strokeWidth="2" strokeDasharray="4 3" /></svg> needs-review edge</span>
      </div>

      <div className="cg-toolbar">
        <div className="cg-group">
          <span className="cg-label">Zoom</span>
          <button className="cg-zoombtn" onClick={() => zoomBy(1 / 1.2)} aria-label="Zoom in">+</button>
          <button className="cg-zoombtn" onClick={() => zoomBy(1.2)} aria-label="Zoom out">−</button>
          <button className="cg-zoombtn wide" onClick={reset} aria-label="Reset view">Reset</button>
        </div>

        <div className="cg-group cg-find">
          <span className="cg-label">Find</span>
          <input
            type="text"
            placeholder="node id…"
            value={find}
            onChange={(e) => { setFind(e.target.value); setFindMiss(false); }}
            onKeyDown={(e) => { if (e.key === "Enter") runFind(); }}
            aria-label="Find a node by id"
          />
          <button className="cg-zoombtn wide" onClick={runFind}>Go</button>
          {findMiss && <span className="miss">no match</span>}
        </div>

        <div className="cg-group cg-thresh">
          <span className="cg-label">Min confidence</span>
          <input
            type="range" min="0" max="1" step="0.05"
            value={threshold}
            onChange={(e) => setThreshold(parseFloat(e.target.value))}
            aria-label="Minimum edge confidence"
          />
          <span className="val">{threshold.toFixed(2)}</span>
          {hiddenByConf > 0 && <span className="cg-hidden">{hiddenByConf} edge{hiddenByConf === 1 ? "" : "s"} hidden</span>}
        </div>

        {relTypes.length > 0 && (
          <div className="cg-group cg-types">
            <span className="cg-label">Edges</span>
            {relTypes.map((t) => (
              <label key={t}>
                <input
                  type="checkbox"
                  checked={typeOn(t)}
                  onChange={(e) =>
                    setEnabledTypes((cur) => {
                      const base = cur || Object.fromEntries(relTypes.map((x) => [x, true]));
                      return { ...base, [t]: e.target.checked };
                    })
                  }
                />
                {t}
              </label>
            ))}
          </div>
        )}
      </div>

      <div className="graph-layout">
        <div className="graph-wrap">
          <svg
            ref={svgRef}
            className={`cg-svg${drag.current ? " panning" : ""}`}
            width="100%"
            height={baseH}
            viewBox={`${vb.x} ${vb.y} ${vb.w} ${vb.h}`}
            onWheel={onWheel}
            onPointerDown={onPointerDown}
            onPointerMove={onPointerMove}
            onPointerUp={endPan}
            onPointerLeave={endPan}
          >
            <defs>
              <marker id="arrow" markerWidth="8" markerHeight="8" refX="7" refY="3" orient="auto">
                <path d="M0,0 L7,3 L0,6 Z" fill="#5b6b7d" /></marker>
              <marker id="arrow-rev" markerWidth="8" markerHeight="8" refX="7" refY="3" orient="auto">
                <path d="M0,0 L7,3 L0,6 Z" fill="var(--amber)" /></marker>
            </defs>

            {visibleEdges.map(({ e, i }) => {
              const a = pos[e.source], b = pos[e.target];
              if (!a || !b) return null;
              const review = e.validation_status !== "confirmed";
              const on = sel?.type === "edge" && sel.i === i;
              const x1 = a.x + NW, y1 = a.y + NH / 2, x2 = b.x, y2 = b.y + NH / 2;
              const mx = (x1 + x2) / 2, my = (y1 + y2) / 2;
              const selectEdge = () => { if (!moved.current) setSel({ type: "edge", edge: e, i }); };
              return (
                <g key={i} className="cg-edge" onClick={selectEdge} style={{ cursor: "pointer" }}>
                  {/* wide transparent hit area so thin edges are easy to click */}
                  <line x1={x1} y1={y1} x2={x2} y2={y2} stroke="transparent" strokeWidth="14" />
                  <line x1={x1} y1={y1} x2={x2} y2={y2}
                    stroke={on ? "var(--text)" : review ? "var(--amber)" : "#5b6b7d"}
                    strokeWidth={on ? 3 : 1.6} strokeDasharray={review ? "4 3" : "0"}
                    markerEnd={review ? "url(#arrow-rev)" : "url(#arrow)"} />
                  {showEdgeLabels && (
                    <text className="cg-edge-label" x={mx} y={my - 4} textAnchor="middle"
                      fill={on ? "var(--text)" : review ? "var(--amber)" : "var(--muted)"}>
                      {e.rel_type}{e.confidence != null && e.confidence < 1 ? ` ${e.confidence}` : ""}
                    </text>
                  )}
                </g>
              );
            })}

            {data.nodes.map((n) => {
              const p = pos[n.id]; if (!p) return null;
              const nn = { ...n, is_dynamic: dynamicSet.has(n.id) };
              const on = sel?.type === "node" && sel.node.id === n.id;
              const glyph = glyphOf(nn);
              const aria = `${n.type} ${n.id}` +
                (n.is_root ? ", root" : "") + (n.is_dead ? ", dead" : "") +
                (nn.is_dynamic ? ", dynamic or unresolved" : "");
              return (
                <g key={n.id} className={`cg-node${hitId === n.id ? " cg-hit" : ""}`}
                   transform={`translate(${p.x},${p.y})`}
                   tabIndex={0} role="button" aria-label={aria}
                   onClick={() => { if (!moved.current) activateNode(nn); }}
                   onKeyDown={(ev) => {
                     if (ev.key === "Enter" || ev.key === " ") { ev.preventDefault(); activateNode(nn); }
                   }}>
                  <rect className="cg-focus-ring" x="-3" y="-3" width={NW + 6} height={NH + 6} rx="9"
                        fill="none" stroke="var(--accent)" strokeWidth="2" />
                  <rect className="cg-node-rect" width={NW} height={NH} rx="7"
                        fill={on ? "var(--panel)" : "var(--panel-2)"}
                        stroke={colorOf(nn)} strokeWidth={on ? 3 : 2} />
                  <circle cx="11" cy={NH / 2} r="4" fill={colorOf(nn)} />
                  <text x="22" y={NH / 2 + 4} fill="var(--text)" fontSize="11.5"
                        fontFamily="ui-monospace, Consolas, monospace">{n.id}</text>
                  {glyph && (
                    <text x={NW - 11} y={NH / 2 + 4} textAnchor="middle" fontSize="11"
                          fontWeight="700" fill={colorOf(nn)}
                          fontFamily="ui-monospace, Consolas, monospace">{glyph}</text>
                  )}
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
                {sel.edge.discovery_method &&
                  <div><span>Method</span>{sel.edge.discovery_method}</div>}
                {sel.edge.source_evidence &&
                  <div><span>Evidence</span><code>{sel.edge.source_evidence}</code></div>}
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
                {sel.node.is_dead && <span className="badge dead">dead</span>}{" "}
                {sel.node.is_dynamic && <span className="badge review">dynamic</span>}{" "}
                {sel.node.community != null && <span className="badge ok">community {sel.node.community}</span>}
              </div>
              {sel.node.type === "program" ? (
                profile ? (
                  <>
                    <ProfileCard profile={profile} onOpenProgram={onOpenProgram} />
                    <div className="cap-sec">
                      <div className="l">Structure / AST</div>
                      <Structure structure={profile.structure} />
                    </div>
                    <div style={{ display: "flex", gap: 8, marginTop: 12 }}>
                      <button className="btn secondary"
                              onClick={() => onOpenProgram(sel.node.id)}>Open full page →</button>
                      <button className="btn secondary"
                              onClick={() => navigate(`/trace/${encodeURIComponent(sel.node.id)}`)}>Call trace ↗</button>
                    </div>
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
