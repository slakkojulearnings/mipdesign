import React, { useEffect, useMemo, useState } from "react";
import { createRoot } from "react-dom/client";
import {
  Activity,
  AlertCircle,
  Boxes,
  Braces,
  ClipboardCheck,
  Database,
  Download,
  FileJson,
  Filter,
  GitBranch,
  Layers3,
  Network,
  RefreshCw,
  Route,
  Search,
  ServerCog,
  ShieldCheck,
  Sparkles,
  Table2,
  Workflow,
} from "lucide-react";
import { api } from "./api";
import "./styles.css";

const RELATIONSHIP_PRESETS = [
  { label: "All", value: "" },
  { label: "Control", value: "CALLS,DYNAMIC_CALL,EXECUTES,STARTS_PROGRAM,STARTS_TRANSACTION" },
  { label: "Data", value: "READS_TABLE,WRITES_TABLE,READS_FILE,WRITES_FILE,READS_DATASET,WRITES_DATASET" },
];

const HEATMAP_PRESETS = [
  { label: "Programs to tables", left: "PROGRAM", right: "TABLE", relationship: "READS_TABLE" },
  { label: "Programs to files", left: "PROGRAM", right: "FILE", relationship: "READS_FILE" },
  { label: "Jobs to programs", left: "JOB", right: "PROGRAM", relationship: "EXECUTES" },
];

