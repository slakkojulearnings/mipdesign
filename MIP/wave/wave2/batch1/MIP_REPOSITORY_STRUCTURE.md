# MIP_REPOSITORY_STRUCTURE.md

# Mainframe Intelligence Platform

## Repository Structure Standard

Version: 1.0

Status: Approved

Owner: MIP Engineering Team

---

# Purpose

This document defines the official repository structure for the Mainframe Intelligence Platform (MIP).

The objective is to ensure:

* Consistency
* Maintainability
* Scalability
* Team Collaboration
* AI-Assisted Development

Every contributor must follow this structure.

No new top-level directories should be created without architecture review.

---

# Design Principles

The repository structure follows:

* Clean Architecture
* Domain Driven Design
* Modular Monolith
* Plugin-Based Discovery
* Metadata First Design

---

# Architectural Philosophy

MIP transforms:

Source Code
↓

Metadata
↓

Relationships
↓

Knowledge Graph
↓

Reasoning
↓

Modernization Intelligence

The repository structure mirrors this flow.

---

# High Level Repository Layout

```text
mip-platform/

.github/
docs/
skills/
prompts/

src/
tests/

scripts/
tools/

examples/
output/

data/
logs/

deployment/
```

---

# Repository Ownership

| Folder     | Purpose             | Owner             |
| ---------- | ------------------- | ----------------- |
| docs       | Documentation       | Architecture Team |
| skills     | Copilot Skills      | Platform Team     |
| prompts    | Prompt Library      | Platform Team     |
| src        | Production Code     | Engineering Team  |
| tests      | Test Suite          | Engineering Team  |
| scripts    | Automation          | DevOps Team       |
| tools      | Developer Utilities | Platform Team     |
| examples   | Sample Repositories | Engineering Team  |
| output     | Generated Artifacts | Runtime           |
| data       | SQLite Databases    | Runtime           |
| logs       | Runtime Logs        | Runtime           |
| deployment | Deployment Assets   | DevOps Team       |

---

# .github

Purpose:

Repository Governance

Structure:

```text
.github/

copilot-instructions.md

workflows/

CODEOWNERS

pull_request_template.md

issue_template.md
```

---

# copilot-instructions.md

Purpose:

Global engineering contract.

Responsibilities:

* Coding standards
* Architecture guidance
* Metadata-first principles
* Review expectations

Required:

Yes

---

# workflows

Purpose:

GitHub Actions

Examples:

```text
lint.yml

tests.yml

build.yml
```

---

# docs

Purpose:

All non-code knowledge.

Contains:

Architecture

Roadmaps

Standards

Playbooks

Decision Records

Leadership Materials

---

# docs Structure

```text
docs/

00-foundation/

01-vision/

02-strategy/

03-architecture/

04-engineering/

05-roadmap/

06-tsys/

07-skills/

08-prompts/

09-diagrams/
```

---

# docs/00-foundation

Purpose:

Core project documents.

Examples:

```text
MIP_PROJECT_CHARTER.md

MIP_MISSION.md

MIP_VISION.md
```

---

# docs/03-architecture

Purpose:

System architecture.

Examples:

```text
MIP_TARGET_ARCHITECTURE.md

MIP_DOMAIN_MODEL.md

MIP_KNOWLEDGE_GRAPH_MODEL.md

MIP_METADATA_MODEL.md
```

---

# docs/04-engineering

Purpose:

Engineering standards.

Examples:

```text
MIP_ENGINEERING_PLAYBOOK.md

MIP_WORKSPACE_BOOTSTRAP.md

MIP_CODING_STANDARDS.md
```

---

# skills

Purpose:

Reusable GitHub Copilot Skills.

Structure:

```text
skills/

repository-engineer/

skill.md

mainframe-modernization-architect/

skill.md

mainframe-code-analyst/

skill.md

metadata-modeler/

skill.md

graph-engineer/

skill.md

sqlite-engineer/

skill.md

test-engineer/

skill.md

code-reviewer/

skill.md

documentation-writer/

skill.md
```

---

# Skill Structure Standard

Every skill contains:

