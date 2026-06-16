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
import CapabilityRequirements from "./components/CapabilityRequirements.jsx";
import QaLog from "./components/QaLog.jsx";
import GlobalSearch from "./components/GlobalSearch.jsx";
import ExportMenu from "./components/ExportMenu.jsx";
import Toast from "./components/Toast.jsx";

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
function CapabilityRequirementsRoute() {
  const { name } = useParams();
  const { openProgram, go } = useNav();
  return <CapabilityRequirements name={name} onOpenProgram={openProgram} back={() => go("capabilities")} />;
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
  const [toasts, setToasts] = useState([]);

  useEffect(() => { api.health().then(setHealth).catch((e) => setError(String(e))); }, []);

  const dismissToast = (id) => setToasts((ts) => ts.filter((t) => t.id !== id));
  const pushToast = (t) => {
    const id = Date.now() + Math.random();
    setToasts((ts) => [...ts, { id, timeout: 4000, ...t }]);
    return id;
  };

  // Summarize a scan response for the success toast (best-effort over its shape).
  const scanSummary = (r) => {
    const s = r && r.summary ? r.summary : r || {};
    const parts = [];
    if (s.programs != null) parts.push(`${s.programs} programs`);
    if (s.jobs != null) parts.push(`${s.jobs} jobs`);
    if (s.edges != null) parts.push(`${s.edges} relationships`);
    return parts.length ? parts.join(" · ") : "Scan complete.";
  };

  const rescan = async () => {
    setScanning(true); setError(null);
    const pending = pushToast({ title: "Scanning source…", message: "Re-parsing the estate.", timeout: 0 });
    try {
      const r = await api.scan();
      window.dispatchEvent(new Event("mip-rescan"));
      dismissToast(pending);
      pushToast({ kind: "green", title: "Scan complete", message: scanSummary(r) });
    } catch (e) {
      dismissToast(pending);
      setError(String(e));
      pushToast({ kind: "red", title: "Scan failed", message: String(e), timeout: 6000 });
    } finally {
      setScanning(false);
    }
  };

  // Switch the COBOL parser backend (default | advanced) and re-parse the estate.
  const switchParser = async (mode) => {
    if (!mode || mode === health?.parser?.requested) return;
    setScanning(true); setError(null);
    const pending = pushToast({ title: `Switching to ${mode} parser…`, message: "Re-parsing the estate.", timeout: 0 });
    try {
      const r = await api.setParser(mode);
      setHealth((h) => ({ ...h, parser: r.parser }));
      window.dispatchEvent(new Event("mip-rescan"));
      dismissToast(pending);
      if (mode === "advanced" && r.parser.effective !== "advanced") {
        pushToast({ kind: "amber", title: "Advanced parser unavailable",
          message: "The ANTLR backend isn't installed/built — staying on default. Install the 'advanced' extra and build the grammar.",
          timeout: 7000 });
      } else {
        pushToast({ kind: "green", title: `Parser: ${r.parser.effective}`, message: "Estate re-parsed with the new backend." });
      }
    } catch (e) {
      dismissToast(pending); setError(String(e));
      pushToast({ kind: "red", title: "Parser switch failed", message: String(e), timeout: 6000 });
    } finally {
      setScanning(false);
    }
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
          {health?.parser && (
            <div className="parser-ctl" title="Active COBOL parser backend">
              <span className="parser-lbl">parser</span>
              <select
                value={health.parser.requested}
                onChange={(e) => switchParser(e.target.value)}
                disabled={scanning}
                aria-label="COBOL parser backend"
              >
                <option value="default">default (grammar)</option>
                <option value="advanced" disabled={!health.parser.advanced_available}>
                  advanced (ANTLR){health.parser.advanced_available ? "" : " — not installed"}
                </option>
              </select>
              <span className={`parser-eff ${health.parser.effective}`}>{health.parser.effective}</span>
            </div>
          )}
          <ExportMenu />
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
          <Route path="/capability/:name" element={<CapabilityRequirementsRoute />} />
          <Route path="/jobs" element={<JobsRoute />} />
          <Route path="/graph" element={<CallGraphRoute />} />
          <Route path="/roots" element={<RootsRoute />} />
          <Route path="/deadcode" element={<DeadcodeRoute />} />
          <Route path="/query" element={<QueryRoute />} />
          <Route path="/log" element={<QaLog />} />
          <Route path="*" element={<Navigate to="/" replace />} />
        </Routes>
      </main>
      <Toast toasts={toasts} onDismiss={dismissToast} />
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