function App() {
  const [stats, setStats] = useState(null);
  const [validation, setValidation] = useState(null);
  const [roots, setRoots] = useState([]);
  const [clusters, setClusters] = useState([]);
  const [domainContexts, setDomainContexts] = useState([]);
  const [serviceCandidates, setServiceCandidates] = useState([]);
  const [roadmap, setRoadmap] = useState([]);
  const [backendInsights, setBackendInsights] = useState([]);
  const [graph, setGraph] = useState(null);
  const [selected, setSelected] = useState(null);
  const [query, setQuery] = useState("");
  const [results, setResults] = useState([]);
  const [depth, setDepth] = useState(2);
  const [limit, setLimit] = useState(350);
  const [confidenceMin, setConfidenceMin] = useState(0);
  const [relationshipTypes, setRelationshipTypes] = useState("");
  const [heatmapPreset, setHeatmapPreset] = useState(HEATMAP_PRESETS[0]);
  const [heatmap, setHeatmap] = useState(null);
  const [focusAsset, setFocusAsset] = useState("");
  const [callView, setCallView] = useState(null);
  const [dependencyView, setDependencyView] = useState(null);
  const [filesView, setFilesView] = useState(null);
  const [astView, setAstView] = useState(null);
  const [workbenchDirection, setWorkbenchDirection] = useState("both");
  const [activeTab, setActiveTab] = useState("dashboard");
  const [message, setMessage] = useState("");
  const [busy, setBusy] = useState(false);

  const run = stats?.run;
  const assetTypes = Object.entries(stats?.assets || {}).map(([asset_type, count]) => ({ asset_type, count }));
  const relationshipCounts = Object.entries(stats?.relationships || {}).map(([relationship_type, count]) => ({
    relationship_type,
    count,
  }));

  const loadHome = async () => {
    setBusy(true);
    try {
      const [s, r, c, h, v, d, svc, road, insightPayload] = await Promise.all([
        api.stats(),
        api.roots({ limit: 100 }),
        api.clusters({ limit: 100 }),
        api.heatmap(heatmapPreset),
        api.validate(),
        api.domainContexts({ limit: 50 }),
        api.serviceCandidates({ limit: 50 }),
        api.modernizationRoadmap({ limit: 50 }),
        api.insights({ limit: 50 }),
      ]);
      setStats(s);
      setRoots(r.roots || []);
      setClusters(c.clusters || []);
      setHeatmap(h);
      setValidation(v);
      setDomainContexts(d.contexts || []);
      setServiceCandidates(svc.service_candidates || []);
      setRoadmap(road.work_packages || []);
      setBackendInsights(insightPayload.insights || []);
      setFocusAsset((current) => current || r.roots?.[0]?.technical_name || r.roots?.[0]?.asset_id || "");
      setMessage("");
    } catch (error) {
      setMessage("No run loaded. Use Demo to seed a graph or start the backend with an analyzed database.");
    } finally {
      setBusy(false);
    }
  };

  useEffect(() => {
    loadHome();
  }, []);

  const openGraph = async (assetId, overrides = {}) => {
    setBusy(true);
    try {
      const nextDepth = overrides.depth ?? depth;
      const nextLimit = overrides.limit ?? limit;
      const nextConfidence = overrides.confidenceMin ?? confidenceMin;
      const nextRelationships = overrides.relationshipTypes ?? relationshipTypes;
      const slice = await api.graphSlice({
        rootAssetId: assetId,
        depth: nextDepth,
        limit: nextLimit,
        confidenceMin: nextConfidence,
        relationshipTypes: nextRelationships,
      });
      setGraph(slice);
      setFocusAsset(assetId);
      setDepth(nextDepth);
      setLimit(nextLimit);
      setConfidenceMin(nextConfidence);
      setRelationshipTypes(nextRelationships);
      setActiveTab("graph");
      setMessage(slice.truncated ? "Slice is bounded and truncated by the selected limit." : "");
    } catch (error) {
      setMessage(error.message || "Could not load graph slice.");
    } finally {
      setBusy(false);
    }
  };

  const reloadGraph = (overrides = {}) => {
    if (graph?.root_asset_id) openGraph(graph.root_asset_id, overrides);
  };

  const openNode = async (id) => {
    setSelected({ kind: "loading" });
    setSelected({ kind: "node", payload: await api.node(id, graph?.run_id) });
  };

  const openEdge = async (id) => {
    setSelected({ kind: "loading" });
    setSelected({ kind: "edge", payload: await api.edge(id, graph?.run_id) });
  };

  const runSearch = async (event) => {
    event.preventDefault();
    if (!query.trim()) return;
    setBusy(true);
    try {
      const payload = await api.search(query.trim(), { limit: 50, runId: run?.run_id });
      setResults(payload.results || []);
      setActiveTab("search");
    } catch (error) {
      setMessage(error.message || "Search failed.");
    } finally {
      setBusy(false);
    }
  };

  const loadHeatmap = async (preset = heatmapPreset) => {
    setBusy(true);
    try {
      setHeatmapPreset(preset);
      setHeatmap(await api.heatmap({ ...preset, runId: run?.run_id }));
      setActiveTab("matrix");
    } catch (error) {
      setMessage(error.message || "Heatmap failed.");
    } finally {
      setBusy(false);
    }
  };

  const loadWorkbench = async (asset = focusAsset, direction = workbenchDirection) => {
    const selectedAsset = asset || graph?.root_asset_id || roots[0]?.technical_name || roots[0]?.asset_id;
    if (!selectedAsset) {
      setMessage("Select or search an asset first.");
      return;
    }
    setBusy(true);
    try {
      setFocusAsset(selectedAsset);
      setWorkbenchDirection(direction);
      const [calls, deps, files, ast] = await Promise.all([
        api.callGraph({ asset: selectedAsset, direction, depth: 8, limit: 1500, runId: run?.run_id }),
        api.dependencyGraph({ asset: selectedAsset, direction: "both", depth: 4, limit: 1500, runId: run?.run_id }),
        api.requiredFiles({ asset: selectedAsset, depth: 8, limit: 5000, runId: run?.run_id }),
        api.astTree({ asset: selectedAsset, runId: run?.run_id }),
      ]);
      setCallView(calls);
      setDependencyView(deps);
      setFilesView(files);
      setAstView(ast);
      setActiveTab("workbench");
      setMessage(files.truncated ? "Required-file set is bounded by the selected limit." : "");
    } catch (error) {
      setMessage(error.message || "Could not load 360 workbench.");
    } finally {
      setBusy(false);
    }
  };

  const seedDemo = async () => {
    setBusy(true);
    await api.demo();
    setMessage("Demo graph loaded.");
    await loadHome();
    setBusy(false);
  };

  const insights = useMemo(() => buildInsights({ stats, validation, roots, clusters, graph, heatmap, roadmap, backendInsights }), [
    stats,
    validation,
    roots,
    clusters,
    graph,
    heatmap,
    roadmap,
    backendInsights,
  ]);

  return (
    <main className="app-shell">
      <aside className="sidebar">
        <div className="brand">
          <Layers3 size={26} />
          <div>
            <strong>MIP Intelligence</strong>
            <span>Enterprise explorer</span>
          </div>
        </div>

        <form className="search" onSubmit={runSearch}>
          <Search size={17} />
          <input value={query} onChange={(event) => setQuery(event.target.value)} placeholder="Search programs, jobs, tables" />
        </form>

        <nav className="nav-list" aria-label="Explorer sections">
          <button className={activeTab === "dashboard" ? "active" : ""} onClick={() => setActiveTab("dashboard")}>
            <ServerCog size={16} /> Dashboard
          </button>
          <button className={activeTab === "graph" ? "active" : ""} onClick={() => setActiveTab("graph")}>
            <Network size={16} /> Graph Slice
          </button>
          <button className={activeTab === "matrix" ? "active" : ""} onClick={() => setActiveTab("matrix")}>
            <Table2 size={16} /> Matrix
          </button>
          <button className={activeTab === "workbench" ? "active" : ""} onClick={() => setActiveTab("workbench")}>
            <GitBranch size={16} /> 360 Workbench
          </button>
          <button className={activeTab === "architecture" ? "active" : ""} onClick={() => setActiveTab("architecture")}>
            <Workflow size={16} /> Architecture
          </button>
          <button className={activeTab === "search" ? "active" : ""} onClick={() => setActiveTab("search")}>
            <Search size={16} /> Search Results
          </button>
        </nav>

        <section>
          <h2>Run Status</h2>
          <StatusPill status={run?.status || "unknown"} />
          <Metric icon={<Database />} label="Run" value={run?.run_id || "-"} compact />
          <Metric icon={<Boxes />} label="Assets" value={run?.asset_count ?? "-"} />
          <Metric icon={<GitBranch />} label="Edges" value={run?.relationship_count ?? "-"} />
          <Metric icon={<AlertCircle />} label="Unknowns" value={run?.unknown_count ?? "-"} />
        </section>

        <div className="sidebar-actions">
          <button className="primary" onClick={seedDemo} disabled={busy}>
            <Database size={16} /> Demo
          </button>
          <button className="ghost" onClick={loadHome} disabled={busy}>
            <RefreshCw size={16} /> Refresh
          </button>
        </div>
      </aside>

      <section className="workspace">
        <header className="topbar">
          <div>
            <span className="eyebrow">Inventory to graph to reasoning</span>
            <h1>Enterprise Intelligence Explorer</h1>
          </div>
          <ExportControls
            run={run}
            stats={stats}
            roots={roots}
            clusters={clusters}
            graph={graph}
            heatmap={heatmap}
            results={results}
            domainContexts={domainContexts}
            serviceCandidates={serviceCandidates}
            roadmap={roadmap}
          />
        </header>

        {message && <div className="notice">{message}</div>}

        <section className={activeTab === "dashboard" ? "view active" : "view"}>
          <Dashboard
            run={run}
            stats={stats}
            validation={validation}
            roots={roots}
            clusters={clusters}
            assetTypes={assetTypes}
            relationshipCounts={relationshipCounts}
            onOpenGraph={(id) => openGraph(id)}
          />
        </section>

        <section className={activeTab === "graph" ? "view active" : "view"}>
          <GraphExplorer
            graph={graph}
            depth={depth}
            limit={limit}
            confidenceMin={confidenceMin}
            relationshipTypes={relationshipTypes}
            onDepth={(value) => reloadGraph({ depth: value })}
            onLimit={(value) => reloadGraph({ limit: value })}
            onConfidence={(value) => reloadGraph({ confidenceMin: value })}
            onRelationships={(value) => reloadGraph({ relationshipTypes: value })}
            onNode={openNode}
            onEdge={openEdge}
          />
        </section>

        <section className={activeTab === "matrix" ? "view active" : "view"}>
          <MatrixView heatmap={heatmap} preset={heatmapPreset} onPreset={loadHeatmap} />
        </section>

        <section className={activeTab === "workbench" ? "view active" : "view"}>
          <EngineeringWorkbench
            focusAsset={focusAsset}
            direction={workbenchDirection}
            callView={callView}
            dependencyView={dependencyView}
            filesView={filesView}
            astView={astView}
            busy={busy}
            onAsset={setFocusAsset}
            onDirection={(value) => loadWorkbench(focusAsset, value)}
            onLoad={() => loadWorkbench()}
            onNode={openNode}
            onEdge={openEdge}
          />
        </section>

        <section className={activeTab === "architecture" ? "view active" : "view"}>
          <ArchitectureView
            contexts={domainContexts}
            services={serviceCandidates}
            roadmap={roadmap}
            onOpenGraph={(id) => openGraph(id)}
          />
        </section>

        <section className={activeTab === "search" ? "view active" : "view"}>
          <SearchResults results={results} query={query} onOpenGraph={(id) => openGraph(id)} onInspect={(id) => loadWorkbench(id)} />
        </section>
      </section>

      <aside className="insights-panel">
        <InsightsPanel insights={insights} graph={graph} roadmap={roadmap} />
      </aside>

      <DetailDrawer selected={selected} onClose={() => setSelected(null)} />
    </main>
  );
}

