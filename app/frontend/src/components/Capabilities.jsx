import React from "react";
import { api } from "../api.js";
import { useData } from "../hooks.js";

export default function Capabilities({ onOpenProgram }) {
  const { data, err, loading } = useData(() => api.capabilities());
  if (loading) return <div className="loading">Loading…</div>;
  if (err) return <div className="error">{err}</div>;

  return (
    <div>
      <h1 className="page-title">Business Capabilities</h1>
      <p className="page-sub">
        Functional areas recovered from the artifacts — each is a root driver plus its call-closure.
        Labels are <strong>inferred</strong> from naming + structure (confidence-scored), never asserted as ground truth.
      </p>

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
