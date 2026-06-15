import React, { useEffect, useRef, useState } from "react";
import { api } from "../api.js";

const ITEMS = [
  ["Export JSON", "json", undefined],
  ["CSV — programs", "csv", "programs"],
  ["CSV — edges", "csv", "edges"],
  ["GraphML", "graphml", undefined],
];

// Top-bar export dropdown + a "Copy link" button. Each export item is a real
// <a download> pointing at the backend export endpoint.
export default function ExportMenu({ onCopied }) {
  const [open, setOpen] = useState(false);
  const ref = useRef(null);

  useEffect(() => {
    if (!open) return;
    const onDoc = (e) => { if (ref.current && !ref.current.contains(e.target)) setOpen(false); };
    document.addEventListener("mousedown", onDoc);
    return () => document.removeEventListener("mousedown", onDoc);
  }, [open]);

  const copyLink = async () => {
    try { await navigator.clipboard.writeText(window.location.href); onCopied && onCopied(true); }
    catch { onCopied && onCopied(false); }
  };

  return (
    <div className="export-menu" ref={ref}>
      <button className="btn secondary" onClick={copyLink}>Copy link</button>
      <div className="export-dd">
        <button className="btn secondary" onClick={() => setOpen((v) => !v)}>Export ▾</button>
        {open && (
          <div className="export-drop">
            {ITEMS.map(([label, fmt, kind]) => (
              <a key={label} className="export-item" href={api.exportUrl(fmt, kind)}
                 download onClick={() => setOpen(false)}>{label}</a>
            ))}
          </div>
        )}
      </div>
    </div>
  );
}
