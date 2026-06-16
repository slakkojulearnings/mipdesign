import React, { useState } from "react";
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

  // ---- Developer detail (re-implementation spec) ----
  const withSpec = d.programs.filter((p) => p.spec);
  if (withSpec.length) {
    L.push("## Developer detail (re-implementation spec)");
    L.push("");
    withSpec.forEach((p) => {
      const s = p.spec;
      L.push(`### ${p.program}`);
      L.push("");
      L.push("**Data structures**");
      s.data_structures.forEach((g) => {
        L.push(`- _${g.section}_`);
        g.items.forEach((it) => L.push(`  - ${String(it.level).padStart(2, "0")} \`${it.name}\`${it.pic ? ` PIC ${it.pic}` : ""}`));
      });
      L.push("");
      L.push("**Procedure outline**");
      s.procedure_outline.forEach((o) => L.push(`- \`${o.paragraph}\`: ${o.steps.map((x) => x.verb).join(" → ") || "—"}`));
      L.push("");
      L.push(`**I/O** — reads: ${s.io.reads.join(", ") || "—"}; writes: ${s.io.writes.join(", ") || "—"}; copybooks: ${s.io.copybooks.join(", ") || "—"}; calls: ${s.io.calls.map((c) => c.target).join(", ") || "—"}`);
      L.push("");
      if (s.rules.length) {
        L.push("**Rules with code**");
        s.rules.forEach((r) => {
          L.push(`- ${r.statement} _(${r.source_evidence})_`);
          L.push("  ```cobol");
          r.snippet.forEach((ln) => L.push(`  ${String(ln.line).padStart(4)}  ${ln.text}`));
          L.push("  ```");
          const tf = r.typed_fields.filter((f) => f.pic).map((f) => `${f.name} PIC ${f.pic}`);
          if (tf.length) L.push(`  fields: ${tf.join(", ")}`);
        });
        L.push("");
      }
    });
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
  const [open, setOpen] = useState({});
  if (loading) return <div className="loading">Loading…</div>;
  if (err) return <div className="error">{err}</div>;

  const grouped = groupRules(d.business_rules);
  const specs = d.programs.filter((p) => p.spec);
  const toggle = (k) => setOpen((o) => ({ ...o, [k]: !o[k] }));

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

      {/* ---- Developer detail (re-implementation spec) ---- */}
      {specs.length > 0 && (
        <div className="panel" style={{ marginTop: 16 }}>
          <h3>Developer detail <span className="tag" style={{ marginLeft: 8 }}>re-implementation spec · source-cited</span></h3>
          <p className="muted" style={{ marginTop: 0, fontSize: 12 }}>
            Data layouts, procedure pseudocode, the I/O contract, and each rule with its real
            code snippet + typed fields — enough to faithfully re-implement each program.
          </p>
          {specs.map((p) => {
            const s = p.spec;
            const isOpen = !!open[p.program];
            return (
              <div key={p.program} className="spec-block">
                <button className="spec-toggle" onClick={() => toggle(p.program)} aria-expanded={isOpen}>
                  <span className="spec-caret">{isOpen ? "▾" : "▸"}</span>
                  <span className="link">{p.program}</span>
                  <span className="muted"> — {p.role}</span>
                  <span className="muted spec-meta"> · {s.rules.length} rules · complexity {s.complexity}</span>
                </button>
                {isOpen && (
                  <div className="spec-body">
                    <div className="spec-sec">
                      <div className="l">Data structures</div>
                      {s.data_structures.map((g) => (
                        <div key={g.section} className="spec-data">
                          <div className="spec-section-name">{g.section}</div>
                          {g.items.map((it, i) => (
                            <div key={i} className="spec-di" style={{ paddingLeft: Math.min(it.level, 12) * 2 }}>
                              <span className="spec-lvl">{String(it.level).padStart(2, "0")}</span>
                              <span className="spec-name">{it.name}</span>
                              {it.pic && <span className="spec-pic">PIC {it.pic}</span>}
                            </div>
                          ))}
                        </div>
                      ))}
                    </div>

                    <div className="spec-sec">
                      <div className="l">Procedure outline (pseudocode)</div>
                      {s.procedure_outline.map((o) => (
                        <div key={o.paragraph} className="spec-para">
                          <span className="spec-para-name">{o.paragraph}</span>
                          <span className="spec-steps">{o.steps.map((x) => x.verb).join(" → ") || "—"}</span>
                        </div>
                      ))}
                    </div>

                    <div className="spec-sec">
                      <div className="l">I/O contract</div>
                      <div className="spec-io">
                        <span>reads: {s.io.reads.join(", ") || "—"}</span>
                        <span>writes: {s.io.writes.join(", ") || "—"}</span>
                        <span>copybooks: {s.io.copybooks.join(", ") || "—"}</span>
                        <span>calls: {s.io.calls.map((c) => c.target).join(", ") || "—"}</span>
                      </div>
                    </div>

                    {s.rules.length > 0 && (
                      <div className="spec-sec">
                        <div className="l">Rules with code</div>
                        {s.rules.map((r) => (
                          <div key={r.id} className="spec-rule">
                            <div className="spec-rule-stmt">{r.statement}</div>
                            <pre className="spec-snippet">{r.snippet.map((ln) => `${String(ln.line).padStart(4)}  ${ln.text}`).join("\n")}</pre>
                            {r.typed_fields.filter((f) => f.pic).length > 0 && (
                              <div className="spec-fields">
                                {r.typed_fields.filter((f) => f.pic).map((f) => (
                                  <span key={f.name} className="pill">{f.name} · PIC {f.pic}</span>
                                ))}
                              </div>
                            )}
                          </div>
                        ))}
                      </div>
                    )}
                  </div>
                )}
              </div>
            );
          })}
        </div>
      )}
    </div>
  );
}
