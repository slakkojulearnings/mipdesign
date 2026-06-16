import React, { useState } from "react";
import { useNavigate } from "react-router-dom";
import { api } from "../api.js";
import { useData } from "../hooks.js";
import "./CallTrace.css";

const KIND = {
  program: "#5e5ce6", job: "#ff9500", db2_table: "#248a3d",
  copybook: "#0071e3", transaction: "#b25e00",
};
const colorOf = (k) => KIND[k] || "#8a8a92";

// layered layout: upstream depths negative (left), focus 0, downstream positive (right)
function layout(focus, nodes, edges) {
  const depth = { [focus]: 0 };
  const downAdj = {}, upRev = {};
  edges.forEach((e) => {
    if (e.direction === "down") (downAdj[e.source] ||= []).push(e.target);
    else (upRev[e.target] ||= []).push(e.source);
  });
  let q = [focus];
  while (q.length) { const u = q.shift(); for (const v of downAdj[u] || []) if (!(v in depth)) { depth[v] = depth[u] + 1; q.push(v); } }
  q = [focus];
  while (q.length) { const u = q.shift(); for (const v of upRev[u] || []) if (!(v in depth)) { depth[v] = depth[u] - 1; q.push(v); } }
  nodes.forEach((n) => { if (!(n.id in depth)) depth[n.id] = 0; });

  const cols = {};
  nodes.forEach((n) => { (cols[depth[n.id]] ||= []).push(n.id); });
  const ds = Object.keys(cols).map(Number).sort((a, b) => a - b);
  const minD = ds[0] ?? 0, maxD = ds[ds.length - 1] ?? 0;
  const colW = 180, rowH = 48, padX = 16, padY = 16, NW = 138, NH = 30;
  const pos = {}; let maxRows = 0;
  ds.forEach((d) => {
    cols[d].sort(); maxRows = Math.max(maxRows, cols[d].length);
    cols[d].forEach((id, i) => { pos[id] = { x: padX + (d - minD) * colW, y: padY + i * rowH }; });
  });
  return { pos, NW, NH,
    width: padX * 2 + (maxD - minD + 1) * colW,
    height: padY * 2 + Math.max(1, maxRows) * rowH };
}

