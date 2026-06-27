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
    origin TEXT NOT NULL DEFAULT 'baseline',
    enriched_by_member TEXT,
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
    origin TEXT NOT NULL DEFAULT 'baseline',
    enriched_by_member TEXT,
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

CREATE TABLE IF NOT EXISTS enrichment_artifact_cache (
    artifact_id TEXT PRIMARY KEY,
    source_sha256 TEXT NOT NULL,
    parser_version TEXT NOT NULL,
    grammar_dialect TEXT NOT NULL DEFAULT 'ibm-enterprise-cobol',
    resolver_fingerprint TEXT NOT NULL,
    parse_status TEXT NOT NULL,
    ast_json TEXT,
    payload_json TEXT,
    diagnostics_json TEXT NOT NULL DEFAULT '{}',
    fact_count INTEGER NOT NULL DEFAULT 0,
    parser_confidence REAL NOT NULL DEFAULT 0,
    elapsed_ms REAL NOT NULL DEFAULT 0,
    created_at TEXT NOT NULL,
    UNIQUE(source_sha256, parser_version, grammar_dialect, resolver_fingerprint)
);

CREATE TABLE IF NOT EXISTS enrichment_member_status (
    run_id TEXT NOT NULL REFERENCES run_manifest(run_id) ON DELETE CASCADE,
    member_id TEXT NOT NULL REFERENCES source_member(member_id) ON DELETE CASCADE,
    source_sha256 TEXT NOT NULL,
    artifact_id TEXT REFERENCES enrichment_artifact_cache(artifact_id) ON DELETE SET NULL,
    state TEXT NOT NULL,
    priority INTEGER NOT NULL DEFAULT 0,
    attempts INTEGER NOT NULL DEFAULT 0,
    last_error TEXT,
    materialized_at TEXT,
    updated_at TEXT NOT NULL,
    PRIMARY KEY(run_id, member_id)
);

CREATE TABLE IF NOT EXISTS enrichment_job (
    job_id TEXT PRIMARY KEY,
    run_id TEXT NOT NULL REFERENCES run_manifest(run_id) ON DELETE CASCADE,
    started_at TEXT NOT NULL,
    finished_at TEXT,
    status TEXT NOT NULL,
    selected_count INTEGER NOT NULL DEFAULT 0,
    enriched_count INTEGER NOT NULL DEFAULT 0,
    failed_count INTEGER NOT NULL DEFAULT 0,
    skipped_count INTEGER NOT NULL DEFAULT 0,
    config_json TEXT NOT NULL DEFAULT '{}'
);

