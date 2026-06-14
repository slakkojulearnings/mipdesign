import React from "react";

// AST/structure outline: divisions + procedure paragraphs, a statement-mix bar,
// and a cyclomatic-complexity gauge. (v0.1 structural view — see ARCHITECTURE.md.)
const MIX = [
  ["CALL", "var(--green)"],
  ["PERFORM", "var(--accent)"],
  ["IF", "var(--amber)"],
  ["COPY", "var(--purple)"],
  ["EXEC_SQL", "var(--red)"],
];

export default function Structure({ structure }) {
  if (!structure) return <div className="muted">No source structure available.</div>;
  const c = structure.counts || {};
  const total = MIX.reduce((s, [k]) => s + (c[k] || 0), 0);
  const cx = structure.complexity || 0;
  const cls = cx <= 4 ? "low" : cx <= 10 ? "med" : "high";

  return (
    <div>
      <div style={{ display: "flex", gap: 24, alignItems: "center", marginBottom: 12 }}>
        <div className={`gauge ${cls}`}>
          <span className="num">{cx}</span>
          <span className="muted">cyclomatic (proxy)</span>
        </div>
        <div className="muted" style={{ fontSize: 12 }}>
          {structure.paragraphs?.length || 0} paragraphs · {structure.divisions?.length || 0} divisions
        </div>
      </div>

      {total > 0 && (
        <>
          <div className="bar">
            {MIX.map(([k, col]) => c[k] ? <i key={k} style={{ width: `${(c[k] / total) * 100}%`, background: col }} /> : null)}
          </div>
          <div className="legend-mini">
            {MIX.map(([k, col]) => c[k] ? <span key={k}><i className="dot" style={{ background: col }} /> {k} {c[k]}</span> : null)}
          </div>
        </>
      )}

      <div className="ast" style={{ marginTop: 12 }}>
        {(structure.divisions || []).map((d) => (
          <div key={d}>
            <span className="div">▸ {d} DIVISION</span>
            {d === "PROCEDURE" && (structure.paragraphs || []).map((p) => (
              <div key={p} className="para">└ {p}</div>
            ))}
          </div>
        ))}
      </div>
    </div>
  );
}
