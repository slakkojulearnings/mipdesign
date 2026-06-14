# Enterprise Data Structure Discovery

> Prompt 04 · Category: Discovery · Skills: [mainframe-code-analyst](../../03-skills/mainframe-code-analyst/SKILL.md), [security-compliance-analyst](../../03-skills/security-compliance-analyst/SKILL.md)
> Honors [MIP Engineering Principles](../../03-skills/MIP_ENGINEERING_PRINCIPLES.md).

## Purpose
Build a complete inventory of enterprise data structures and identify shared business information models.

## Context
Copybooks often contain decades of embedded business knowledge.

## Inputs
Copybook source files.

## Instructions
**Extract:** Copybook Name · Record Structures · OCCURS Clauses · REDEFINES Clauses · Key Fields · Data Types · Field Lengths · Validation Rules · Business Codes · Reference Data.

**Identify:** Shared Structures · Canonical Data Models · Sensitive Data Fields · PII Indicators · Financial Data Indicators · Regulatory Data Indicators.

**Generate:** Data Structure Catalog · Reuse Analysis · Data Complexity Analysis · Sensitive Data Assessment.

## Expected Output
- Copybook Inventory `| Copybook | Records | Key Fields |`
- Structural Complexity Report
- Shared Data Models
- Sensitive Data Assessment
- Reuse Analysis

## Constraints
Do not invent business meaning. Use evidence-based classification; sensitive-data classifications carry a confidence score, and low-confidence ones are flagged for review.

## Success Criteria
All copybooks represented consistently and analyzed for enterprise significance.

## Example Usage
Analyze copybooks and identify shared enterprise data structures.

## Review Checklist
- Structures extracted?
- OCCURS identified?
- REDEFINES identified?
- Sensitive fields identified?
- Reuse measured?