function Dashboard({ run, stats, validation, roots, clusters, assetTypes, relationshipCounts, onOpenGraph }) {
  const topRisk = [...roots].sort((a, b) => Number(b.risk_score || 0) - Number(a.risk_score || 0)).slice(0, 6);
  return (
    <div className="dashboard-grid">
      <Panel title="Run Overview" icon={<ServerCog />}>
        <div className="metric-grid">
          <Metric icon={<Boxes />} label="Files" value={run?.file_count ?? "-"} />
          <Metric icon={<Database />} label="Binary" value={run?.binary_count ?? "-"} />
          <Metric icon={<GitBranch />} label="Relations" value={run?.relationship_count ?? "-"} />
          <Metric icon={<AlertCircle />} label="Unknown" value={run?.unknown_count ?? "-"} />
        </div>
        <div className="bars">
          {assetTypes.map((item) => (
            <Bar key={item.asset_type} label={item.asset_type} value={item.count} max={run?.asset_count || 1} />
          ))}
        </div>
      </Panel>

      <ScanQualityPanel stats={stats} validation={validation} />

      <Panel title="Root Driver Portfolio" icon={<Network />}>
        <div className="root-grid">
          {topRisk.map((root) => (
            <button className="root-card" key={root.asset_id} onClick={() => onOpenGraph(root.asset_id)}>
              <strong>{root.technical_name}</strong>
              <span>{root.capability_label || "Needs Review"}</span>
              <small>{root.reachable_assets ?? 0} assets / risk {formatNumber(root.risk_score)}</small>
            </button>
          ))}
        </div>
      </Panel>

      <Panel title="Application Clusters" icon={<Layers3 />}>
        <div className="cluster-list">
          {clusters.slice(0, 8).map((cluster) => (
            <button key={cluster.cluster_id} onClick={() => cluster.root_asset_id && onOpenGraph(cluster.root_asset_id)}>
              <span>
                <strong>{cluster.name}</strong>
                <small>{cluster.asset_count} assets / {cluster.program_count} programs</small>
              </span>
              <RiskDot value={cluster.risk_score} />
            </button>
          ))}
        </div>
      </Panel>

      <Panel title="Relationship Mix" icon={<GitBranch />}>
        <div className="bars">
          {relationshipCounts.map((item) => (
            <Bar key={item.relationship_type} label={item.relationship_type} value={item.count} max={run?.relationship_count || 1} />
          ))}
        </div>
      </Panel>
    </div>
  );
}

