import React from "react";
import { api } from "../api.js";
import { useData } from "../hooks.js";

// Build a self-contained Markdown requirements document from the API payload.
function toMarkdown(d) {
  const L = [];
  L.push(`# ${d.capability} — Requirements`);
  L.push("");
  L.push(`> Entry point (root driver): **${d.root}** · inferred (confidence ${d.confidence})`);
  L.push(`>`);
  L.push(`> ${d.disclaimer}`);
  L.push("");
  L.push("## Functional requirements");
  L.push("");
  L.push("### Triggers (how this capability runs)");
  if (d.triggers.length) d.triggers.forEach((t) => L.push(`- ${t.type}: \`${t.id}\``));
  else L.push("- _none detected_");
  L.push("");
  L.push("### Programs & their function");
  d.programs.forEach((p) => {
    const role = p.role && p.role !== p.program ? ` — ${p.role}` : "";
    const calls = p.calls.length ? ` (calls ${p.calls.join(", ")})` : "";
    L.push(`- \`${p.program}\`${role}${calls}${p.line_count ? ` · ${p.line_count} lines` : ""}`);
  });
  L.push("");
  if (d.tables.length) {
    L.push("### Data touched");
    d.tables.forEach((t) => L.push(`- \`${t.table}\` — ${t.access.join(" / ")}`));
    L.push("");
  }
  if (d.copybooks.length) {
    L.push("### Shared structures (copybooks)");
    d.copybooks.forEach((c) => L.push(`- \`${c}\``));
    L.push("");
  }
  L.push("## Business rules");
  L.push("");
  L.push(`_${d.business_rules.length} rule(s) extracted across ${d.summary.program_count} program(s). Each cites a source line._`);
  L.push("");
  if (d.business_rules.length) {
    let cur = null;
    d.business_rules.forEach((r) => {
      const prog = r.id.split("-")[0];
      if (prog !== cur) { cur = prog; L.push(`### ${prog}`); L.push(""); }
      L.push(`- **${r.kind}** — ${r.statement}`);
      L.push(`  - condition: \`${r.condition}\``);
      L.push(`  - evidence: \`${r.source_evidence}\` · ${r.validation_status} (confidence ${r.confidence})`);
    });
    L.push("");
  } else {
    L.push("_No IF / EVALUATE / COMPUTE rules found in the member programs._");
    L.push("");
  }
  return L.join("\n");
}

function download(name, text) {
  const blob = new Blob([text], { type: "text/markdown" });
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url; a.download = name; a.click();
  URL.revokeObjectURL(url);
}

// group business rules by program (id prefix before "-Rnnn")
function groupRules(rules) {
  const g = {};
  rules.forEach((r) => { const p = r.id.split("-")[0]; (g[p] ||= []).push(r); });
  return g;
}

export default function CapabilityRequirements({ name, onOpenProgram, back }) {
  const { data: d, err, loading } = useData(() => api.capabilityRequirements(name), [name]);
  if (loading) return <div className="loading">Loading…</div>;
  if (err) return <div className="error">{err}</div>;

  const grouped = groupRules(d.business_rules);

  return (
    <div>
      <div className="topbar-min">
        <button className="btn secondary" onClick={back}>← Capabilities</button>
        <div style={{ flex: 1 }} />
        <button className="btn" onClick={() => download(`${d.root}-requirements.md`, toMarkdown(d))}>
          ⤓ Export Markdown
        </button>
      </div>

      <h1 className="page-title">{d.capability} — Requirements</h1>
      <p className="page-sub">
        Entry point <span className="link" onClick={() => onOpenProgram(d.root)}>{d.root}</span>{" "}
        <span className="badge review">inferred · {d.confidence}</span>
      </p>

      <div className="req-disclaimer">{d.disclaimer}</div>

      <div className="req-stats">
        <span><b>{d.summary.program_count}</b> programs</span>
        <span><b>{d.summary.rule_count}</b> business rules</span>
        <span><b>{d.summary.table_count}</b> tables</span>
        <span><b>{d.summary.trigger_count}</b> triggers</span>
      </div>

      {/* ---- Functional requirements ---- */}
      <div className="panel">
        <h3>Functional requirements</h3>

        <div className="cap-sec">
          <div className="l">Triggers — how this capability runs</div>
          {d.triggers.length
            ? d.triggers.map((t) => (
                <div key={t.type + t.id} style={{ padding: "2px 0" }}>
                  <span className="pill">{t.type}</span> <code>{t.id}</code>
                </div>))
            : <span className="muted">none detected</span>}
        </div>

        <div className="cap-sec">
          <div className="l">Programs &amp; their function</div>
          {d.programs.map((p) => (
            <div key={p.program} style={{ padding: "2px 0" }}>
              <span className="link rel" onClick={() => onOpenProgram(p.program)}>{p.program}</span>
              {p.role && p.role !== p.program && <span className="muted"> — {p.role}</span>}
              {p.calls.length > 0 && <span className="muted"> · calls {p.calls.join(", ")}</span>}
              {p.line_count != null && <span className="muted"> · {p.line_count} lines</span>}
            </div>
          ))}
        </div>

        {d.tables.length > 0 && (
          <div className="cap-sec">
            <div className="l">Data touched</div>
            {d.tables.map((t) => (
              <span key={t.table} className="pill tbl">{t.table} · {t.access.join("/")}</span>
            ))}
          </div>
        )}
        {d.copybooks.length > 0 && (
          <div className="cap-sec">
            <div className="l">Shared structures</div>
            {d.copybooks.map((c) => <span key={c} className="pill cpy">{c}</span>)}
          </div>
        )}
      </div>

      {/* ---- Business rules ---- */}
      <div className="panel" style={{ marginTop: 16 }}>
        <h3>Business rules <span className="tag" style={{ marginLeft: 8 }}>{d.business_rules.length} extracted · each cites a source line</span></h3>
        {d.business_rules.length === 0 && (
          <p className="muted">No IF / EVALUATE / COMPUTE rules found in the member programs.</p>
        )}
        {Object.entries(grouped).map(([prog, rules]) => (
          <div key={prog} className="req-rule-group">
            <div className="req-rule-prog">
              <span className="link" onClick={() => onOpenProgram(prog)}>{prog}</span>
              <span className="muted"> · {rules.length} rule{rules.length === 1 ? "" : "s"}</span>
            </div>
            {rules.map((r) => (
              <div key={r.id} className="req-rule">
                <div className="req-rule-head">
                  <span className="badge ok">{r.kind}</span>
                  <span className="req-rule-stmt">{r.statement}</span>
                </div>
                <code className="req-rule-cond">{r.condition}</code>
                <div className="req-rule-ev muted">
                  {r.source_evidence} · <span className="badge review">{r.validation_status} · {r.confidence}</span>
                </div>
              </div>
            ))}
          </div>
        ))}
      </div>
    </div>
  );
}
