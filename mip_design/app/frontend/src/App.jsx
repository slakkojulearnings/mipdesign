import React, { useEffect, useState } from "react";
import { api } from "./api.js";
import Dashboard from "./components/Dashboard.jsx";
import Programs from "./components/Programs.jsx";
import ProgramDetail from "./components/ProgramDetail.jsx";
import Jobs from "./components/Jobs.jsx";
import Lists from "./components/Lists.jsx";
import QueryConsole from "./components/QueryConsole.jsx";
import CallGraph from "./components/CallGraph.jsx";
import Capabilities from "./components/Capabilities.jsx";
import QaLog from "./components/QaLog.jsx";

const NAV = [
  ["dashboard", "Dashboard"],
  ["programs", "Programs"],
  ["capabilities", "Capabilities"],
  ["jobs", "Jobs"],
  ["graph", "Call Graph"],
  ["roots", "Root Programs"],
  ["deadcode", "Dead Code"],
  ["query", "Query Console"],
  ["log", "Q&A Log"],
];

export default function App() {
  const [view, setView] = useState("dashboard");
  const [selected, setSelected] = useState(null); // program id for detail
  const [health, setHealth] = useState(null);
  const [scanning, setScanning] = useState(false);
  const [error, setError] = useState(null);

  useEffect(() => { api.health().then(setHealth).catch((e) => setError(String(e))); }, []);

  const openProgram = (pid) => { setSelected(pid); setView("program"); };
  const go = (v) => { setSelected(null); setView(v); };

  const rescan = async () => {
    setScanning(true); setError(null);
    try { await api.scan(); setView((v) => v); window.dispatchEvent(new Event("mip-rescan")); }
    catch (e) { setError(String(e)); }
    finally { setScanning(false); }
  };

  return (
    <div className="app">
      <aside className="sidebar">
        <div className="brand">MIP<small>Mainframe Intelligence Platform</small></div>
        <nav className="nav">
          {NAV.map(([k, label]) => (
            <button key={k} className={view === k ? "active" : ""} onClick={() => go(k)}>{label}</button>
          ))}
        </nav>
        <div className="src-box">
          source<br />
          <code>{health?.source || "…"}</code>
          {health && !health.source_exists && <div style={{ color: "var(--red)" }}>not found</div>}
        </div>
      </aside>

      <main className="main">
        <div className="topbar">
          <div style={{ flex: 1 }} />
          <button className="btn secondary" onClick={rescan} disabled={scanning}>
            {scanning ? "Scanning…" : "↻ Rescan source"}
          </button>
        </div>
        {error && <div className="error">{error}</div>}

        {view === "dashboard" && <Dashboard onOpenProgram={openProgram} go={go} />}
        {view === "programs" && <Programs onOpenProgram={openProgram} />}
        {view === "program" && <ProgramDetail pid={selected} onOpenProgram={openProgram} back={() => go("programs")} />}
        {view === "jobs" && <Jobs onOpenProgram={openProgram} />}
        {view === "graph" && <CallGraph onOpenProgram={openProgram} />}
        {view === "capabilities" && <Capabilities onOpenProgram={openProgram} />}
        {view === "roots" && <Lists kind="roots" onOpenProgram={openProgram} />}
        {view === "deadcode" && <Lists kind="deadcode" onOpenProgram={openProgram} />}
        {view === "query" && <QueryConsole onOpenProgram={openProgram} />}
        {view === "log" && <QaLog />}
      </main>
    </div>
  );
}
