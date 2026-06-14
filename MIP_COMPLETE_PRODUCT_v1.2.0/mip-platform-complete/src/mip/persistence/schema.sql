PRAGMA foreign_keys = ON;
PRAGMA journal_mode = WAL;
PRAGMA synchronous = NORMAL;

CREATE TABLE IF NOT EXISTS tenant (
    id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

INSERT OR IGNORE INTO tenant(id, name) VALUES ('default', 'Default Tenant');

CREATE TABLE IF NOT EXISTS scan_run (
    id TEXT PRIMARY KEY,
    tenant_id TEXT NOT NULL DEFAULT 'default',
    source_root TEXT NOT NULL,
    started_at TEXT NOT NULL,
    completed_at TEXT,
    status TEXT NOT NULL,
    file_count INTEGER NOT NULL DEFAULT 0,
    parsed_count INTEGER NOT NULL DEFAULT 0,
    unknown_count INTEGER NOT NULL DEFAULT 0,
    asset_count INTEGER NOT NULL DEFAULT 0,
    relationship_count INTEGER NOT NULL DEFAULT 0,
    issue_count INTEGER NOT NULL DEFAULT 0,
    tool_version TEXT NOT NULL,
    FOREIGN KEY(tenant_id) REFERENCES tenant(id)
);

CREATE TABLE IF NOT EXISTS source_file (
    id TEXT PRIMARY KEY,
    tenant_id TEXT NOT NULL DEFAULT 'default',
    scan_id TEXT NOT NULL,
    relative_path TEXT NOT NULL,
    sha256 TEXT NOT NULL,
    size_bytes INTEGER NOT NULL,
    artifact_type TEXT NOT NULL,
    classification_confidence REAL NOT NULL,
    classification_reasons_json TEXT NOT NULL,
    encoding TEXT,
    is_binary INTEGER NOT NULL DEFAULT 0,
    parse_status TEXT NOT NULL DEFAULT 'DISCOVERED',
    FOREIGN KEY(scan_id) REFERENCES scan_run(id) ON DELETE CASCADE,
    UNIQUE(scan_id, relative_path)
);

CREATE TABLE IF NOT EXISTS asset (
    id TEXT PRIMARY KEY,
    tenant_id TEXT NOT NULL DEFAULT 'default',
    scan_id TEXT NOT NULL,
    source_file_id TEXT,
    asset_type TEXT NOT NULL,
    technical_name TEXT NOT NULL,
    readable_name TEXT,
    attributes_json TEXT NOT NULL,
    confidence REAL NOT NULL,
    status TEXT NOT NULL DEFAULT 'OBSERVED',
    FOREIGN KEY(scan_id) REFERENCES scan_run(id) ON DELETE CASCADE,
    FOREIGN KEY(source_file_id) REFERENCES source_file(id) ON DELETE SET NULL,
    UNIQUE(scan_id, asset_type, technical_name)
);

CREATE TABLE IF NOT EXISTS relationship (
    id TEXT PRIMARY KEY,
    tenant_id TEXT NOT NULL DEFAULT 'default',
    scan_id TEXT NOT NULL,
    relationship_type TEXT NOT NULL,
    source_asset_id TEXT NOT NULL,
    target_asset_id TEXT NOT NULL,
    attributes_json TEXT NOT NULL,
    confidence REAL NOT NULL,
    status TEXT NOT NULL DEFAULT 'OBSERVED',
    FOREIGN KEY(scan_id) REFERENCES scan_run(id) ON DELETE CASCADE,
    FOREIGN KEY(source_asset_id) REFERENCES asset(id) ON DELETE CASCADE,
    FOREIGN KEY(target_asset_id) REFERENCES asset(id) ON DELETE CASCADE,
    UNIQUE(scan_id, relationship_type, source_asset_id, target_asset_id, attributes_json)
);

CREATE TABLE IF NOT EXISTS evidence (
    id TEXT PRIMARY KEY,
    tenant_id TEXT NOT NULL DEFAULT 'default',
    scan_id TEXT NOT NULL,
    entity_kind TEXT NOT NULL,
    entity_id TEXT NOT NULL,
    source_path TEXT NOT NULL,
    line_start INTEGER,
    line_end INTEGER,
    evidence_text TEXT NOT NULL,
    extractor TEXT NOT NULL,
    confidence REAL NOT NULL,
    FOREIGN KEY(scan_id) REFERENCES scan_run(id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS parse_issue (
    id TEXT PRIMARY KEY,
    tenant_id TEXT NOT NULL DEFAULT 'default',
    scan_id TEXT NOT NULL,
    source_file_id TEXT,
    severity TEXT NOT NULL,
    message TEXT NOT NULL,
    line_number INTEGER,
    FOREIGN KEY(scan_id) REFERENCES scan_run(id) ON DELETE CASCADE,
    FOREIGN KEY(source_file_id) REFERENCES source_file(id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS validation_result (
    id TEXT PRIMARY KEY,
    tenant_id TEXT NOT NULL DEFAULT 'default',
    scan_id TEXT NOT NULL,
    validation_type TEXT NOT NULL,
    status TEXT NOT NULL,
    entity_kind TEXT,
    entity_id TEXT,
    message TEXT NOT NULL,
    created_at TEXT NOT NULL,
    FOREIGN KEY(scan_id) REFERENCES scan_run(id) ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS idx_source_file_scan_type ON source_file(scan_id, artifact_type);
CREATE INDEX IF NOT EXISTS idx_asset_scan_type ON asset(scan_id, asset_type);
CREATE INDEX IF NOT EXISTS idx_asset_scan_name ON asset(scan_id, technical_name);
CREATE INDEX IF NOT EXISTS idx_relationship_source ON relationship(scan_id, source_asset_id);
CREATE INDEX IF NOT EXISTS idx_relationship_target ON relationship(scan_id, target_asset_id);
CREATE INDEX IF NOT EXISTS idx_relationship_type ON relationship(scan_id, relationship_type);
CREATE INDEX IF NOT EXISTS idx_evidence_entity ON evidence(scan_id, entity_kind, entity_id);
CREATE INDEX IF NOT EXISTS idx_issue_scan ON parse_issue(scan_id, severity);


CREATE TABLE IF NOT EXISTS analysis_shard (
    id TEXT PRIMARY KEY,
    tenant_id TEXT NOT NULL DEFAULT 'default',
    scan_id TEXT,
    shard_index INTEGER NOT NULL,
    shard_count INTEGER NOT NULL,
    source_root TEXT NOT NULL,
    path_prefix TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'PLANNED',
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY(tenant_id) REFERENCES tenant(id),
    FOREIGN KEY(scan_id) REFERENCES scan_run(id) ON DELETE SET NULL
);
