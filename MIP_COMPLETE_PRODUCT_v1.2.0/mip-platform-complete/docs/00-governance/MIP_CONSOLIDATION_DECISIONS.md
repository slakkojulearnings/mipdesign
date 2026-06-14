# MIP Consolidation Decisions

## Decision 1: One Canonical Document Per Concern

Earlier drafts used overlapping names such as metadata model, enterprise metadata model, graph model, graph engine, impact model, and impact engine. This pack keeps one architecture file per concern and places executable behavior in skills.

## Decision 2: Skills Are Operational, Prompts Are Invocations

A skill defines a durable workflow, constraints, and outputs. A prompt invokes that skill for a specific task. Prompts must not duplicate the entire skill.

## Decision 3: Ledgers Are the Minimum Viable Memory

`catalog.txt`, `relationships.txt`, `todo.list`, and `processed.log` are human-readable and versionable. SQLite may later mirror them, but the text format remains useful for review, recovery, and agent interoperability.

## Decision 4: Translation Is a Separate Stage

Discovery, documentation, and behavior characterization must finish before code translation. This prevents syntactically successful but semantically incorrect migrations.

## Decision 5: Parallelism Uses Claims, Not Hope

Parallel agents may process different files only after atomically claiming work items. The work ledger and content hash prevent duplicate processing.

## Decision 6: Business Names Are Hypotheses Until Validated

Readable names may be proposed from identifiers, comments, jobs, datasets, and behavior, but inferred names must carry confidence and review status.
