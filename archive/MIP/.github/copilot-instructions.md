recommendation

Before writing any code, create a workspace-level file:

.github/copilot-instructions.md

and a skill:

skills/mainframe-modernization-architect/skill.md

These two files are probably the highest ROI files you can create for your VS Code + GitHub Copilot setup.

The objective is:

Make Copilot think like a Mainframe Modernization Architect
Keep architecture consistent
Prevent random code generation
Enforce MIP standards
Enable reuse across teams

These two files will dramatically improve GitHub Copilot's consistency and are the first things I would create after setting up the workspace.

# MIP - GitHub Copilot Instructions

## Purpose

You are assisting in the development of the Mainframe Intelligence Platform (MIP).

MIP is an enterprise platform that transforms legacy application source code into metadata, relationships, knowledge graphs, reasoning capabilities, and modernization intelligence.

The platform focuses on:

* COBOL
* JCL
* DB2
* VSAM
* IMS
* CICS
* Copybooks

The goal is NOT code conversion.

The goal is enterprise understanding.

---

# Core Philosophy

Always think in the following order:

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

Never skip layers.

---

# Architecture Principles

Follow:

* Clean Architecture
* SOLID Principles
* Domain Driven Design
* Plugin Architecture
* Separation of Concerns

Prefer maintainability over cleverness.

Prefer readability over optimization.

Prefer explicitness over magic.

---

# Technology Stack

Python 3.13

FastAPI

Pydantic v2

SQLite

NetworkX

Pytest

Google ADK (future phases)

---

# Development Approach

Always follow:

1. Design
2. Review
3. Critique
4. Improve
5. Implement
6. Test
7. Refactor

Never jump directly to implementation.

---

# Coding Standards

All code must:

* Use type hints
* Use dataclasses or Pydantic models
* Include docstrings
* Include logging
* Include unit tests
* Handle exceptions explicitly

Avoid:

* Global variables
* Tight coupling
* Circular dependencies
* Hidden side effects

---

# Repository Structure

src/

domain/

discovery/

parsers/

repository/

graph/

services/

api/

common/

tests/

docs/

skills/

prompts/

---

# Parsing Rules

Parser implementations must:

* Be deterministic
* Be repeatable
* Be testable
* Not depend on LLMs

Never use AI to parse source code.

Use explicit parsing logic.

---

# Metadata Rules

Metadata is the source of truth.

Every parser must generate metadata.

Every metadata object must have:

* Identifier
* Name
* Source Path
* Artifact Type

---

# Relationship Rules

Every relationship must contain:

Source

Target

Relationship Type

Confidence

Discovery Source

Examples:

CALLS

USES

READS

UPDATES

EXECUTES

---

# NetworkX Standards

NetworkX is the graph engine.

Nodes:

Program

Job

Copybook

Table

Dataset

Transaction

Edges:

CALLS

USES

READS

UPDATES

EXECUTES

Never create graph nodes without metadata.

---

# SQLite Standards

Use SQLite as the local metadata repository.

Every entity must have:

Primary Key

Created Timestamp

Updated Timestamp

Source File

Never store duplicate entities.

---

# Logging Standards

Use structured logging.

Include:

File

Parser

Artifact

Execution Time

Errors

Do not use print statements.

---

# Testing Standards

Every parser requires:

Unit Tests

Edge Cases

Negative Tests

Malformed Input Tests

Target Coverage:

80%+

---

# Copilot Behavior

When asked to implement:

1. Propose architecture first.
2. Identify risks.
3. Suggest improvements.
4. Generate code only after design approval.

Always explain trade-offs.

Never generate unnecessary complexity.

---

# MIP Vision

The purpose of MIP is to preserve enterprise knowledge and enable modernization through understanding.

Always optimize for:

Knowledge Extraction

Relationship Discovery

Enterprise Understanding

Modernization Readiness

Not code generation.
