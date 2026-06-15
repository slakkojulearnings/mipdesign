import React, { useEffect, useState } from "react";
import {
  HashRouter,
  Routes,
  Route,
  NavLink,
  Navigate,
  useNavigate,
  useParams,
} from "react-router-dom";
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
import GlobalSearch from "./components/GlobalSearch.jsx";

const NAV = [
  ["/", "Dashboard"],
  ["/programs", "Programs"],
  ["/capabilities", "Capabilities"],
  ["/jobs", "Jobs"],
  ["/graph", "Call Graph"],
  ["/roots", "Root Programs"],
  ["/deadcode", "Dead Code"],
  ["/query", "Query Console"],
  ["/log", "Q&A Log"],
];

// Navigation helpers shared with the existing components, which expect
// `onOpenProgram(pid)` and `go(view)` callbacks. We adapt them to router routes.
function useNav() {
  const navigate = useNavigate();
  const openProgram = (pid) => navigate("/program/" + encodeURIComponent(pid));
  // Back-compat: old screens called go("graph"), go("roots"), etc.
  const go = (v) => navigate(v === "dashboard" ? "/" : "/" + v);
  return { openProgram, go };
}

// Small wrappers that inject the router-backed nav callbacks into each screen.
function DashboardRoute() {
  const { openProgram, go } = useNav();
  return <Dashboard onOpenProgram={openProgram} go={go} />;
}
function ProgramsRoute() {
  const { openProgram } = useNav();
  return <Programs onOpenProgram={openProgram} />;
}
function ProgramDetailRoute() {
  const { pid } = useParams();
  const { openProgram, go } = useNav();
  return <ProgramDetail pid={pid} onOpenProgram={openProgram} back={() => go("programs")} />;
}
function JobsRoute() {
  const { openProgram } = useNav();
  return <Jobs onOpenProgram={openProgram} />;
}
function CallGraphRoute() {
  const { openProgram } = useNav();
  return <CallGraph onOpenProgram={openProgram} />;
}
function CapabilitiesRoute() {
  const { openProgram } = useNav();
  return <Capabilities onOpenProgram={openProgram} />;
}
function RootsRoute() {
  const { openProgram } = useNav();
  return <Lists kind="roots" onOpenProgram={openProgram} />;
}
function DeadcodeRoute() {
  const { openProgram } = useNav();
  return <Lists kind="deadcode" onOpenProgram={openProgram} />;
}
function QueryRoute() {
  const { openProgram } = useNav();
  return <QueryConsole onOpenProgram={openProgram} />;
}

function Layout() {
  const [health, setHealth] = useState(null);
  const [scanning, setScanning] = useState(false);
  const [error, setError] = useState(null);

  useEffect(() => { api.health().then(setHealth).catch((e) => setError(String(e))); }, []);

  const rescan = async () => {
    setScanning(true); setError(null);
    try { await api.scan(); window.dispatchEvent(new Event("mip-rescan")); }
    catch (e) { setError(String(e)); }
    finally { setScanning(false); }
  };

  return (
    <div className="app">
      <aside className="sidebar">
        <div className="brand">MIP<small>Mainframe Intelligence Platform</small></div>
        <nav className="nav">
          {NAV.map(([path, label]) => (
            <NavLink key={path} to={path} end={path === "/"}
                     className={({ isActive }) => (isActive ? "active" : "")}>{label}</NavLink>
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
          <GlobalSearch />
          <div style={{ flex: 1 }} />
          <button className="btn secondary" onClick={rescan} disabled={scanning}>
            {scanning ? "Scanning…" : "↻ Rescan source"}
          </button>
        </div>
        {error && <div className="error">{error}</div>}

        <Routes>
          <Route path="/" element={<DashboardRoute />} />
          <Route path="/programs" element={<ProgramsRoute />} />
          <Route path="/program/:pid" element={<ProgramDetailRoute />} />
          <Route path="/capabilities" element={<CapabilitiesRoute />} />
          <Route path="/jobs" element={<JobsRoute />} />
          <Route path="/graph" element={<CallGraphRoute />} />
          <Route path="/roots" element={<RootsRoute />} />
          <Route path="/deadcode" element={<DeadcodeRoute />} />
          <Route path="/query" element={<QueryRoute />} />
          <Route path="/log" element={<QaLog />} />
          <Route path="*" element={<Navigate to="/" replace />} />
        </Routes>
      </main>
    </div>
  );
}

export default function App() {
  return (
    <HashRouter>
      <Layout />
    </HashRouter>
  );
}
