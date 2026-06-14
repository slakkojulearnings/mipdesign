# JCL Parser Architecture

> Prompt 07 · Category: Parsing · Skill: [mainframe-code-analyst](../../batch2/skills_framework/skills/mainframe-code-analyst/skill.md)
> Honors [MIP Engineering Principles](../../batch2/skills_framework/MIP_ENGINEERING_PRINCIPLES.md).

## Purpose
Design a parser for Job Control Language.

## Context
JCL defines: execution flows, program execution, dataset usage, batch orchestration. Understanding JCL is critical for root-program identification.

## Inputs
JCL source members.

## Instructions
Design parser architecture capable of extracting:
- **Job Metadata:** JOB Statements · Parameters
- **Execution Metadata:** EXEC Statements · Programs · Procedures
- **Dataset Metadata:** DD Statements · Inputs · Outputs
- **Scheduling Metadata:** Dependencies · Conditions

Generate architecture and metadata model.

## Expected Output
- Parser Design
- Metadata Model
- Extraction Flow
- Error Handling

## Constraints
No implementation code. Fault-tolerant extraction; partial results + recorded errors on malformed members.

## Success Criteria
Every JCL job can be represented as metadata.

## Example Usage
Design a parser for 5,000 production JCL jobs.

## Review Checklist
- JOB extraction supported?
- EXEC extraction supported?
- DD extraction supported?
- Dependency extraction supported?
