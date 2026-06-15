import React, { useEffect, useRef, useState } from "react";
import { useSearchParams } from "react-router-dom";
import { api } from "../api.js";
import Trace from "./Trace.jsx";
import ProfileCard from "./ProfileCard.jsx";
import Structure from "./Structure.jsx";

const EXAMPLES = [
  "which jobs execute CRDPOST",
  "what does INTDRV call",
  "what does PAYUPD use and write",
  "show root programs",
  "show dead code",
];

function Result({ kind, result, onOpenProgram }) {
  if (kind === "help" || result == null)
    return <div className="muted">Ask about a program by name, or for roots / dead code.</div>;

  if (kind === "jobs_executing")
    return result.length
      ? <ul>{result.map((j) => <li key={j} className="rel">{j}</li>)}</ul>
      : <div className="muted">No job executes it.</div>;

  if (kind === "calls")
    return result.map((r, i) => (
      <div key={i} className="rel">
        <span className="t">CALLS</span> → <span className="link" onClick={() => onOpenProgram(r.target_id)}>{r.target_id}</span>{" "}
        {r.validation_status !== "confirmed" && <span className="badge review">{r.validation_status} · {r.confidence}</span>}
      </div>
    ));

  if (kind === "dependencies")
    return result.map((r, i) => (
      <div key={i} className="rel">
        <span className="t">{r.rel_type}</span> → {r.target_id} <span className="tag">({r.target_type})</span>{" "}
        {r.validation_status !== "confirmed" && <span className="badge review">{r.validation_status}</span>}
      </div>
    ));

  if (kind === "roots" || kind === "dead_code")
    return result.map((p) => (
      <div key={p} className="rel"><span className="link" onClick={() => onOpenProgram(p)}>{p}</span></div>
    ));

  return <pre className="code">{JSON.stringify(result, null, 2)}</pre>;
}

export default function QueryConsole({ onOpenProgram }) {
  const [params, setParams] = useSearchParams();
  const initial = params.get("q") || "which jobs execute CRDPOST";
  const [q, setQ] = useState(initial);
  const [res, setRes] = useState(null);
  const [err, setErr] = useState(null);
  const [busy, setBusy] = useState(false);

  // Run a query and (optionally) push it into the URL so /query?q=... is shareable.
  const run = async (question, share = true) => {
    const text = question ?? q;
    if (share) setParams(text ? { q: text } : {}, { replace: true });
    setBusy(true); setErr(null);
    try { setRes(await api.query(text)); }
    catch (e) { setErr(String(e)); }
    finally { setBusy(false); }
  };

  // Deep link: if the page is opened with ?q=..., prefill + run it once.
  const ranInitial = useRef(false);
  useEffect(() => {
    const deep = params.get("q");
    if (deep && !ranInitial.current) {
      ranInitial.current = true;
      setQ(deep);
      run(deep, false);
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  return (
    <div>
      <h1 className="page-title">Query Console</h1>
      <p className="page-sub">Natural-language questions answered over the knowledge graph (facts, not guesses).</p>

      <div className="topbar">
        <input className="q" value={q} onChange={(e) => setQ(e.target.value)}
               onKeyDown={(e) => e.key === "Enter" && run()} placeholder="e.g. which jobs execute CRDPOST" />
        <button className="btn" onClick={() => run()} disabled={busy}>{busy ? "…" : "Ask"}</button>
      </div>
      <div className="chips">
        {EXAMPLES.map((ex) => (
          <span key={ex} className="chip" onClick={() => { setQ(ex); run(ex); }}>{ex}</span>
        ))}
      </div>

      {err && <div className="error">{err}</div>}
      {res && (
        <>
          <div className="panel" style={{ marginTop: 16 }}>
            <h3>Answer <span className="tag">({res.kind})</span></h3>
            <Result kind={res.kind} result={res.result} onOpenProgram={onOpenProgram} />
          </div>
          <div className="panel">
            <h3>Why — reasoning trace <span className="tag">(logged to question_log.md)</span></h3>
            <Trace trace={res.trace} />
          </div>
          {res.profile && (
            <div className="panel">
              <h3>Complete profile — {res.profile.program_id}
                {res.profile.capability && <span className="badge ok" style={{ marginLeft: 8 }}>{res.profile.capability}</span>}</h3>
              <ProfileCard profile={res.profile} onOpenProgram={onOpenProgram} />
              <div className="cap-sec">
                <div className="l">Structure / AST</div>
                <Structure structure={res.profile.structure} />
              </div>
            </div>
          )}
        </>
      )}
    </div>
  );
}