function ScanQualityPanel({ stats, validation }) {
  const progress = stats?.progress || [];
  const latest = progress[progress.length - 1] || {};
  const issues = Object.entries(stats?.issues || {});
  const failedChecks = (validation?.checks || []).filter((check) => check.status !== "passed");
  return (
    <Panel title="Scan & Parser Quality" icon={<ClipboardCheck />}>
      <div className="quality-grid">
        <Metric icon={<Activity />} label="Phase" value={latest.phase || "-"} />
        <Metric icon={<Braces />} label="Parsed" value={latest.parsed_files ?? 0} />
        <Metric icon={<Database />} label="Cache Hits" value={latest.cached_parse_hits ?? 0} />
        <Metric icon={<AlertCircle />} label="Failed" value={latest.failed_files ?? 0} />
      </div>
      <div className="check-list">
        {(validation?.checks || []).slice(0, 6).map((check) => (
          <div key={check.check_name || check.name}>
            <StatusPill status={check.status} />
            <span>{check.check_name || check.name}</span>
          </div>
        ))}
        {!validation && <div className="empty-inline">No validation payload.</div>}
      </div>
      <div className="issue-strip">
        {issues.length ? (
          issues.map(([bucket, count]) => (
            <span key={bucket} className="warning">{bucket}: {count}</span>
          ))
        ) : (
          <span className={failedChecks.length ? "warning" : "badge"}>
            {failedChecks.length ? `${failedChecks.length} validation gaps` : "no scan issues"}
          </span>
        )}
      </div>
    </Panel>
  );
}

function GraphExplorer({
  graph,
  depth,
  limit,
  confidenceMin,
  relationshipTypes,
  onDepth,
  onLimit,
  onConfidence,
  onRelationships,
  onNode,
  onEdge,
}) {
  return (
    <section className="graph-zone">
      <div className="toolbar">
        <div>
          <strong>{graph ? `${graph.nodes.length} nodes / ${graph.edges.length} edges` : "Select a root or search result"}</strong>
          {graph?.cached && <span className="badge">cached</span>}
          {graph?.truncated && <span className="warning">bounded</span>}
        </div>
        <div className="controls">
          <label>
            <Filter size={14} /> Depth {depth}
            <input type="range" min="1" max="4" value={depth} onChange={(event) => onDepth(Number(event.target.value))} disabled={!graph} />
          </label>
          <label>
            Limit
            <select value={limit} onChange={(event) => onLimit(Number(event.target.value))} disabled={!graph}>
              {[100, 250, 350, 500, 750].map((item) => (
                <option key={item} value={item}>{item}</option>
              ))}
            </select>
          </label>
          <label>
            Confidence {confidenceMin.toFixed(1)}
            <input
              type="range"
              min="0"
              max="1"
              step="0.1"
              value={confidenceMin}
              onChange={(event) => onConfidence(Number(event.target.value))}
              disabled={!graph}
            />
          </label>
          <select value={relationshipTypes} onChange={(event) => onRelationships(event.target.value)} disabled={!graph} aria-label="Relationship type filter">
            {RELATIONSHIP_PRESETS.map((preset) => (
              <option key={preset.label} value={preset.value}>{preset.label}</option>
            ))}
          </select>
        </div>
      </div>
      <GraphCanvas graph={graph} onNode={onNode} onEdge={onEdge} />
    </section>
  );
}

function MatrixView({ heatmap, preset, onPreset }) {
  const max = Math.max(...(heatmap?.cells || []).map((cell) => cell.weight), 1);
  return (
    <Panel title="Heatmap Matrix" icon={<Table2 />}>
      <div className="matrix-controls">
        {HEATMAP_PRESETS.map((item) => (
          <button className={item.label === preset.label ? "active" : ""} key={item.label} onClick={() => onPreset(item)}>
            {item.label}
          </button>
        ))}
      </div>
      {!heatmap?.cells?.length ? (
        <div className="empty compact">No matrix cells for this relationship type.</div>
      ) : (
        <div className="heatmap-grid">
          {heatmap.cells.slice(0, 60).map((cell) => (
            <div className="heat-cell" key={`${cell.left_name}-${cell.right_name}`} style={{ "--heat": cell.weight / max }}>
              <strong>{cell.left_name}</strong>
              <span>{cell.right_name}</span>
              <small>{cell.weight}</small>
            </div>
          ))}
        </div>
      )}
    </Panel>
  );
}

