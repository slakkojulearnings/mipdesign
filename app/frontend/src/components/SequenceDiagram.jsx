import React, { useEffect, useRef, useState } from "react";
import mermaid from "mermaid";

mermaid.initialize({ startOnLoad: false, theme: "neutral", securityLevel: "loose" });

let _seq = 0;

// Renders a mermaid string to SVG. On any render error, falls back to showing
// the mermaid source in <pre class="code"> with a Copy button so nothing is lost.
export default function SequenceDiagram({ code }) {
  const [svg, setSvg] = useState(null);
  const [failed, setFailed] = useState(false);
  const [copied, setCopied] = useState(false);
  const idRef = useRef("mmd-" + (++_seq));

  useEffect(() => {
    let alive = true;
    setSvg(null);
    setFailed(false);
    if (!code) return;
    mermaid
      .render(idRef.current, code)
      .then((out) => { if (alive) setSvg(out.svg); })
      .catch(() => { if (alive) setFailed(true); });
    return () => { alive = false; };
  }, [code]);

  const copy = async () => {
    try { await navigator.clipboard.writeText(code || ""); setCopied(true); setTimeout(() => setCopied(false), 1500); }
    catch { /* clipboard blocked — source is still visible to copy by hand */ }
  };

  if (failed)
    return (
      <div>
        <div className="muted" style={{ marginBottom: 8 }}>
          Could not render the diagram — showing the source.
          <button className="btn secondary" style={{ marginLeft: 8 }} onClick={copy}>
            {copied ? "Copied" : "Copy"}
          </button>
        </div>
        <pre className="code">{code}</pre>
      </div>
    );

  if (!svg) return <div className="loading">Rendering diagram…</div>;

  return <div className="mermaid-svg" dangerouslySetInnerHTML={{ __html: svg }} />;
}
