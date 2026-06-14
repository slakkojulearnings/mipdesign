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
