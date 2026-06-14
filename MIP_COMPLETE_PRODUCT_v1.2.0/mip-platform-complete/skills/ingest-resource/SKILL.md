---
name: ingest-resource
description: Brings a URL, article, transcript, notes file, attachment, or repository reference into the MIP Internal OS. Use to detect source type, read content, summarize it, file it under knowledge, and cross-reference related material with provenance.
license: Apache-2.0
compatibility: Works with skills-aware coding agents; repository workflows assume Python 3.12+, Git, and local file access.
metadata:
  author: mip-project
  version: "1.0"
---


# Ingest Resource

## Workflow

1. Detect source type: URL, repository, article, transcript, notes, attachment, or document.
2. Capture provenance: title, author/owner, source location, retrieval date, license when known.
3. Read or fetch the content using an appropriate tool.
4. Store raw content or a source pointer under `resources/raw/` according to policy.
5. Create a concise evidence-preserving summary under `resources/summaries/`.
6. Extract reusable practices, decisions, risks, and open questions.
7. Cross-reference canonical MIP files and related resources.
8. Do not merge external guidance into canonical instructions automatically; propose or apply a reviewed surgical change.
9. Record ingestion in `memory/processed.log`.

## Success Criteria

The resource is findable, provenance is preserved, summary is accurate, and relevant cross-references exist.

## Operating Rules

- Follow `CLAUDE.md`.
- Preserve source evidence and confidence.
- Do not modify `mfcode/`.
- Keep generated material under `knowledge/` or `output/`.
- Use the work ledger before processing repository artifacts.
- Report unresolved references and unknowns explicitly.
