import React, { useState } from "react";
import { useNavigate } from "react-router-dom";
import { api } from "../api.js";
import { useData } from "../hooks.js";
import ProfileCard from "./ProfileCard.jsx";
import Structure from "./Structure.jsx";
import SequenceDiagram from "./SequenceDiagram.jsx";
import LineageDiagram from "./LineageDiagram.jsx";

function Insight({ l, v, cls }) {
  return <div className={`insight ${cls || ""}`}><div className="l">{l}</div><div className="v">{v}</div></div>;
}

// "path:line" -> { path, line }. The backend addresses source by relative path,
// so we split on the LAST colon (Windows drive colons never appear here).
function splitEvidence(ev) {
  if (!ev) return null;
  const m = /^(.*):(\d+)$/.exec(ev);
  return m ? { path: m[1], line: Number(m[2]) } : { path: ev, line: null };
}

// Clickable "file:line" tag that opens the member source in a modal near the line.
function EvidenceTag({ evidence, onOpen }) {
  if (!evidence) return null;
  return (
    <span className="tag evidence-link" title="View source evidence"
          onClick={() => onOpen(evidence)}>{evidence}</span>
  );
}

// Best-effort source viewer modal: loads the member and highlights the cited line.
function EvidenceModal({ evidence, onClose }) {
  const loc = splitEvidence(evidence);
  const { data, err, loading } = useData(() => api.source(loc.path), [evidence]);
  const lines = data ? data.text.split("\n") : [];
  return (
    <div className="modal-backdrop" onClick={onClose}>
      <div className="modal" onClick={(e) => e.stopPropagation()}>
        <div className="modal-head">
          <h3>{loc.path}{loc.line ? `:${loc.line}` : ""}</h3>
          <button className="btn secondary" onClick={onClose}>Close</button>
        </div>
        {loading && <div className="loading">Loading source…</div>}
        {err && <div className="error">{err}</div>}
        {data && (
          <pre className="code modal-src">
            {lines.map((ln, i) => {
              const n = i + 1;
              const hit = loc.line === n;
              return (
                <div key={n} ref={hit ? (el) => el && el.scrollIntoView({ block: "center" }) : null}
                     className={hit ? "src-line hit" : "src-line"}>
                  <span className="src-ln">{n}</span>{ln}
                </div>
              );
            })}
          </pre>
        )}
      </div>
    </div>
  );
}

