PRAGMA foreign_keys = ON;

CREATE TABLE IF NOT EXISTS schema_version (
    version INTEGER PRIMARY KEY,
    backend TEXT NOT NULL,
    description TEXT NOT NULL,
    applied_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS run_manifest (
    run_id TEXT PRIMARY KEY,
    source_root TEXT NOT NULL,
    started_at TEXT NOT NULL,
    completed_at TEXT,
    status TEXT NOT NULL,
    file_count INTEGER NOT NULL DEFAULT 0,
    asset_count INTEGER NOT NULL DEFAULT 0,
    relationship_count INTEGER NOT NULL DEFAULT 0,
    unknown_count INTEGER NOT NULL DEFAULT 0,
    binary_count INTEGER NOT NULL DEFAULT 0,
    warning_count INTEGER NOT NULL DEFAULT 0,
    config_json TEXT NOT NULL DEFAULT '{}'
);

CREATE TABLE IF NOT EXISTS source_member (
    member_id TEXT PRIMARY KEY,
    run_id TEXT NOT NULL REFERENCES run_manifest(run_id) ON DELETE CASCADE,
    relative_path TEXT NOT NULL,
    folder_path TEXT NOT NULL,
    member_name TEXT NOT NULL,
    sha256 TEXT NOT NULL,
    size_bytes INTEGER NOT NULL,
    encoding TEXT,
    is_binary INTEGER NOT NULL DEFAULT 0,
    text_status TEXT NOT NULL DEFAULT 'TEXT',
    artifact_type TEXT NOT NULL,
    classification_basis TEXT NOT NULL,
    confidence REAL NOT NULL,
    validation_status TEXT NOT NULL,
    discovered_at TEXT NOT NULL,
    UNIQUE(run_id, relative_path)
);

CREATE TABLE IF NOT EXISTS asset (
    asset_id TEXT PRIMARY KEY,
    run_id TEXT NOT NULL REFERENCES run_manifest(run_id) ON DELETE CASCADE,
    asset_type TEXT NOT NULL,
    technical_name TEXT NOT NULL,
    display_name TEXT NOT NULL,
    member_id TEXT REFERENCES source_member(member_id) ON DELETE SET NULL,
    folder_path TEXT,
    confidence REAL NOT NULL,
    validation_status TEXT NOT NULL,
    discovery_method TEXT NOT NULL,
    attributes_json TEXT NOT NULL DEFAULT '{}',
    created_at TEXT NOT NULL,
    UNIQUE(run_id, asset_type, technical_name)
);

CREATE TABLE IF NOT EXISTS relationship (
    relationship_id TEXT PRIMARY KEY,
    run_id TEXT NOT NULL REFERENCES run_manifest(run_id) ON DELETE CASCADE,
    relationship_type TEXT NOT NULL,
    source_asset_id TEXT NOT NULL REFERENCES asset(asset_id) ON DELETE CASCADE,
    target_asset_id TEXT NOT NULL REFERENCES asset(asset_id) ON DELETE CASCADE,
    confidence REAL NOT NULL,
    validation_status TEXT NOT NULL,
    discovery_method TEXT NOT NULL,
    attributes_json TEXT NOT NULL DEFAULT '{}',
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS evidence (
    evidence_id TEXT PRIMARY KEY,
    run_id TEXT NOT NULL REFERENCES run_manifest(run_id) ON DELETE CASCADE,
    entity_kind TEXT NOT NULL,
    entity_id TEXT NOT NULL,
    source_path TEXT NOT NULL,
    line_start INTEGER,
    line_end INTEGER,
    evidence_text TEXT NOT NULL,
    extractor TEXT NOT NULL,
    discovery_method TEXT NOT NULL,
    confidence REAL NOT NULL,
    validation_status TEXT NOT NULL,
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS root_summary (
    run_id TEXT NOT NULL REFERENCES run_manifest(run_id) ON DELETE CASCADE,
    root_asset_id TEXT NOT NULL REFERENCES asset(asset_id) ON DELETE CASCADE,
    reachable_assets INTEGER NOT NULL,
    reachable_programs INTEGER NOT NULL,
    data_touchpoints INTEGER NOT NULL,
    unresolved_count INTEGER NOT NULL,
    risk_score REAL NOT NULL,
    capability_label TEXT NOT NULL,
    summary_json TEXT NOT NULL DEFAULT '{}',
    PRIMARY KEY(run_id, root_asset_id)
);

CREATE TABLE IF NOT EXISTS app_cluster (
    cluster_id TEXT PRIMARY KEY,
    run_id TEXT NOT NULL REFERENCES run_manifest(run_id) ON DELETE CASCADE,
    name TEXT NOT NULL,
    root_asset_id TEXT REFERENCES asset(asset_id) ON DELETE SET NULL,
    asset_count INTEGER NOT NULL,
    program_count INTEGER NOT NULL,
    data_count INTEGER NOT NULL,
    unresolved_count INTEGER NOT NULL,
    risk_score REAL NOT NULL,
    attributes_json TEXT NOT NULL DEFAULT '{}'
);

CREATE TABLE IF NOT EXISTS node_degree (
    run_id TEXT NOT NULL REFERENCES run_manifest(run_id) ON DELETE CASCADE,
    asset_id TEXT NOT NULL REFERENCES asset(asset_id) ON DELETE CASCADE,
    in_degree INTEGER NOT NULL,
    out_degree INTEGER NOT NULL,
    total_degree INTEGER NOT NULL,
    PRIMARY KEY(run_id, asset_id)
);

CREATE TABLE IF NOT EXISTS graph_slice_cache (
    cache_key TEXT PRIMARY KEY,
    run_id TEXT NOT NULL REFERENCES run_manifest(run_id) ON DELETE CASCADE,
    root_asset_id TEXT REFERENCES asset(asset_id) ON DELETE CASCADE,
    mode TEXT NOT NULL,
    depth INTEGER NOT NULL,
    limit_count INTEGER NOT NULL,
    relationship_types TEXT NOT NULL,
    confidence_min REAL NOT NULL,
    payload_json TEXT NOT NULL,
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS parser_result_cache (
    cache_key TEXT PRIMARY KEY,
    source_sha256 TEXT NOT NULL,
    resolver_fingerprint TEXT NOT NULL,
    parser_version TEXT NOT NULL,
    payload_json TEXT NOT NULL,
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS insight (
    insight_id TEXT PRIMARY KEY,
    run_id TEXT NOT NULL REFERENCES run_manifest(run_id) ON DELETE CASCADE,
    insight_type TEXT NOT NULL,
    subject_asset_id TEXT REFERENCES asset(asset_id) ON DELETE CASCADE,
    title TEXT NOT NULL,
    body TEXT NOT NULL,
    confidence REAL NOT NULL,
    validation_status TEXT NOT NULL,
    citations_json TEXT NOT NULL DEFAULT '[]',
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS validation_result (
    validation_id TEXT PRIMARY KEY,
    run_id TEXT NOT NULL REFERENCES run_manifest(run_id) ON DELETE CASCADE,
    check_name TEXT NOT NULL,
    status TEXT NOT NULL,
    details_json TEXT NOT NULL DEFAULT '{}',
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS scan_progress (
    run_id TEXT NOT NULL REFERENCES run_manifest(run_id) ON DELETE CASCADE,
    phase TEXT NOT NULL,
    total_files INTEGER NOT NULL DEFAULT 0,
    processed_files INTEGER NOT NULL DEFAULT 0,
    parsed_files INTEGER NOT NULL DEFAULT 0,
    cached_parse_hits INTEGER NOT NULL DEFAULT 0,
    failed_files INTEGER NOT NULL DEFAULT 0,
    started_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    details_json TEXT NOT NULL DEFAULT '{}',
    PRIMARY KEY(run_id, phase)
);

CREATE TABLE IF NOT EXISTS scan_issue (
    issue_id TEXT PRIMARY KEY,
    run_id TEXT NOT NULL REFERENCES run_manifest(run_id) ON DELETE CASCADE,
    relative_path TEXT NOT NULL,
    stage TEXT NOT NULL,
    severity TEXT NOT NULL,
    error_type TEXT NOT NULL,
    message TEXT NOT NULL,
    details_json TEXT NOT NULL DEFAULT '{}',
    created_at TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_member_run_type ON source_member(run_id, artifact_type);
CREATE INDEX IF NOT EXISTS idx_member_run_folder ON source_member(run_id, folder_path);
CREATE INDEX IF NOT EXISTS idx_member_run_status ON source_member(run_id, validation_status);
CREATE INDEX IF NOT EXISTS idx_asset_run_type_name ON asset(run_id, asset_type, technical_name);
CREATE INDEX IF NOT EXISTS idx_asset_run_folder ON asset(run_id, folder_path);
CREATE INDEX IF NOT EXISTS idx_asset_run_status ON asset(run_id, validation_status);
CREATE INDEX IF NOT EXISTS idx_relationship_run_source ON relationship(run_id, source_asset_id);
CREATE INDEX IF NOT EXISTS idx_relationship_run_target ON relationship(run_id, target_asset_id);
CREATE INDEX IF NOT EXISTS idx_relationship_run_type ON relationship(run_id, relationship_type);
CREATE INDEX IF NOT EXISTS idx_relationship_run_status ON relationship(run_id, validation_status);
CREATE INDEX IF NOT EXISTS idx_relationship_run_confidence ON relationship(run_id, confidence);
CREATE INDEX IF NOT EXISTS idx_evidence_entity ON evidence(run_id, entity_kind, entity_id);
CREATE INDEX IF NOT EXISTS idx_root_summary_risk ON root_summary(run_id, risk_score DESC);
CREATE INDEX IF NOT EXISTS idx_cluster_run_risk ON app_cluster(run_id, risk_score DESC);
CREATE INDEX IF NOT EXISTS idx_insight_run_type ON insight(run_id, insight_type);
CREATE INDEX IF NOT EXISTS idx_parser_cache_source ON parser_result_cache(source_sha256, resolver_fingerprint);
CREATE INDEX IF NOT EXISTS idx_scan_progress_run ON scan_progress(run_id, phase);
CREATE INDEX IF NOT EXISTS idx_scan_issue_run_stage ON scan_issue(run_id, stage, severity);
