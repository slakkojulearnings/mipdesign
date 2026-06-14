import React from "react";

// Renders a reasoning trace: thought process + evidence + reason. Used inline in the
// Query Console and in the Q&A Log.
export default function Trace({ trace }) {
  if (!trace) return null;
  return (
    <div>
      <div className="muted" style={{ fontSize: 12, marginBottom: 4 }}>Thought process</div>
      <ol className="rel" style={{ margin: "0 0 12px 18px" }}>
        {(trace.thought_process || []).map((s, i) => <li key={i} style={{ marginBottom: 2 }}>{s}</li>)}
      </ol>

      {trace.evidence?.length > 0 && (
        <>
          <div className="muted" style={{ fontSize: 12, marginBottom: 4 }}>Evidence</div>
          {trace.evidence.map((e, i) => (
            <div key={i} className="rel" style={{ padding: "1px 0" }}>
              <span className="t">{e.source_id} {e.rel_type} {e.target_id}</span>{" "}
              <span className="tag">{e.source_evidence}</span>{" "}
              {e.validation_status !== "confirmed" &&
                <span className="badge review">{e.validation_status} · {e.confidence}</span>}
            </div>
          ))}
        </>
      )}

      <div style={{ marginTop: 10 }}>
        <div className="muted" style={{ fontSize: 12 }}>Reason</div>
        <div>{trace.reason}</div>
      </div>
    </div>
  );
}
