import React, { useState } from "react";
import { api } from "../api.js";
import { useData } from "../hooks.js";
import ProfileCard from "./ProfileCard.jsx";
import Structure from "./Structure.jsx";

function Insight({ l, v, cls }) {
  return <div className={`insight ${cls || ""}`}><div className="l">{l}</div><div className="v">{v}</div></div>;
}

export default function ProgramDetail({ pid, onOpenProgram, back }) {
  const { data, err, loading } = useData(() => api.profile(pid), [pid]);
  const [src, setSrc] = useState(null);
  const [srcErr, setSrcErr] = useState(null);
  const [impact, setImpact] = useState(null);
  const [impactErr, setImpactErr] = useState(null);

  if (loading) return <div className="loading">Loading…</div>;
  if (err) return <div className="error">{err}</div>;
  const d = data;
  const cx = d.structure?.complexity ?? 0;
  const cxCls = cx <= 4 ? "green" : cx <= 10 ? "amber" : "red";

  const viewSource = async () => {
    setSrcErr(null);
    try { setSrc(await api.source(d.source_path)); }
    catch (e) { setSrcErr(String(e)); }
  };

  const runImpact = async () => {
    setImpactErr(null);
    try { setImpact(await api.impact(pid)); }
    catch (e) { setImpactErr(String(e)); }
  };

  return (
    <div>
      <p><span className="link" onClick={back}>← Programs</span></p>
      <h1 className="page-title">{d.program_id} {d.capability && <span className="badge ok">{d.capability}</span>}</h1>

      <div className="insights">
        <Insight l="Complexity (proxy)" cls={cxCls} v={cx} />
        <Insight l="Fan-out (depends on)" v={d.dependencies.length} />
        <Insight l="Fan-in (used by)" v={d.callers.length} />
        <Insight l="Run by jobs" v={d.executing_jobs.length} />
      </div>

      <div className="panel">
        <h3>Profile</h3>
        <ProfileCard profile={d} onOpenProgram={onOpenProgram} />
      </div>

      <div className="panel">
        <h3>Structure / AST</h3>
        <Structure structure={d.structure} />
      </div>

      <div className="panel">
        <h3>Impact / blast radius
          <button className="btn secondary" style={{ marginLeft: 8 }} onClick={runImpact}>Analyze</button>
          <span className="tag" style={{ marginLeft: 8 }}>NetworkX — what breaks if this changes</span>
        </h3>
        {impactErr && <div className="error">{impactErr}</div>}
        {!impact && !impactErr && <div className="muted">Click “Analyze” to compute the blast radius.</div>}
        {impact && (impact.found ? (
          <>
            <div className="insights" style={{ marginBottom: 12 }}>
              <Insight l="Blast-radius score" cls="amber" v={impact.blast_radius_score} />
              <Insight l="Impacted (upstream)" v={impact.impacted.length} />
              <Insight l="Depends on (downstream)" v={impact.depends_on.length} />
              <Insight l="Reached via needs-review" cls="red" v={impact.review.length} />
            </div>
            <div className="cap-sec">
              <div className="l">Impacted if changed (closest first)</div>
              {impact.impacted.map((x) => (
                <span key={x.id}
                      className={`pill ${x.kind === "program" || x.kind === "job" ? "click" : ""}`}
                      onClick={() => (x.kind === "program") && onOpenProgram(x.id)}
                      title={`${x.kind} · distance ${x.distance} · confidence ${x.confidence}`}>
                  {x.id}{x.via_needs_review ? " ⚠" : ""} <span className="muted">·{x.distance}</span>
                </span>
              ))}
            </div>
            {impact.depends_on.length > 0 && (
              <div className="cap-sec">
                <div className="l">Depends on</div>
                {impact.depends_on.map((x) => (
                  <span key={x.id} className={`pill ${x.kind === "program" ? "click" : x.kind === "copybook" ? "cpy" : "tbl"}`}
                        onClick={() => x.kind === "program" && onOpenProgram(x.id)}>{x.id}</span>
                ))}
              </div>
            )}
          </>
        ) : <div className="muted">No graph node for this id.</div>)}
      </div>

      {d.source_path && (
        <div className="panel">
          <h3>Source <button className="btn secondary" style={{ marginLeft: 8 }} onClick={viewSource}>View</button>
            <span className="tag" style={{ marginLeft: 8 }}>{d.source_path}</span></h3>
          {srcErr && <div className="error">{srcErr}</div>}
          {src && <pre className="code">{src.text}</pre>}
          {!src && !srcErr && <div className="muted">Click “View” to load the member source.</div>}
        </div>
      )}
    </div>
  );
}
