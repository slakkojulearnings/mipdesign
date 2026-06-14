-- MIP canonical metadata store — SQLite (Phase 0/1)
-- Designed to migrate to PostgreSQL without redesign.
-- Every entity and relationship carries the evidence envelope
-- (source_evidence, discovery_method, confidence, validation_status, discovered_at).
--
-- Confidence is stored as REAL in [0.0, 1.0]. validation_status is one of
-- 'confirmed' | 'inferred' | 'needs_review'.

PRAGMA foreign_keys = ON;

-- ---------------------------------------------------------------------------
-- Artifacts discovered by the scanner (Level 1: inventory)
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS artifact (
    artifact_id     TEXT PRIMARY KEY,           -- stable id (hash of path)
    path            TEXT NOT NULL,
    artifact_type   TEXT NOT NULL,              -- cobol | jcl | copybook | db2 | vsam | cics | unknown
    file_name       TEXT NOT NULL,
    size_bytes      INTEGER,
    line_count      INTEGER,
    -- evidence envelope
    source_evidence TEXT,                       -- e.g. "scan:cobol/PAYPST.cbl"
    discovery_method TEXT NOT NULL DEFAULT 'scan',
    confidence      REAL NOT NULL DEFAULT 1.0,
    validation_status TEXT NOT NULL DEFAULT 'confirmed',
    discovered_at   TIMESTAMP NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_artifact_type ON artifact(artifact_type);
CREATE INDEX IF NOT EXISTS idx_artifact_path ON artifact(path);

-- ---------------------------------------------------------------------------
-- Programs (Level 2: metadata)
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS program (
    program_id      TEXT PRIMARY KEY,           -- PROGRAM-ID (canonical name)
    program_name    TEXT NOT NULL,
    language        TEXT NOT NULL DEFAULT 'cobol',
    artifact_id     TEXT REFERENCES artifact(artifact_id),
    line_count      INTEGER,
    -- evidence envelope
    source_evidence TEXT,
    discovery_method TEXT NOT NULL DEFAULT 'static-parse',
    confidence      REAL NOT NULL DEFAULT 1.0,
    validation_status TEXT NOT NULL DEFAULT 'confirmed',
    discovered_at   TIMESTAMP NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_program_name ON program(program_name);

-- ---------------------------------------------------------------------------
-- Jobs and steps (Level 2: metadata) — the source of root-driver discovery
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS job (
    job_id          TEXT PRIMARY KEY,           -- JOB name
    job_name        TEXT NOT NULL,
    artifact_id     TEXT REFERENCES artifact(artifact_id),
    source_evidence TEXT,
    discovery_method TEXT NOT NULL DEFAULT 'static-parse',
    confidence      REAL NOT NULL DEFAULT 1.0,
    validation_status TEXT NOT NULL DEFAULT 'confirmed',
    discovered_at   TIMESTAMP NOT NULL
);

CREATE TABLE IF NOT EXISTS job_step (
    step_id         TEXT PRIMARY KEY,           -- job_id + step name
    job_id          TEXT NOT NULL REFERENCES job(job_id),
    step_name       TEXT NOT NULL,
    program_name    TEXT,                       -- EXEC PGM= target (may be unresolved)
    step_order      INTEGER,
    source_evidence TEXT,
    discovery_method TEXT NOT NULL DEFAULT 'static-parse',
    confidence      REAL NOT NULL DEFAULT 1.0,
    validation_status TEXT NOT NULL DEFAULT 'confirmed',
    discovered_at   TIMESTAMP NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_step_job ON job_step(job_id);
CREATE INDEX IF NOT EXISTS idx_step_program ON job_step(program_name);

-- ---------------------------------------------------------------------------
-- Copybooks and tables (Level 2)
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS copybook (
    copybook_id     TEXT PRIMARY KEY,
    copybook_name   TEXT NOT NULL,
    artifact_id     TEXT REFERENCES artifact(artifact_id),
    source_evidence TEXT,
    discovery_method TEXT NOT NULL DEFAULT 'static-parse',
    confidence      REAL NOT NULL DEFAULT 1.0,
    validation_status TEXT NOT NULL DEFAULT 'confirmed',
    discovered_at   TIMESTAMP NOT NULL
);

CREATE TABLE IF NOT EXISTS db2_table (
    table_id        TEXT PRIMARY KEY,
    table_name      TEXT NOT NULL,
    source_evidence TEXT,
    discovery_method TEXT NOT NULL DEFAULT 'static-parse',
    confidence      REAL NOT NULL DEFAULT 1.0,
    validation_status TEXT NOT NULL DEFAULT 'confirmed',
    discovered_at   TIMESTAMP NOT NULL
);

-- ---------------------------------------------------------------------------
-- Relationships (Level 3: graph edges) — the heart of the platform
-- Generic edge table so call/batch/lineage graphs all materialize from here.
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS relationship (
    relationship_id TEXT PRIMARY KEY,
    source_type     TEXT NOT NULL,              -- program | job | job_step | copybook | db2_table | ...
    source_id       TEXT NOT NULL,
    rel_type        TEXT NOT NULL,              -- CALLS | EXECUTES | USES | READS | WRITES | CONTAINS | ...
    target_type     TEXT NOT NULL,
    target_id       TEXT NOT NULL,              -- may be an unresolved name (e.g. dynamic call target)
    -- evidence envelope
    source_evidence TEXT,
    discovery_method TEXT NOT NULL DEFAULT 'static-parse',
    confidence      REAL NOT NULL DEFAULT 1.0,
    validation_status TEXT NOT NULL DEFAULT 'confirmed',
    discovered_at   TIMESTAMP NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_rel_type   ON relationship(rel_type);
CREATE INDEX IF NOT EXISTS idx_rel_source ON relationship(source_type, source_id);
CREATE INDEX IF NOT EXISTS idx_rel_target ON relationship(target_type, target_id);
CREATE INDEX IF NOT EXISTS idx_rel_validation ON relationship(validation_status);

-- ---------------------------------------------------------------------------
-- Convenience views (graph materialization)
-- ---------------------------------------------------------------------------
-- Which programs each program calls
CREATE VIEW IF NOT EXISTS vw_program_calls AS
    SELECT source_id AS caller, target_id AS callee, confidence, validation_status
    FROM relationship WHERE rel_type = 'CALLS';

-- Which job executes which program (root-driver query backbone)
CREATE VIEW IF NOT EXISTS vw_job_programs AS
    SELECT j.job_name, s.step_name, s.program_name
    FROM job j JOIN job_step s ON s.job_id = j.job_id
    WHERE s.program_name IS NOT NULL;
