import React from "react";
import { api } from "../api.js";
import { useData } from "../hooks.js";

const CFG = {
  roots: {
    title: "Root / Driver Programs",
    sub: "True execution entry points — executed by a job and not called by another program.",
    load: () => api.roots(),
    badge: "root",
  },
  deadcode: {
    title: "Dead-Code Candidates",
    sub: "Unreachable from any root. Flagged needs_review — may still be invoked dynamically or externally.",
    load: () => api.deadcode(),
    badge: "dead",
  },
};

export default function Lists({ kind, onOpenProgram }) {
  const cfg = CFG[kind];
  const { data, err, loading } = useData(cfg.load, [kind]);
  if (loading) return <div className="loading">Loading…</div>;
  if (err) return <div className="error">{err}</div>;
  return (
    <div>
      <h1 className="page-title">{cfg.title}</h1>
      <p className="page-sub">{cfg.sub}</p>
      {data.length === 0 ? <div className="muted">None found.</div> : (
        <div className="panel">
          {data.map((pid) => (
            <div key={pid} style={{ padding: "6px 0" }}>
              <span className={`badge ${cfg.badge}`}>{cfg.badge}</span>{" "}
              <span className="link" onClick={() => onOpenProgram(pid)}>{pid}</span>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
