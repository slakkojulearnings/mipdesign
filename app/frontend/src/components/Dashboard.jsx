import React from "react";
import { api } from "../api.js";
import { useData } from "../hooks.js";

function Card({ n, l, cls }) {
  return <div className={`card ${cls || ""}`}><div className="n">{n}</div><div className="l">{l}</div></div>;
}

export default function Dashboard({ go }) {
  const { data, err, loading } = useData(() => api.summary());
  const { data: ins } = useData(() => api.insights());
  if (loading) return <div className="loading">Loading…</div>;
  if (err) return <div className="error">{err}</div>;
  const s = data;
  const top = ins?.most_depended_on?.[0];
  return (
    <div>
      <h1 className="page-title">Discovery Dashboard</h1>
      <p className="page-sub">Evidence-based inventory of the scanned mainframe estate.</p>
      <div className="cards">
        <Card n={s.artifacts} l="Artifacts" />
        <Card n={s.programs} l="Programs" />
        <Card n={s.jobs} l="Jobs" />
        <Card n={s.edges} l="Relationships" />
        <Card n={s.roots} l="Root programs" cls="green" />
        <Card n={s.dead_code} l="Dead-code" cls="red" />
        <Card n={s.needs_review_edges} l="Needs review" cls="amber" />
      </div>

      {ins && (
        <div className="insights" style={{ marginTop: 18 }}>
          <div className="insight green"><div className="l">Most depended-on</div>
            <div className="v">{top ? <span className="link" onClick={() => go("graph")}>{top.program} <small>×{top.called_by} callers</small></span> : "—"}</div></div>
          <div className="insight amber"><div className="l">Needs review (dynamic)</div>
            <div className="v">{ins.dynamic_edges.length} <small>edge(s)</small></div></div>
          <div className="insight red"><div className="l">Dead-code candidates</div>
            <div className="v">{ins.dead.length}</div></div>
        </div>
      )}

      <div className="panel" style={{ marginTop: 22 }}>
        <h3>Artifact breakdown</h3>
        <div className="cards">
          {Object.entries(s.by_type || {}).map(([t, c]) => <Card key={t} n={c} l={t} />)}
        </div>
      </div>

      <div className="panel">
        <h3>Where to start</h3>
        <p className="muted" style={{ margin: 0 }}>
          The platform answers <em>understand-before-transform</em> questions.
          See <span className="link" onClick={() => go("graph")}>the Call Graph</span>,
          the <span className="link" onClick={() => go("roots")}>root/driver programs</span> (true entry points),
          or ask the <span className="link" onClick={() => go("query")}>Query Console</span>
          {" "}e.g. “which jobs execute CRDPOST”. The {s.needs_review_edges} needs-review
          relationship(s) are dynamic/unresolved calls — kept and flagged, never dropped.
        </p>
      </div>
    </div>
  );
}