function EngineeringWorkbench({
  focusAsset,
  direction,
  callView,
  dependencyView,
  filesView,
  astView,
  busy,
  onAsset,
  onDirection,
  onLoad,
  onNode,
  onEdge,
}) {
  return (
    <div className="workbench-grid">
      <Panel title="360 Input" icon={<GitBranch />}>
        <div className="asset-input-row">
          <input value={focusAsset} onChange={(event) => onAsset(event.target.value)} placeholder="Program, job, transaction, or asset id" />
          <select value={direction} onChange={(event) => onDirection(event.target.value)}>
            <option value="both">360</option>
            <option value="downstream">Downstream</option>
            <option value="upstream">Upstream</option>
          </select>
          <button className="primary" onClick={onLoad} disabled={busy || !focusAsset}>
            <Network size={16} /> Load
          </button>
        </div>
        <p className="small-muted">
          Membership is graph-derived. LLM naming should only explain cited evidence, not decide boundaries.
        </p>
      </Panel>

      <Panel title="Complete Call Graph" icon={<Network />}>
        <GraphCanvas graph={callView} onNode={onNode} onEdge={onEdge} />
      </Panel>

      <Panel title="Dependency Graph" icon={<GitBranch />}>
        <GraphCanvas graph={dependencyView} onNode={onNode} onEdge={onEdge} />
      </Panel>

      <Panel title="Required Files For Reverse Engineering" icon={<FileJson />}>
        <RequiredFilesView payload={filesView} />
      </Panel>

      <Panel title="AST Tree" icon={<Braces />}>
        <AstTreeView payload={astView} />
      </Panel>
    </div>
  );
}

function RequiredFilesView({ payload }) {
  if (!payload) return <div className="empty compact">Load an asset to see required files.</div>;
  const files = payload.files || [];
  return (
    <>
      <div className="mini-stats">
        <span>{files.length} files</span>
        <span>{payload.relationships?.length || 0} relationships</span>
        <span>{payload.ast_summaries?.length || 0} AST summaries</span>
      </div>
      {!files.length ? (
        <div className="empty compact">No physical source files were linked to this graph.</div>
      ) : (
        <div className="file-table">
          {files.slice(0, 120).map((file) => (
            <div key={`${file.asset_id}-${file.relative_path}`}>
              <strong>{file.relative_path}</strong>
              <span>{file.asset_type} / {file.artifact_type} / {file.validation_status}</span>
              <small>{file.absolute_path || "source root not available"}</small>
            </div>
          ))}
        </div>
      )}
    </>
  );
}

function AstTreeView({ payload }) {
  const tree = payload?.ast_tree;
  if (!tree) return <div className="empty compact">No AST tree loaded.</div>;
  return (
    <div className="ast-tree">
      <strong>{payload.asset?.technical_name}</strong>
      <small>
        complexity {tree.complexity ?? "-"} / parser {tree.parser?.effective || "unknown"}
      </small>
      <TreeNode node={tree} depth={0} />
    </div>
  );
}

function TreeNode({ node, depth }) {
  const children = node.children || [];
  return (
    <div className="tree-node" style={{ "--depth": depth }}>
      <span>{node.type}: <strong>{node.label}</strong></span>
      {node.pic && <small>PIC {node.pic}</small>}
      {children.slice(0, 80).map((child, index) => (
        <TreeNode key={`${child.type}-${child.label}-${index}`} node={child} depth={depth + 1} />
      ))}
      {children.length > 80 && <em>{children.length - 80} more nodes omitted from browser view</em>}
    </div>
  );
}

function SearchResults({ results, query, onOpenGraph, onInspect }) {
  return (
    <Panel title="Search-First Navigation" icon={<Search />}>
      {!results.length ? (
        <div className="empty compact">{query ? "No matching assets found." : "Search from the left rail to find an asset."}</div>
      ) : (
        <div className="result-table">
          {results.map((item) => (
            <button key={item.asset_id} onClick={() => onOpenGraph(item.asset_id)}>
              <span>
                <strong>{item.technical_name}</strong>
                <small>{item.asset_type} / {item.validation_status} / confidence {formatNumber(item.confidence)}</small>
              </span>
              <span className="result-actions">
                <GitBranch size={16} onClick={(event) => { event.stopPropagation(); onInspect(item.asset_id); }} />
                <Network size={16} />
              </span>
            </button>
          ))}
        </div>
      )}
    </Panel>
  );
}

