# Enterprise Repository Discovery

> Prompt 01 · Category: Discovery · Skill: [mainframe-code-analyst](../../03-skills/mainframe-code-analyst/SKILL.md)
> Honors [MIP Engineering Principles](../../03-skills/MIP_ENGINEERING_PRINCIPLES.md).

## Purpose
Perform a complete enterprise repository scan and create a comprehensive inventory of all technical, operational, and business artifacts.

## Context
Large enterprise repositories often contain significantly more than source code. Discovery should identify: COBOL Programs, JCL, PROCs, Copybooks, DB2 SQL, VSAM Definitions, CICS Definitions, IMS Definitions, MQ Definitions, REXX Scripts, Easytrieve Programs, Scheduler Definitions, Control Cards, Utilities, Configuration Files, API Specifications, Documentation, Architecture Diagrams, Operational Runbooks, Test Assets, Deployment Scripts.

## Inputs
Repository root folder.

## Instructions
Analyze the repository recursively.

**Identify:** Source Artifacts · Configuration Artifacts · Operational Artifacts · Infrastructure Artifacts · Documentation Assets · Test Assets · Security Assets.

**Capture:** File Types · Naming Standards · Folder Structures · Ownership Indicators · Environment References · Version Indicators.

**Detect:** Unknown File Types · Duplicate Assets · Orphaned Assets · Dead Assets · Archived Components · Missing Documentation.

**Generate:** Repository Heat Maps · Artifact Distribution Analysis · Technology Footprint Analysis · Repository Health Assessment.

## Expected Output
- Executive Summary
- Repository Statistics (Artifact Type / Count)
- Technology Landscape
- Repository Inventory `| Type | Name | Path | Description |`
- Repository Health Assessment
- Discovery Risks
- Modernization Opportunities
- Recommendations

## Constraints
Do not infer unsupported business functionality. Use observable evidence only. Where classification is uncertain, attach a confidence level and flag for review rather than guessing.

## Success Criteria
Every repository artifact is cataloged, classified, and traceable.

## Example Usage
Analyze the repository under `mfcode` and produce a complete enterprise artifact inventory.

## Review Checklist
- All folders scanned?
- Unknown files identified?
- Duplicate assets identified?
- Repository health assessed?
- Technology footprint generated?
