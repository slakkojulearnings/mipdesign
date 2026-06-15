import React, { useMemo, useState } from "react";
import { api } from "../api.js";
import { useData } from "../hooks.js";
import "./Programs.css";

const COLUMNS = [
  { key: "program_id", label: "Program", sortable: true },
  { key: "language", label: "Lang", sortable: false },
  { key: "line_count", label: "LOC", sortable: true },
  { key: "calls_out", label: "Calls →", sortable: true },
  { key: "called_by", label: "← Called by", sortable: true },
  { key: "flags", label: "Flags", sortable: false },
];

export default function Programs({ onOpenProgram }) {
  const { data, err, loading } = useData(() => api.programs());
  const [search, setSearch] = useState("");
  const [sort, setSort] = useState({ key: "program_id", dir: "asc" });
  const [rootsOnly, setRootsOnly] = useState(false);
  const [deadOnly, setDeadOnly] = useState(false);
  const [lang, setLang] = useState("all");

  // Language options derived from the data (stable hook order — runs on null too).
  const languages = useMemo(() => {
    const s = new Set();
    (data || []).forEach((p) => p.language && s.add(p.language));
    return Array.from(s).sort();
  }, [data]);

  const rows = useMemo(() => {
    let r = data || [];
    const q = search.trim().toLowerCase();
    if (q) r = r.filter((p) => String(p.program_id).toLowerCase().includes(q));
    if (rootsOnly) r = r.filter((p) => p.is_root);
    if (deadOnly) r = r.filter((p) => p.is_dead);
    if (lang !== "all") r = r.filter((p) => p.language === lang);

    const { key, dir } = sort;
    const mul = dir === "asc" ? 1 : -1;
    // Copy before sort so we never mutate the cached array.
    r = [...r].sort((a, b) => {
      const av = a[key], bv = b[key];
      if (typeof av === "number" && typeof bv === "number") return (av - bv) * mul;
      return String(av).localeCompare(String(bv)) * mul;
    });
    return r;
  }, [data, search, rootsOnly, deadOnly, lang, sort]);

  if (loading) return <div className="loading">Loading…</div>;
  if (err) return <div className="error">{err}</div>;

  const total = data.length;
  const toggleSort = (key) =>
    setSort((s) => (s.key === key ? { key, dir: s.dir === "asc" ? "desc" : "asc" } : { key, dir: "asc" }));

  return (
    <div>
      <h1 className="page-title">Programs</h1>
      <p className="page-sub">{total} programs discovered. Click a row for dependencies, callers, and source.</p>

      <div className="prog-controls">
        <div className="prog-search">
          <input
            type="text"
            placeholder="Search by program id…"
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            aria-label="Search programs by id"
          />
          {search && (
            <button className="clear" onClick={() => setSearch("")} aria-label="Clear search">×</button>
          )}
        </div>

        <div className="prog-facets">
          <button
            className={`facet-chip${rootsOnly ? " on" : ""}`}
            aria-pressed={rootsOnly}
            onClick={() => setRootsOnly((v) => !v)}
          >Roots only</button>
          <button
            className={`facet-chip${deadOnly ? " on" : ""}`}
            aria-pressed={deadOnly}
            onClick={() => setDeadOnly((v) => !v)}
          >Dead only</button>
          <select
            className="prog-lang"
            value={lang}
            onChange={(e) => setLang(e.target.value)}
            aria-label="Filter by language"
          >
            <option value="all">All languages</option>
            {languages.map((l) => <option key={l} value={l}>{l}</option>)}
          </select>
        </div>

        <span className="prog-count">{rows.length} of {total} programs</span>
      </div>

      <table>
        <thead>
          <tr>
            {COLUMNS.map((c) => {
              const active = sort.key === c.key;
              return c.sortable ? (
                <th
                  key={c.key}
                  className={`sortable${active ? " active" : ""}`}
                  onClick={() => toggleSort(c.key)}
                  aria-sort={active ? (sort.dir === "asc" ? "ascending" : "descending") : "none"}
                >
                  {c.label}
                  <span className="arrow">{active ? (sort.dir === "asc" ? "▲" : "▼") : "↕"}</span>
                </th>
              ) : (
                <th key={c.key}>{c.label}</th>
              );
            })}
          </tr>
        </thead>
        <tbody>
          {rows.map((p) => (
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

      {rows.length === 0 && (
        <div className="prog-empty">
          No programs match the current filters.
          {(search || rootsOnly || deadOnly || lang !== "all") && (
            <>
              {" "}
              <span
                className="link"
                onClick={() => { setSearch(""); setRootsOnly(false); setDeadOnly(false); setLang("all"); }}
              >Clear filters</span>
            </>
          )}
        </div>
      )}
    </div>
  );
}
