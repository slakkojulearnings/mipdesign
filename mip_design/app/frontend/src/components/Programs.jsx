import React from "react";
import { api } from "../api.js";
import { useData } from "../hooks.js";

export default function Programs({ onOpenProgram }) {
  const { data, err, loading } = useData(() => api.programs());
  if (loading) return <div className="loading">Loading…</div>;
  if (err) return <div className="error">{err}</div>;
  return (
    <div>
      <h1 className="page-title">Programs</h1>
      <p className="page-sub">{data.length} programs discovered. Click a row for dependencies, callers, and source.</p>
      <table>
        <thead>
          <tr><th>Program</th><th>Lang</th><th>LOC</th><th>Calls →</th><th>← Called by</th><th>Flags</th></tr>
        </thead>
        <tbody>
          {data.map((p) => (
            <tr key={p.program_id} className="clickable" onClick={() => onOpenProgram(p.program_id)}>
              <td><strong>{p.program_id}</strong></td>
              <td className="tag">{p.language}</td>
              <td>{p.line_count}</td>
              <td>{p.calls_out}</td>
              <td>{p.called_by}</td>
              <td>
                {p.is_root && <span className="badge root">root</span>}{" "}
                {p.is_dead && <span className="badge dead">dead</span>}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