function ArchitectureView({ contexts, services, roadmap, onOpenGraph }) {
  return (
    <div className="architecture-grid">
      <Panel title="Bounded Contexts" icon={<Workflow />}>
        <div className="context-list">
          {contexts.slice(0, 12).map((context) => (
            <button key={context.context_id} onClick={() => context.root_asset_id && onOpenGraph(context.root_asset_id)}>
              <span>
                <strong>{context.name}</strong>
                <small>{context.domain} / {context.membership_scope} / confidence {formatNumber(context.confidence)}</small>
              </span>
              <RiskDot value={context.risk_score} />
            </button>
          ))}
          {!contexts.length && <div className="empty compact">No bounded context candidates.</div>}
        </div>
      </Panel>

      <Panel title="Service Candidates" icon={<ServerCog />}>
        <div className="service-list">
          {services.slice(0, 10).map((service) => (
            <article key={service.candidate_id}>
              <div className="service-head">
                <span>
                  <strong>{service.java_service_candidate}</strong>
                  <small>{service.package_candidate}</small>
                </span>
                <StatusPill status={service.validation_status} />
              </div>
              <div className="mini-stats">
                <span>{service.api_candidates.length} APIs</span>
                <span>{service.data_contracts.length} contracts</span>
                <span>risk {formatNumber(service.risk_score)}</span>
              </div>
              <ul className="compact-list">
                {service.data_contracts.slice(0, 4).map((contract) => (
                  <li key={contract.asset_id}>{contract.technical_name} / {contract.role}</li>
                ))}
              </ul>
            </article>
          ))}
          {!services.length && <div className="empty compact">No service candidates.</div>}
        </div>
      </Panel>

      <Panel title="Modernization Roadmap" icon={<Route />}>
        <div className="roadmap-list">
          {roadmap.slice(0, 8).map((packageItem) => (
            <article key={`${packageItem.sequence}-${packageItem.service_candidate}`}>
              <div className="roadmap-sequence">{packageItem.sequence}</div>
              <div>
                <strong>{packageItem.service_candidate}</strong>
                <small>{packageItem.bounded_context} / risk {formatNumber(packageItem.risk_score)}</small>
                <div className="step-row">
                  {packageItem.steps.slice(0, 4).map((step) => (
                    <span key={step.kind}>{step.kind.replaceAll("_", " ")}</span>
                  ))}
                </div>
                <div className="gate-row">
                  {(packageItem.feedback_loop?.quality_gates || []).slice(0, 4).map((gate) => (
                    <span key={gate}>{gate.replaceAll("_", " ")}</span>
                  ))}
                </div>
              </div>
            </article>
          ))}
          {!roadmap.length && <div className="empty compact">No roadmap work packages.</div>}
        </div>
      </Panel>

      <Panel title="Feedback Gates" icon={<ShieldCheck />}>
        <div className="gate-board">
          <div>
            <strong>Evidence</strong>
            <span>parser confidence, graph boundary review, cited facts</span>
          </div>
          <div>
            <strong>Regression</strong>
            <span>golden-master tests, contract tests, dual-run reconciliation</span>
          </div>
          <div>
            <strong>Operations</strong>
            <span>rollback signal, telemetry, readiness review</span>
          </div>
        </div>
      </Panel>
    </div>
  );
}

function GraphCanvas({ graph, onNode, onEdge }) {
  const positioned = useMemo(() => {
    if (!graph) return [];
    const rings = graph.nodes.reduce((acc, node) => {
      acc[node.depth] = (acc[node.depth] || 0) + 1;
      return acc;
    }, {});
    const seen = {};
    return graph.nodes.map((node) => {
      const index = seen[node.depth] || 0;
      seen[node.depth] = index + 1;
      const ring = 70 + node.depth * 92;
      const count = Math.max(rings[node.depth], 1);
      const angle = (index / count) * Math.PI * 2 + node.depth * 0.55;
      return { ...node, x: 430 + Math.cos(angle) * ring, y: 280 + Math.sin(angle) * ring };
    });
  }, [graph]);
  const byId = Object.fromEntries(positioned.map((node) => [node.id, node]));
  if (!graph) {
    return <div className="empty">Choose a root driver, cluster, or search result to load a bounded graph slice.</div>;
  }
  return (
    <svg className="graph-canvas" viewBox="0 0 860 560" role="img" aria-label="Bounded graph slice">
      {graph.edges.map((edge) => {
        const source = byId[edge.source];
        const target = byId[edge.target];
        if (!source || !target) return null;
        return (
          <g key={edge.id} onClick={() => onEdge(edge.id)} className={`edge ${edge.validation_status}`}>
            <line x1={source.x} y1={source.y} x2={target.x} y2={target.y} />
            <text x={(source.x + target.x) / 2} y={(source.y + target.y) / 2}>
              {edge.type}
            </text>
          </g>
        );
      })}
      {positioned.map((node) => (
        <g key={node.id} className={`node ${node.validation_status}`} onClick={() => onNode(node.id)}>
          <circle cx={node.x} cy={node.y} r={node.depth === 0 ? 21 : node.type === "PROGRAM" ? 16 : 12} />
          <text x={node.x} y={node.y + 32}>
            {node.label}
          </text>
        </g>
      ))}
    </svg>
  );
}

