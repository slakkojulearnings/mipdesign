import React, { useState } from "react";
import { api } from "../api.js";
import { useData } from "../hooks.js";
import Trace from "./Trace.jsx";

export default function QaLog() {
  const { data, err, loading, reload } = useData(() => api.log());
  const [raw, setRaw] = useState(null);

  if (loading) return <div className="loading">Loading…</div>;
  if (err) return <div className="error">{err}</div>;

  return (
    <div>
      <h1 className="page-title">Q&amp;A Log</h1>
      <p className="page-sub">
        Every question is recorded to <code>question_log.md</code> with its reasoning and
        evidence — an auditable trail (newest first).
      </p>
      <div className="topbar">
        <div style={{ flex: 1 }} />
        <button className="btn secondary" onClick={reload}>↻ Refresh</button>
        <button className="btn secondary" onClick={async () => setRaw(raw ? null : (await api.logRaw()).markdown)}>
          {raw ? "Hide raw .md" : "View raw question_log.md"}
        </button>
      </div>

      {raw && <pre className="code">{raw}</pre>}

      {data.length === 0 && <div className="muted">No questions logged yet. Ask something in the Query Console.</div>}

      {data.map((e, i) => (
        <div key={i} className="panel">
          <div style={{ display: "flex", justifyContent: "space-between", alignItems: "baseline" }}>
            <h3 style={{ margin: 0 }}>{e.question}</h3>
            <span className="tag">{e.discovered_at}</span>
          </div>
          <div style={{ margin: "6px 0 12px" }}>
            <span className="badge ok">{e.intent}</span>{" "}
            {e.program && <span className="tag">program: {e.program}</span>}
          </div>
          <Trace trace={e} />
        </div>
      ))}
    </div>
  );
}