```text
skill.md

examples/

templates/

prompts/
```

---

# prompts

Purpose:

Reusable Prompt Library

Structure:

```text
prompts/

architecture/

discovery/

parsing/

metadata/

graph/

testing/

review/

modernization/
```

---

# Prompt Standard

Every prompt must contain:

Role

Context

Requirements

Output Format

Constraints

Review Questions

---

# src

Purpose:

Production code.

No experimental code.

No notebooks.

No prototypes.

---

# src Structure

```text
src/

api/

common/

config/

domain/

discovery/

parsers/

metadata/

repository/

graph/

services/

reasoning/

modernization/
```

---

# src/domain

Purpose:

Core business models.

Contains:

Program

Job

Copybook

Table

Relationship

Dataset

Transaction

---

# Rules

No external dependencies.

Pure business objects only.

---

# src/discovery

Purpose:

Repository discovery.

Responsibilities:

* File scanning
* Artifact classification
* Inventory generation

---

# src/parsers

Purpose:

Source code parsing.

Subfolders:

```text
cobol/

jcl/

copybook/

db2/

vsam/

cics/
```

Responsibilities:

Extract metadata.

Never infer business meaning.

---

# src/metadata

Purpose:

Metadata management.

Responsibilities:

Metadata creation

Metadata validation

Metadata persistence

---

# src/repository

Purpose:

Persistence layer.

Responsibilities:

SQLite operations

Future PostgreSQL operations

---

# src/graph

Purpose:

Knowledge Graph Layer.

Responsibilities:

Node creation

Edge creation

Graph traversal

Graph queries

Technology:

NetworkX

---

# src/services

Purpose:

Application services.

Responsibilities:

Orchestration

Workflow execution

Use case implementation

---

# src/reasoning

Purpose:

Future capability.

Phase 6+

Responsibilities:

Impact analysis

Dependency analysis

Flow analysis

---

# src/modernization

Purpose:

Future capability.

Phase 8+

Responsibilities:

Service identification

API identification

Migration recommendations

---

# tests

Purpose:

All automated testing.

Structure:

```text
tests/

unit/

integration/

performance/

fixtures/
```

---

# Test Rule

Every production module must have tests.

Minimum coverage:

80%

Target coverage:

90%

---

# scripts

Purpose:

Automation.

Examples:

```text
bootstrap.py

generate_inventory.py

export_graph.py
```

---

# tools

Purpose:

Developer utilities.

Examples:

```text
sqlite_viewer.py

metadata_validator.py
```

---

# examples

Purpose:

Sample repositories.

Examples:

```text
sample-cobol/

sample-jcl/

sample-db2/
```

---

# output

Purpose:

Generated artifacts.

Examples:

```text
inventory.json

metadata.json

call_graph.json
```

Never commit output files.

---

# data

Purpose:

Local databases.

Examples:

```text
mip.db

metadata.db
```

Never commit production databases.

---

# logs

Purpose:

Runtime logs.

Examples:

```text
application.log

parser.log
```

Never commit logs.

---

# deployment

Purpose:

Deployment assets.

Examples:

```text
docker/

kubernetes/

terraform/
```

Future phases only.

---

# Dependency Rules

Allowed:

```text
api
    ↓

services
    ↓

domain

repository

graph
```

Forbidden:

```text
domain
    ↓
api

parsers
    ↓
api
```

Domain must remain independent.

---

# Naming Standards

Packages:

snake_case

Modules:

snake_case

Classes:

PascalCase

Functions:

snake_case

Constants:

UPPER_CASE

---

# Branch Strategy

main

development

feature/*

bugfix/*

release/*

---

# Definition Of Done

A repository is compliant when:

✓ Folder structure matches this document

✓ Skills installed

✓ Prompt library installed

✓ Copilot instructions configured

✓ Testing structure created

✓ Documentation structure created

✓ Dependency rules enforced

---

# Success Metric

A new engineer can:

* Clone the repository
* Understand the structure
* Find code quickly
* Add a feature safely
* Use Copilot effectively

Within one day of onboarding.

This repository structure becomes the foundation for all future MIP phases and all future modernization initiatives.