function DetailDrawer({ selected, onClose }) {
  if (!selected) return null;
  if (selected.kind === "loading") {
    return (
      <aside className="drawer">
        <button className="close" onClick={onClose}>Close</button>
        <div className="empty compact">Loading evidence...</div>
      </aside>
    );
  }
  const payload = selected.payload;
  const isNode = selected.kind === "node";
  const title = isNode ? payload.asset.technical_name : `${payload.relationship.source_name} to ${payload.relationship.target_name}`;
  return (
    <aside className="drawer">
      <button className="close" onClick={onClose}>Close</button>
      <span className="eyebrow">{isNode ? "Asset profile" : "Relationship profile"}</span>
      <h2>{title}</h2>
      {isNode ? (
        <>
          <p>{payload.functionality}</p>
          <dl>
            <dt>Type</dt><dd>{payload.asset.asset_type}</dd>
            <dt>Confidence</dt><dd>{formatNumber(payload.asset.confidence)}</dd>
            <dt>Status</dt><dd><StatusPill status={payload.asset.validation_status} /></dd>
            <dt>Outgoing</dt><dd>{payload.metrics.outgoing_count}</dd>
            <dt>Incoming</dt><dd>{payload.metrics.incoming_count}</dd>
            <dt>Data Touchpoints</dt><dd>{payload.metrics.data_touchpoints}</dd>
          </dl>
          <RelationshipList title="Incoming" rows={payload.incoming} />
          <RelationshipList title="Outgoing" rows={payload.outgoing} />
          <h3>Attributes</h3>
          <JsonBlock value={payload.asset.attributes} />
          <h3>Evidence</h3>
          <EvidenceList rows={payload.evidence} />
        </>
      ) : (
        <>
          <dl>
            <dt>Relationship</dt><dd>{payload.relationship.relationship_type}</dd>
            <dt>Confidence</dt><dd>{formatNumber(payload.relationship.confidence)}</dd>
            <dt>Status</dt><dd><StatusPill status={payload.relationship.validation_status} /></dd>
            <dt>Method</dt><dd>{payload.relationship.discovery_method}</dd>
          </dl>
          <h3>Attributes</h3>
          <JsonBlock value={payload.relationship.attributes} />
          <h3>Evidence</h3>
          <EvidenceList rows={payload.evidence} />
        </>
      )}
    </aside>
  );
}

function JsonBlock({ value }) {
  if (!value || !Object.keys(value).length) return <p>No attributes recorded.</p>;
  return <pre className="json-block">{JSON.stringify(value, null, 2)}</pre>;
}

function InsightsPanel({ insights, graph, roadmap }) {
  return (
    <section>
      <div className="panel-heading">
        <Sparkles size={17} />
        <h2>Insights</h2>
      </div>
      <div className="insight-list">
        {insights.map((insight) => (
          <article key={insight.title} className={insight.level}>
            <strong>{insight.title}</strong>
            <p>{insight.body}</p>
            <small>{insight.evidence}</small>
          </article>
        ))}
      </div>
      {graph && (
        <div className="slice-summary">
          <strong>Current Slice</strong>
          <span>{graph.depth} depth / {graph.limit} limit</span>
          <span>{graph.stats?.needs_review_edges || 0} needs-review edges</span>
        </div>
      )}
      {!!roadmap?.length && (
        <div className="slice-summary">
          <strong>Roadmap</strong>
          <span>{roadmap.length} work packages</span>
          <span>next: {roadmap[0]?.service_candidate}</span>
        </div>
      )}
    </section>
  );
}

function ExportControls({ run, stats, roots, clusters, graph, heatmap, results, domainContexts, serviceCandidates, roadmap }) {
  const exportPayload = (name, payload) => {
    const blob = new Blob([JSON.stringify(payload, null, 2)], { type: "application/json" });
    const url = URL.createObjectURL(blob);
    const link = document.createElement("a");
    link.href = url;
    link.download = `${name}.json`;
    link.click();
    URL.revokeObjectURL(url);
  };
  return (
    <div className="export-controls">
      <button onClick={() => exportPayload(`mip-run-${run?.run_id || "latest"}`, { stats, roots, clusters })}>
        <FileJson size={16} /> Portfolio
      </button>
      <button onClick={() => exportPayload(`mip-slice-${graph?.root_asset_id || "none"}`, graph || {})} disabled={!graph}>
        <Download size={16} /> Slice
      </button>
      <button onClick={() => exportPayload("mip-workbench", { results, heatmap })}>
        <Braces size={16} /> Workbench
      </button>
      <button onClick={() => exportPayload("mip-architecture", { domainContexts, serviceCandidates, roadmap })}>
        <Workflow size={16} /> Architecture
      </button>
    </div>
  );
}

function Metric({ icon, label, value, compact = false }) {
  return (
    <div className={compact ? "metric compact" : "metric"}>
      {React.cloneElement(icon, { size: 16 })}
      <span>{label}</span>
      <strong title={String(value)}>{value}</strong>
    </div>
  );
}

function Panel({ title, icon, children }) {
  return (
    <section className="panel">
      <div className="panel-heading">
        {React.cloneElement(icon, { size: 17 })}
        <h2>{title}</h2>
      </div>
      {children}
    </section>
  );
}

