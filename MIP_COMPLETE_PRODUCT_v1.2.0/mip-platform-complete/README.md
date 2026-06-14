# Mainframe Intelligence Platform

## v1.2.0 P0/P1/P2 Capability Implementation

This release implements root driver chain discovery, capability-to-files discovery, BRD generation, business rule catalogs, functional test scenario generation, and separated Python/Java application skeleton generation. It also includes configurable credit/debit card function skeletons for bank/product-specific behavior. See `docs/03-execution/MIP_P0_P1_P2_IMPLEMENTATION_GUIDE.md`.

## v1.1.0 Advanced Enterprise Additions

This release adds practical open-source support for COBOL COPY REPLACING metadata, symbolic JCL PROC expansion, generic scheduler imports, IMS, MQ, assembler, PL/I, deterministic distributed shard planning, and multi-tenant schema foundations. See `docs/ADVANCED_AREAS_IMPLEMENTATION.md`. (MIP)

## Consolidated Enterprise Engineering Pack

This repository pack is the canonical starting point for building MIP as a repeatable, evidence-driven legacy modernization platform.

MIP follows this sequence:

```text
Raw Sources
    ↓
Deterministic Discovery
    ↓
Canonical Metadata
    ↓
Relationships and Lineage
    ↓
Knowledge Graph
    ↓
Reasoning and Impact Analysis
    ↓
Verified Modernization
```

## Start Here

1. Read `CLAUDE.md` or `.github/copilot-instructions.md`.
2. Read `docs/00-governance/MIP_CANONICAL_FILE_INDEX.md`.
3. Place source code under `mfcode/` without renaming or modifying it.
4. Run discovery using `skills/repository-discovery/SKILL.md`.
5. Maintain `memory/todo.list`, `memory/catalog.txt`, and `memory/relationships.txt`.
6. Do not begin translation until discovery evidence and acceptance criteria are complete.

## Repository Intent

This pack intentionally separates:

- **Source evidence**: immutable files under `mfcode/`
- **Generated knowledge**: Markdown under `knowledge/`
- **Indexes and state**: text ledgers under `memory/`
- **Reusable behavior**: Agent Skills under `skills/`
- **Reusable task requests**: prompts under `prompts/`
- **Architecture and governance**: documents under `docs/`

## Technology Defaults

- Python 3.12+
- Google ADK for orchestration
- SQLite for local persistence
- NetworkX for local graph analysis
- PostgreSQL as the enterprise persistence evolution path
- GitHub Copilot Chat or another skills-aware coding agent

## Non-Goals

The initial platform does not perform blind source-to-source translation, automatic production deployment, or unreviewed architecture generation. Understanding and verification come first.