CREATE TABLE IF NOT EXISTS enrichment_fact_source (
    fact_source_id TEXT PRIMARY KEY,
    run_id TEXT NOT NULL REFERENCES run_manifest(run_id) ON DELETE CASCADE,
    entity_kind TEXT NOT NULL,
    entity_id TEXT NOT NULL,
    origin TEXT NOT NULL,
    source_member_id TEXT NOT NULL,
    evidence_id TEXT,
    parser_tier TEXT NOT NULL,
    confidence REAL NOT NULL,
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS runtime_observation (
    observation_id TEXT PRIMARY KEY,
    run_id TEXT NOT NULL REFERENCES run_manifest(run_id) ON DELETE CASCADE,
    observation_type TEXT NOT NULL,
    source_asset TEXT NOT NULL,
    target_asset TEXT NOT NULL,
    observation_count INTEGER NOT NULL DEFAULT 1,
    first_seen TEXT,
    last_seen TEXT,
    environment TEXT,
    job TEXT,
    transaction_id TEXT,
    source_system TEXT NOT NULL,
    evidence_json TEXT NOT NULL DEFAULT '{}',
    imported_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS catalog_dataset (
    catalog_id TEXT PRIMARY KEY,
    run_id TEXT NOT NULL REFERENCES run_manifest(run_id) ON DELETE CASCADE,
    raw_dataset TEXT NOT NULL,
    canonical_dataset TEXT NOT NULL,
    dataset_type TEXT,
    gdg_base TEXT,
    vsam_cluster TEXT,
    volume TEXT,
    storage_class TEXT,
    management_class TEXT,
    record_format TEXT,
    lrecl TEXT,
    owner TEXT,
    application TEXT,
    catalog_source TEXT NOT NULL,
    evidence_json TEXT NOT NULL DEFAULT '{}',
    imported_at TEXT NOT NULL,
    UNIQUE(run_id, raw_dataset, catalog_source)
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

CREATE TABLE IF NOT EXISTS scan_phase_telemetry (
    telemetry_id TEXT PRIMARY KEY,
    run_id TEXT NOT NULL REFERENCES run_manifest(run_id) ON DELETE CASCADE,
    phase TEXT NOT NULL,
    elapsed_ms REAL NOT NULL,
    memory_peak_bytes INTEGER NOT NULL DEFAULT 0,
    details_json TEXT NOT NULL DEFAULT '{}',
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS scan_file_telemetry (
    run_id TEXT NOT NULL REFERENCES run_manifest(run_id) ON DELETE CASCADE,
    relative_path TEXT NOT NULL,
    sha256 TEXT NOT NULL,
    size_bytes INTEGER NOT NULL,
    artifact_type TEXT NOT NULL,
    classification_basis TEXT NOT NULL,
    validation_status TEXT NOT NULL,
    classify_ms REAL NOT NULL DEFAULT 0,
    parse_ms REAL NOT NULL DEFAULT 0,
    graph_ms REAL NOT NULL DEFAULT 0,
    total_ms REAL NOT NULL DEFAULT 0,
    reused_classification INTEGER NOT NULL DEFAULT 0,
    parse_cache_hit INTEGER NOT NULL DEFAULT 0,
    skipped INTEGER NOT NULL DEFAULT 0,
    details_json TEXT NOT NULL DEFAULT '{}',
    created_at TEXT NOT NULL,
    PRIMARY KEY(run_id, relative_path)
);

CREATE TABLE IF NOT EXISTS file_inventory_cache (
    source_root TEXT NOT NULL,
    relative_path TEXT NOT NULL,
    sha256 TEXT NOT NULL,
    size_bytes INTEGER NOT NULL,
    encoding TEXT,
    is_binary INTEGER NOT NULL DEFAULT 0,
    text_status TEXT NOT NULL,
    artifact_type TEXT NOT NULL,
    classification_basis TEXT NOT NULL,
    confidence REAL NOT NULL,
    validation_status TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    PRIMARY KEY(source_root, relative_path)
);

CREATE TABLE IF NOT EXISTS discovery_correction (
    correction_id TEXT PRIMARY KEY,
    scope_run_id TEXT,
    entity_kind TEXT NOT NULL,
    selector TEXT NOT NULL,
    action TEXT NOT NULL,
    corrected_type TEXT,
    corrected_name TEXT,
    corrected_status TEXT,
    corrected_confidence REAL,
    reason TEXT NOT NULL DEFAULT '',
    active INTEGER NOT NULL DEFAULT 1,
    attributes_json TEXT NOT NULL DEFAULT '{}',
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS scorecard_result (
    scorecard_id TEXT PRIMARY KEY,
    run_id TEXT NOT NULL REFERENCES run_manifest(run_id) ON DELETE CASCADE,
    name TEXT NOT NULL,
    expected_count INTEGER NOT NULL,
    matched_count INTEGER NOT NULL,
    missing_count INTEGER NOT NULL,
    unexpected_count INTEGER NOT NULL,
    precision REAL NOT NULL,
    recall REAL NOT NULL,
    status TEXT NOT NULL,
    details_json TEXT NOT NULL DEFAULT '{}',
    created_at TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_member_run_type ON source_member(run_id, artifact_type);
CREATE INDEX IF NOT EXISTS idx_member_run_folder ON source_member(run_id, folder_path);
CREATE INDEX IF NOT EXISTS idx_member_run_status ON source_member(run_id, validation_status);
CREATE INDEX IF NOT EXISTS idx_asset_run_type_name ON asset(run_id, asset_type, technical_name);
CREATE INDEX IF NOT EXISTS idx_asset_run_folder ON asset(run_id, folder_path);
CREATE INDEX IF NOT EXISTS idx_asset_run_status ON asset(run_id, validation_status);
CREATE INDEX IF NOT EXISTS idx_asset_run_origin ON asset(run_id, origin);
CREATE INDEX IF NOT EXISTS idx_relationship_run_source ON relationship(run_id, source_asset_id);
CREATE INDEX IF NOT EXISTS idx_relationship_run_target ON relationship(run_id, target_asset_id);
CREATE INDEX IF NOT EXISTS idx_relationship_run_type ON relationship(run_id, relationship_type);
CREATE INDEX IF NOT EXISTS idx_relationship_run_status ON relationship(run_id, validation_status);
CREATE INDEX IF NOT EXISTS idx_relationship_run_confidence ON relationship(run_id, confidence);
CREATE INDEX IF NOT EXISTS idx_relationship_run_origin ON relationship(run_id, origin);
CREATE INDEX IF NOT EXISTS idx_evidence_entity ON evidence(run_id, entity_kind, entity_id);
CREATE INDEX IF NOT EXISTS idx_root_summary_risk ON root_summary(run_id, risk_score DESC);
CREATE INDEX IF NOT EXISTS idx_cluster_run_risk ON app_cluster(run_id, risk_score DESC);
CREATE INDEX IF NOT EXISTS idx_insight_run_type ON insight(run_id, insight_type);
CREATE INDEX IF NOT EXISTS idx_parser_cache_source ON parser_result_cache(source_sha256, resolver_fingerprint);
CREATE INDEX IF NOT EXISTS idx_enrich_artifact_sha ON enrichment_artifact_cache(source_sha256);
CREATE INDEX IF NOT EXISTS idx_enrich_member_state ON enrichment_member_status(run_id, state, priority DESC);
CREATE INDEX IF NOT EXISTS idx_enrich_member_sha ON enrichment_member_status(run_id, source_sha256);
CREATE INDEX IF NOT EXISTS idx_enrich_job_run ON enrichment_job(run_id, started_at);
CREATE INDEX IF NOT EXISTS idx_fact_source_entity ON enrichment_fact_source(run_id, entity_kind, entity_id);
CREATE INDEX IF NOT EXISTS idx_runtime_observation_run ON runtime_observation(run_id, observation_type, source_asset, target_asset);
CREATE INDEX IF NOT EXISTS idx_catalog_dataset_run ON catalog_dataset(run_id, canonical_dataset, raw_dataset);
CREATE INDEX IF NOT EXISTS idx_scan_progress_run ON scan_progress(run_id, phase);
CREATE INDEX IF NOT EXISTS idx_scan_issue_run_stage ON scan_issue(run_id, stage, severity);
CREATE INDEX IF NOT EXISTS idx_phase_telemetry_run ON scan_phase_telemetry(run_id, phase);
CREATE INDEX IF NOT EXISTS idx_file_telemetry_run ON scan_file_telemetry(run_id, artifact_type, validation_status);
CREATE INDEX IF NOT EXISTS idx_file_inventory_cache_sha ON file_inventory_cache(source_root, sha256);
CREATE INDEX IF NOT EXISTS idx_correction_scope ON discovery_correction(scope_run_id, entity_kind, selector, active);
CREATE INDEX IF NOT EXISTS idx_scorecard_run ON scorecard_result(run_id, status, name);