export default function CallTrace({ pid, onOpenProgram, back }) {
  const navigate = useNavigate();
  const [direction, setDirection] = useState("both");
  const [depth, setDepth] = useState(8);
  const [includeData, setIncludeData] = useState(true);
  const { data: t, err, loading } =
    useData(() => api.trace(pid, { direction, depth, includeData }), [pid, direction, depth, includeData]);

  if (loading) return <div className="loading">Loading…</div>;
  if (err) return <div className="error">{err}</div>;

  const goTrace = (id) => navigate(`/trace/${encodeURIComponent(id)}`);

  // ---- readable tree (recursive) ----
  const renderNode = (node, up, key) => {
    if (!node) return null;
    return (
      <li key={key}>
        <div className="tr-row">
          <span className="tr-id" style={{ color: colorOf(node.kind) }}
                onClick={() => goTrace(node.id)}>{node.id}</span>
          <span className="tr-kind">{node.kind}</span>
          {node.repeated && <span className="muted tr-rep">(shown above)</span>}
        </div>
        {node.children && node.children.length > 0 && (
          <ul className="tr-children">
            {node.children.map((c, i) => (
              <li key={i}>
                <div className="tr-edge">
                  <span className="tr-rel">{up ? "←" : "→"} {c.rel}</span>
                  {c.validation_status !== "confirmed" &&
                    <span className="badge review">{c.validation_status} · {c.confidence}</span>}
                  {c.evidence && <span className="tr-ev">{c.evidence}</span>}
                </div>
                <ul className="tr-children">{renderNode(c.node, up, i)}</ul>
              </li>
            ))}
          </ul>
        )}
      </li>
    );
  };

  // ---- Markdown export ----
  const md = () => {
    const L = [`# Call trace — ${t.program} (${t.kind})`, ""];
    const walk = (node, up, d) => {
      if (!node) return;
      (node.children || []).forEach((c) => {
        const arrow = up ? "←" : "→";
        const flag = c.validation_status !== "confirmed" ? ` _(${c.validation_status} ${c.confidence})_` : "";
        L.push(`${"  ".repeat(d)}- ${arrow} ${c.rel} \`${c.node.id}\` (${c.node.kind})${c.node.repeated ? " — shown above" : ""} · \`${c.evidence}\`${flag}`);
        if (!c.node.repeated) walk(c.node, up, d + 1);
      });
    };
    if (t.downstream) { L.push("## Downstream — what it calls + data it touches", "", `\`${t.program}\``); walk(t.downstream, false, 1); L.push(""); }
    if (t.upstream) { L.push("## Upstream — who triggers it", "", `\`${t.program}\``); walk(t.upstream, true, 1); L.push(""); }
    L.push("## DB touchpoints", "", `- reads: ${t.db_touchpoints.reads.join(", ") || "—"}`, `- writes: ${t.db_touchpoints.writes.join(", ") || "—"}`, "");
    if (t.stats.unresolved.length) {
      L.push("## Unresolved / dynamic (kept & flagged)", "");
      t.stats.unresolved.forEach((u) => L.push(`- ${u.source} ${u.rel} ${u.target} — ${u.validation_status}`));
    }
    return L.join("\n");
  };
  const download = () => {
    const blob = new Blob([md()], { type: "text/markdown" });
    const a = document.createElement("a");
    a.href = URL.createObjectURL(blob); a.download = `${t.program}-trace.md`; a.click();
  };

  const lay = layout(t.program, t.nodes, t.edges);
  const posOf = (id) => lay.pos[id];

  return (
    <div>
      <div className="topbar-min">
        <button className="btn secondary" onClick={back}>← Back</button>
        <div style={{ flex: 1 }} />
        <button className="btn secondary" onClick={() => onOpenProgram(t.program)}>Open program page →</button>
        <button className="btn" onClick={download}>⤓ Export Markdown</button>
      </div>

      <h1 className="page-title">Call trace — {t.program}</h1>
      <p className="page-sub">
        Complete upstream (who triggers it) and downstream (what it calls + the DB/copybooks it
        touches) trace. Each hop cites <strong>file:line</strong>; dynamic/unresolved branches are
        kept and <strong>flagged</strong>, never dropped.
      </p>

      <div className="trace-controls">
        <label>Direction
          <select value={direction} onChange={(e) => setDirection(e.target.value)}>
            <option value="both">both</option>
            <option value="down">downstream only</option>
            <option value="up">upstream only</option>
          </select>
        </label>
        <label>Depth
          <select value={depth} onChange={(e) => setDepth(Number(e.target.value))}>
            {[3, 5, 8, 12, 20].map((d) => <option key={d} value={d}>{d}</option>)}
          </select>
        </label>
        <label className="trace-chk">
          <input type="checkbox" checked={includeData} onChange={(e) => setIncludeData(e.target.checked)} />
          include DB &amp; copybooks
        </label>
        <span className="muted">{t.stats.node_count} nodes · {t.stats.edge_count} edges
          {t.stats.unresolved_count > 0 && <> · <span className="badge review">{t.stats.unresolved_count} unresolved</span></>}
        </span>
      </div>

      <div className="trace-db">
        <span className="l">DB touchpoints</span>
        <span>reads: {t.db_touchpoints.reads.length ? t.db_touchpoints.reads.map((x) => <span key={x} className="pill tbl">{x}</span>) : <span className="muted">—</span>}</span>
        <span>writes: {t.db_touchpoints.writes.length ? t.db_touchpoints.writes.map((x) => <span key={x} className="pill" style={{ borderColor: "rgba(36,138,61,.4)" }}>{x}</span>) : <span className="muted">—</span>}</span>
      </div>

      {/* interactive subgraph */}
      <div className="panel" style={{ marginBottom: 16 }}>
        <h3>Trace graph <span className="tag" style={{ marginLeft: 8 }}>upstream ◀ {t.program} ▶ downstream · click a node to re-root</span></h3>
        <div className="trace-graph-wrap">
          <svg className="trace-svg" width={lay.width} height={lay.height}
               viewBox={`0 0 ${lay.width} ${lay.height}`}>
            <defs>
              <marker id="tr-arrow" markerWidth="8" markerHeight="8" refX="7" refY="3" orient="auto">
                <path d="M0,0 L7,3 L0,6 Z" fill="#5b6b7d" /></marker>
              <marker id="tr-arrow-r" markerWidth="8" markerHeight="8" refX="7" refY="3" orient="auto">
                <path d="M0,0 L7,3 L0,6 Z" fill="var(--amber)" /></marker>
            </defs>
            {t.edges.map((e, i) => {
              const a = posOf(e.source), b = posOf(e.target);
              if (!a || !b) return null;
              const review = e.validation_status !== "confirmed";
              return (
                <line key={i} x1={a.x + lay.NW} y1={a.y + lay.NH / 2} x2={b.x} y2={b.y + lay.NH / 2}
                  stroke={review ? "var(--amber)" : "#5b6b7d"} strokeWidth="1.5"
                  strokeDasharray={review ? "4 3" : "0"}
                  markerEnd={review ? "url(#tr-arrow-r)" : "url(#tr-arrow)"} />
              );
            })}
            {t.nodes.map((n) => {
              const p = posOf(n.id); if (!p) return null;
              const focus = n.id === t.program;
              return (
                <g key={n.id} transform={`translate(${p.x},${p.y})`} style={{ cursor: "pointer" }}
                   onClick={() => goTrace(n.id)}>
                  <rect width={lay.NW} height={lay.NH} rx="7"
                        fill={focus ? "var(--panel-2)" : "#fff"} stroke={colorOf(n.kind)}
                        strokeWidth={focus ? 3 : 2} />
                  <circle cx="11" cy={lay.NH / 2} r="4" fill={colorOf(n.kind)} />
                  <text x="22" y={lay.NH / 2 + 4} fontSize="11.5" fill="var(--text)"
                        fontFamily="ui-monospace, Consolas, monospace">{n.id}</text>
                </g>
              );
            })}
          </svg>
        </div>
      </div>

      {/* readable trees */}
      <div className="trace-trees">
        {t.downstream && (
          <div className="panel">
            <h3>Downstream <span className="tag" style={{ marginLeft: 8 }}>calls + data it touches</span></h3>
            <ul className="tr-root">{renderNode(t.downstream, false, "d")}</ul>
          </div>
        )}
        {t.upstream && (
          <div className="panel">
            <h3>Upstream <span className="tag" style={{ marginLeft: 8 }}>who triggers it (← = inbound)</span></h3>
            <ul className="tr-root">{renderNode(t.upstream, true, "u")}</ul>
          </div>
        )}
      </div>
    </div>
  );
}
