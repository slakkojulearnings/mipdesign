# COBOL Parser Architecture

> Prompt 06 · Category: Parsing · Skill: [mainframe-code-analyst](../../batch2/skills_framework/skills/mainframe-code-analyst/skill.md)
> Honors [MIP Engineering Principles](../../batch2/skills_framework/MIP_ENGINEERING_PRINCIPLES.md).

## Purpose
Design a production-grade COBOL parser capable of extracting metadata from enterprise COBOL applications.

## Context
COBOL programs contain: program definitions, business logic, program dependencies, database access, file access. The parser must extract metadata without attempting business interpretation.

## Parser Engineering Principles
Deterministic (same input → same output) · Explainable (every fact points to source evidence) · Extensible (future language variants) · Fault Tolerant (continue processing through source errors) · Observable (detailed extraction metrics).

## Inputs
COBOL source files.

## Instructions
Design a parser architecture capable of extracting:
- **Identification Division:** PROGRAM-ID · AUTHOR · INSTALLATION · DATE-WRITTEN
- **Environment Division:** File assignments · Configuration
- **Data Division:** Working Storage · File Section · Linkage Section
- **Procedure Division:** CALL Statements · PERFORM Statements · Paragraphs · Sections
- **Embedded SQL:** Tables · Views · Operations

**Generate:** Architecture Diagram · Modules · Data Models · Error Handling Strategy · Testing Strategy.

## Expected Output
- Parser Overview
- Component Diagram
- Metadata Extraction Flow
- Error Handling Design
- Testing Design

## Constraints
Do not generate implementation code. Focus on architecture and metadata extraction. Fault tolerance is mandatory — a malformed member must yield partial metadata + recorded errors, not a hard failure.

## Success Criteria
Parser supports enterprise-scale COBOL repositories.

## Example Usage
Design a parser architecture for a repository containing 10,000+ COBOL programs.

## Review Checklist
- PROGRAM-ID extraction supported?
- CALL extraction supported?
- SQL extraction supported?
- Fault tolerance defined?
- Metadata model aligned?
