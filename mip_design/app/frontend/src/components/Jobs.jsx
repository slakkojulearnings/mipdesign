import React from "react";
import { api } from "../api.js";
import { useData } from "../hooks.js";

export default function Jobs({ onOpenProgram }) {
  const { data, err, loading } = useData(() => api.jobs());
  if (loading) return <div className="loading">Loading…</div>;
  if (err) return <div className="error">{err}</div>;
  return (
    <div>
      <h1 className="page-title">Jobs</h1>
      <p className="page-sub">{data.length} batch jobs. Each step's <code>EXEC PGM=</code> is the entry into the program graph.</p>
      {data.map((j) => (
        <div key={j.job_id} className="panel">
          <h3>{j.job_id}</h3>
          <table>
            <thead><tr><th>Step</th><th>Executes program</th></tr></thead>
            <tbody>
              {j.steps.map((s, i) => (
                <tr key={i}>
                  <td className="rel">{s.step}</td>
                  <td>{s.program
                    ? <span className="link" onClick={() => onOpenProgram(s.program)}>{s.program}</span>
                    : <span className="muted">—</span>}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      ))}
    </div>
  );
}
