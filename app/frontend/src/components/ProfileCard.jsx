import React from "react";

// Compact 360° profile: capability, the jobs that ultimately run it, grouped
// dependencies, callers. Shared by the Query Console and the graph detail panel.
const GROUPS = [["CALLS", "Calls"], ["USES", "Copybooks"], ["READS", "Reads"], ["WRITES", "Writes"]];

export default function ProfileCard({ profile, onOpenProgram }) {
  if (!profile) return null;
  const p = profile;
  const grouped = (rel) => p.dependencies.filter((d) => d.rel_type === rel);

  return (
    <div>
      <div className="kv">
        {p.capability && <div><span>Capability</span><span className="badge ok">{p.capability}</span></div>}
        <div><span>Language</span>{p.language || "—"}</div>
        <div><span>Lines</span>{p.line_count ?? "—"}</div>
        <div><span>Fan-out / Fan-in</span>{p.dependencies.length} / {p.callers.length}</div>
      </div>

      {p.executing_jobs?.length > 0 && (
        <div className="cap-sec">
          <div className="l">Run by jobs (transitive)</div>
          {p.executing_jobs.map((j) => <span key={j} className="pill">{j}</span>)}
        </div>
      )}

      {GROUPS.map(([rel, label]) => {
        const items = grouped(rel);
        if (!items.length) return null;
        return (
          <div className="cap-sec" key={rel}>
            <div className="l">{label}</div>
            {items.map((x, i) => (
              <span key={i}
                    className={`pill ${x.target_type === "program" ? "click" : x.target_type === "copybook" ? "cpy" : "tbl"}`}
                    onClick={() => x.target_type === "program" && onOpenProgram?.(x.target_id)}>
                {x.target_id}{x.validation_status !== "confirmed" ? " ⚠" : ""}
              </span>
            ))}
          </div>
        );
      })}

      {p.callers?.length > 0 && (
        <div className="cap-sec">
          <div className="l">Called / executed by</div>
          {p.callers.map((c, i) => (
            <span key={i} className="pill click" onClick={() => onOpenProgram?.(c.source_id)}>{c.source_id}</span>
          ))}
        </div>
      )}
    </div>
  );
}
