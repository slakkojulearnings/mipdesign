import React, { useEffect, useRef, useState } from "react";
import { useNavigate } from "react-router-dom";
import { api } from "../api.js";

// Where a result of a given kind navigates. Programs deep-link to the profile;
// the rest go to the relevant listing page (which is the most useful landing spot).
const DEST = {
  program: (id) => "/program/" + encodeURIComponent(id),
  job: () => "/jobs",
  capability: () => "/capabilities",
  table: () => "/graph",
  copybook: () => "/graph",
  transaction: () => "/graph",
};

export default function GlobalSearch() {
  const navigate = useNavigate();
  const [q, setQ] = useState("");
  const [open, setOpen] = useState(false);
  const [loading, setLoading] = useState(false);
  const [results, setResults] = useState(null); // null until first query
  const [err, setErr] = useState(null);
  const boxRef = useRef(null);

  // Debounced search.
  useEffect(() => {
    const term = q.trim();
    if (!term) { setResults(null); setLoading(false); setErr(null); return; }
    setLoading(true); setErr(null);
    const t = setTimeout(() => {
      api.search(term)
        .then((d) => { setResults(d.results || []); setLoading(false); })
        .catch((e) => { setErr(String(e)); setResults([]); setLoading(false); });
    }, 250);
    return () => clearTimeout(t);
  }, [q]);

  // Close dropdown on outside click.
  useEffect(() => {
    const onDoc = (e) => { if (boxRef.current && !boxRef.current.contains(e.target)) setOpen(false); };
    document.addEventListener("mousedown", onDoc);
    return () => document.removeEventListener("mousedown", onDoc);
  }, []);

  const pick = (r) => {
    const dest = (DEST[r.kind] || (() => "/"))(r.id);
    setOpen(false); setQ("");
    navigate(dest);
  };

  const showDropdown = open && q.trim().length > 0;

  return (
    <div className="search" ref={boxRef}>
      <input
        className="search-input"
        value={q}
        placeholder="Search programs, jobs, tables…"
        onChange={(e) => { setQ(e.target.value); setOpen(true); }}
        onFocus={() => setOpen(true)}
        onKeyDown={(e) => {
          if (e.key === "Escape") setOpen(false);
          if (e.key === "Enter" && results && results.length) pick(results[0]);
        }}
      />
      {showDropdown && (
        <div className="search-drop">
          {loading && <div className="search-msg">Searching…</div>}
          {!loading && err && <div className="search-msg error">{err}</div>}
          {!loading && !err && results && results.length === 0 && (
            <div className="search-msg">No matches for “{q.trim()}”.</div>
          )}
          {!loading && !err && results && results.map((r, i) => (
            <div key={r.kind + ":" + r.id + ":" + i} className="search-item" onMouseDown={() => pick(r)}>
              <span className="badge ok search-kind">{r.kind}</span>
              <span className="search-id">{r.id}</span>
              {r.detail && <span className="muted search-detail">{r.detail}</span>}
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