function Bar({ label, value, max }) {
  const width = `${Math.max(4, (Number(value || 0) / Math.max(Number(max || 1), 1)) * 100)}%`;
  return (
    <div className="bar-row">
      <span>{label}</span>
      <div><i style={{ width }} /></div>
      <strong>{value}</strong>
    </div>
  );
}

function RiskDot({ value }) {
  const risk = Number(value || 0);
  return <span className={risk > 0.65 ? "risk high" : risk > 0.3 ? "risk medium" : "risk low"}>{formatNumber(risk)}</span>;
}

function StatusPill({ status }) {
  return <span className={`status ${String(status).toLowerCase()}`}>{status}</span>;
}

function RelationshipList({ title, rows }) {
  if (!rows?.length) return null;
  return (
    <>
      <h3>{title}</h3>
      <ul className="relationship-list">
        {rows.slice(0, 8).map((row) => (
          <li key={row.relationship_id}>
            <strong>{row.relationship_type}</strong>
            <span>{row.source_name} to {row.target_name}</span>
          </li>
        ))}
      </ul>
    </>
  );
}

function EvidenceList({ rows }) {
  if (!rows?.length) return <p>No evidence recorded.</p>;
  return (
    <ul className="evidence">
      {rows.map((row) => (
        <li key={row.evidence_id}>
          <strong>{row.source_path}:{row.line_start ?? "?"}</strong>
          <span>{row.evidence_text}</span>
        </li>
      ))}
    </ul>
  );
}

function buildInsights({ stats, validation, roots, clusters, graph, heatmap, roadmap, backendInsights }) {
  const run = stats?.run || {};
  const unknowns = Number(run.unknown_count || 0);
  const relationships = Number(run.relationship_count || 0);
  const riskyRoots = roots.filter((root) => Number(root.risk_score || 0) > 0.3);
  const largestCluster = [...clusters].sort((a, b) => Number(b.asset_count || 0) - Number(a.asset_count || 0))[0];
  const validationFailed = (validation?.checks || []).filter((check) => check.status !== "passed").length;
  const items = [
    {
      level: unknowns ? "warn" : "ok",
      title: unknowns ? "Inventory has review gaps" : "Inventory is classified",
      body: unknowns
        ? `${unknowns} source members are unknown or binary and should stay visible in downstream decisions.`
        : "The current run has no unknown members reported.",
      evidence: `run_manifest unknown_count=${unknowns}`,
    },
    {
      level: riskyRoots.length ? "warn" : "ok",
      title: riskyRoots.length ? "Root portfolio has risk concentration" : "Root portfolio risk is low",
      body: `${riskyRoots.length} root drivers have risk above 0.30 across ${roots.length} portfolio entries.`,
      evidence: "root_summary risk_score",
    },
  ];
  if (validation) {
    items.push({
      level: validation.status === "passed" ? "ok" : "warn",
      title: validation.status === "passed" ? "Evidence validation passed" : "Evidence validation has gaps",
      body: `${validationFailed} validation checks need attention across the current run.`,
      evidence: "validation_result computed read model",
    });
  }
  if (graph) {
    items.push({
      level: graph.stats?.needs_review_edges ? "warn" : "ok",
      title: "Bounded graph slice loaded",
      body: `${graph.nodes.length} nodes and ${graph.edges.length} edges are loaded, with ${graph.stats?.needs_review_edges || 0} needs-review edges.`,
      evidence: `graph_slice depth=${graph.depth} limit=${graph.limit}`,
    });
  }
  if (largestCluster) {
    items.push({
      level: "info",
      title: "Largest cluster",
      body: `${largestCluster.name} contains ${largestCluster.asset_count} assets and ${largestCluster.program_count} programs.`,
      evidence: "app_cluster summary",
    });
  }
  if (heatmap?.cells?.length) {
    items.push({
      level: "info",
      title: "Matrix ready for comparison",
      body: `${heatmap.cells.length} weighted cells are available for ${heatmap.relationship_type}.`,
      evidence: "heatmap relationship aggregation",
    });
  }
  if (roadmap?.length) {
    items.push({
      level: "info",
      title: "Modernization roadmap ready",
      body: `${roadmap.length} work packages are ordered by risk and confidence.`,
      evidence: "architecture/roadmap",
    });
  }
  for (const insight of (backendInsights || []).slice(0, 2)) {
    items.push({
      level: insight.validation_status === "needs_review" ? "warn" : "info",
      title: insight.title,
      body: insight.body,
      evidence: insight.insight_type,
    });
  }
  if (!relationships) {
    items.push({
      level: "warn",
      title: "No relationships reported",
      body: "Seed demo data or run analysis before using impact and lineage views.",
      evidence: "run_manifest relationship_count=0",
    });
  }
  return items.slice(0, 7);
}

function formatNumber(value) {
  const number = Number(value ?? 0);
  return Number.isFinite(number) ? number.toFixed(number % 1 ? 2 : 0) : "-";
}

createRoot(document.getElementById("root")).render(<App />);
