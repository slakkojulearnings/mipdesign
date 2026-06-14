import React from "react";
import { api } from "../api.js";
import { useData } from "../hooks.js";

export default function Capabilities({ onOpenProgram }) {
  const { data, err, loading } = useData(() => api.capabilities());
  const { data: comm } = useData(() => api.communities());
  if (loading) return <div className="loading">Loading…</div>;
  if (err) return <div className="error">{err}</div>;

  return (
    <div>
      <h1 className="page-title">Business Capabilities</h1>
      <p className="page-sub">
        Functional areas recovered from the artifacts — each is a root driver plus its call-closure.
        Labels are <strong>inferred</strong> from naming + structure (confidence-scored), never asserted as ground truth.
      </p>

      {comm && comm.communities.length > 0 && (
        <div className="panel" style={{ marginBottom: 18 }}>
          <h3>Structural communities — Louvain
            <span className="tag" style={{ marginLeft: 8 }}>
              {comm.communities.length} domains · modularity {comm.modularity}
            </span>
          </h3>
          <p className="muted" style={{ marginTop: 0, fontSize: 12 }}>
            Application/domain boundaries detected from the dependency graph (calls + shared
            copybooks/tables) — independent of naming. Inferred; review before trusting.
          </p>
          <div className="cap-grid">
            {comm.communities.map((c) => (
              <div className="cap-card" key={c.id}>
                <h3>{c.label} <span className="badge review">community {c.id} · inferred</span></h3>
                <div className="root">{c.size} programs</div>
                <div className="cap-sec">
                  {c.members.map((m) => (
                    <span key={m} className="pill click" onClick={() => onOpenProgram(m)}>{m}</span>
                  ))}
                </div>
              </div>
            ))}
          </div>
        </div>
      )}

      <h3 style={{ margin: "0 0 12px" }}>Capability map (root-driven)</h3>
      <div className="cap-grid">
        {data.map((c) => (
          <div className="cap-card" key={c.root}>
            <h3>{c.capability} <span className="badge review">inferred · {c.confidence}</span></h3>
            <div className="root">entry: <span className="link" onClick={() => onOpenProgram(c.root)}>{c.root}</span> · {c.jobs.join(", ") || "no job"}</div>

            <div className="cap-sec">
              <div className="l">Programs &amp; their function</div>
              {c.functions.map((f) => (
                <div key={f.program} style={{ padding: "2px 0" }}>
                  <span className="link rel" onClick={() => onOpenProgram(f.program)}>{f.program}</span>
                  {f.role && f.role !== f.program && <span className="muted"> — {f.role}</span>}
                </div>
              ))}
            </div>

            {c.tables.length > 0 && (
              <div className="cap-sec">
                <div className="l">Data (tables)</div>
                {c.tables.map((t) => <span key={t} className="pill tbl">{t}</span>)}
              </div>
            )}
            {c.copybooks.length > 0 && (
              <div className="cap-sec">
                <div className="l">Shared structures</div>
                {c.copybooks.map((t) => <span key={t} className="pill cpy">{t}</span>)}
              </div>
            )}
            <div className="cap-sec muted" style={{ fontSize: 12 }}>{c.reason}</div>
          </div>
        ))}
      </div>
    </div>
  );
}
