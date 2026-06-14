# Batch Processing and Operational Flow Discovery

> Prompt 03 · Category: Discovery · Skills: [mainframe-code-analyst](../../03-skills/mainframe-code-analyst/SKILL.md), [resilience-engineer](../../03-skills/resilience-engineer/SKILL.md)
> Honors [MIP Engineering Principles](../../03-skills/MIP_ENGINEERING_PRINCIPLES.md).

## Purpose
Build a complete inventory of batch jobs, operational workflows, execution chains, and recovery dependencies.

## Context
JCL often represents the true operational architecture of the enterprise. Understanding execution chains is critical for resilience and modernization.

## Inputs
JCL members.

## Instructions
**Extract:** JOB Names · Steps · EXEC Statements · Procedures · Utilities · Datasets · GDGs · Sort Operations · Scheduler References · Restart Logic · Recovery Logic.

**Identify:** Batch Chains · Job Dependencies · Trigger Relationships · Critical Processing Windows · Long Running Jobs · Failure Recovery Paths.

**Capture:** Input Dependencies · Output Dependencies · Operational Sequences · Scheduling Constraints.

**Generate:** Batch Execution Graphs · Critical Path Analysis · Operational Risk Assessment · Recovery Dependency Maps.

## Expected Output
- Job Inventory `| Job | Step Count | Programs | Datasets |`
- Execution Summary
- Batch Chain Analysis
- Critical Path Analysis
- Recovery Dependency Analysis
- Operational Risk Assessment

## Constraints
Do not infer unsupported business meaning. Use observable evidence; attach confidence to any inferred dependency.

## Success Criteria
Every batch job and execution dependency is represented.

## Example Usage
Analyze all JCL members and build an enterprise execution architecture.

## Review Checklist
- Steps identified?
- Programs identified?
- Procedures identified?
- Scheduler references identified?
- Recovery logic identified?
- Critical paths identified?