export default function ProgramDetail({ pid, onOpenProgram, back }) {
  const navigate = useNavigate();
  const { data, err, loading } = useData(() => api.profile(pid), [pid]);
  const [src, setSrc] = useState(null);
  const [srcErr, setSrcErr] = useState(null);
  const [impact, setImpact] = useState(null);
  const [impactErr, setImpactErr] = useState(null);
  const [lineage, setLineage] = useState(null);
  const [rules, setRules] = useState(null);
  const [rulesErr, setRulesErr] = useState(null);
  const [seq, setSeq] = useState(null);
  const [seqErr, setSeqErr] = useState(null);
  const [evidence, setEvidence] = useState(null);   // "path:line" currently open in modal

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

  const runLineage = async () => {
    try { setLineage(await api.lineage(pid)); }
    catch (e) { setLineage({ flows: [], error: String(e) }); }
  };

  const runRules = async () => {
    setRulesErr(null);
    try { setRules(await api.rules(pid)); }
    catch (e) { setRulesErr(String(e)); }
  };

  const runSequence = async () => {
    setSeqErr(null);
    try { setSeq(await api.sequence(pid)); }
    catch (e) { setSeqErr(String(e)); }
  };

  return (
    <div>
      <p><span className="link" onClick={back}>← Programs</span></p>
      <div style={{ display: "flex", alignItems: "center", gap: 12 }}>
        <h1 className="page-title" style={{ margin: 0 }}>{d.program_id} {d.capability && <span className="badge ok">{d.capability}</span>}</h1>
        <button className="btn secondary" onClick={() => navigate(`/trace/${encodeURIComponent(d.program_id)}`)}>
          Call trace (up + down) →
        </button>
      </div>

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

      <div className="panel">
        <h3>Sequence diagram
          <button className="btn secondary" style={{ marginLeft: 8 }} onClick={runSequence}>Render</button>
          <span className="tag" style={{ marginLeft: 8 }}>call/exec interactions for this program</span>
        </h3>
        {seqErr && <div className="error">{seqErr}</div>}
        {!seq && !seqErr && <div className="muted">Click “Render” to draw this program's interactions.</div>}
        {seq && (seq.mermaid
          ? <SequenceDiagram code={seq.mermaid} />
          : <div className="muted">No interactions to diagram.</div>)}
      </div>

      <div className="panel">
        <h3>Field-level data lineage
          <button className="btn secondary" style={{ marginLeft: 8 }} onClick={runLineage}>Trace</button>
          <span className="tag" style={{ marginLeft: 8 }}>grammar parser — MOVE + SQL host-var ↔ column</span>
        </h3>
        {lineage && lineage.error && <div className="error">{lineage.error}</div>}
        {!lineage && <div className="muted">Click “Trace” to follow data into and out of this program's fields.</div>}
        {lineage && lineage.flows.length === 0 && !lineage.error
          && <div className="muted">No field-level flows detected (no MOVE/SQL data movement parsed).</div>}
        {lineage && lineage.flows.length > 0 && (
          <>
            <LineageDiagram flows={lineage.flows} />
            <div className="cap-sec" style={{ marginTop: 12 }}>
              <div className="l">Flows (text)</div>
              {lineage.flows.map((f, i) => (
                <div key={i} className="rel" style={{ padding: "2px 0" }}>
                  <span>{f.src}</span> <span className="t">→</span> <span>{f.dst}</span>{" "}
                  <span className="badge ok">{f.kind}</span>{" "}
                  <EvidenceTag evidence={f.evidence} onOpen={setEvidence} />
                </div>
              ))}
            </div>
          </>
        )}
      </div>

      <div className="panel">
        <h3>Business rules
          <button className="btn secondary" style={{ marginLeft: 8 }} onClick={runRules}>Extract</button>
          <span className="tag" style={{ marginLeft: 8 }}>conditions &amp; validations recovered from the code</span>
        </h3>
        {rulesErr && <div className="error">{rulesErr}</div>}
        {!rules && !rulesErr && <div className="muted">Click “Extract” to recover the business rules in this program.</div>}
        {rules && (rules.rules.length === 0
          ? <div className="muted">No business rules detected.</div>
          : rules.rules.map((r, i) => {
              const review = r.validation_status !== "confirmed";
              return (
                <div key={r.id || i} className="rule">
                  <div className="rule-head">
                    <span className={`badge ${review ? "review" : "ok"}`}>{r.kind || "rule"}</span>
                    {review
                      ? <span className="badge review">{r.validation_status || "inferred"}{r.confidence != null ? ` · ${r.confidence}` : ""}</span>
                      : <span className="badge ok">confirmed{r.confidence != null ? ` · ${r.confidence}` : ""}</span>}
                  </div>
                  {r.statement && <div className="rule-stmt">{r.statement}</div>}
                  {r.condition && <pre className="rule-cond">{r.condition}</pre>}
                  {r.action && <div className="muted" style={{ fontSize: 13 }}>→ {r.action}</div>}
                  {((r.fields && r.fields.length) || (r.tables && r.tables.length)) ? (
                    <div className="cap-sec" style={{ marginTop: 8 }}>
                      {(r.fields || []).map((f) => <span key={"f" + f} className="pill">{f}</span>)}
                      {(r.tables || []).map((t) => <span key={"t" + t} className="pill tbl">{t}</span>)}
                    </div>
                  ) : null}
                  {r.source_evidence && <EvidenceTag evidence={r.source_evidence} onOpen={setEvidence} />}
                </div>
              );
            }))}
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

      {evidence && <EvidenceModal evidence={evidence} onClose={() => setEvidence(null)} />}
    </div>
  );
}
