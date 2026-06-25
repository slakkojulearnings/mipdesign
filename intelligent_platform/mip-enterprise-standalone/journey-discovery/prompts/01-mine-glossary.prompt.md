---
mode: agent
description: Mine SME docs/PPTs/notes into an org business glossary (terms + the assets they name)
---

# Step 1 — Mine the org vocabulary from documents

You are a business analyst. Read the attached SME documents, PowerPoints, and notes
(`#file` the docs folder). Your job is **not** to judge whether they are correct — it is to
**extract the business vocabulary the organization uses** so we can later align code-derived
findings to *their* words.

For every business term you find, capture:
- `term` — the capability / domain / sub-domain / customer-journey name as written.
- `kind` — one of: `domain` | `sub_domain` | `capability` | `journey`.
- `definition` — one plain sentence, in the document's own language.
- `named_assets` — every concrete technical name the text mentions near that term: program
  names, transaction codes, screen/map names, table names, job names (UPPERCASE).
- `source_doc` — the file it came from.

Rules:
- Quote, don't invent. If a term has no named assets, still record it (`named_assets: []`).
- Keep journey names verbatim (e.g. "Open a new card", "Dispute a charge").
- Do not merge synonyms yet — capture them as written; reconciliation comes later.

**Output**: a single JSON file `journey-discovery/glossary.json`:
```json
{"terms": [
  {"term": "...", "kind": "capability", "definition": "...",
   "named_assets": ["CARDACT", "CRDACT01", "CARD_MASTER"], "source_doc": "deck_2019.pptx"}
]}
```

Then tell me to run:
`python journey-discovery/check_freshness.py --db <DB> --glossary journey-discovery/glossary.json`
— it will mark each term **relevant / stale / obsolete** by checking its named assets against
the live database, so we keep the business's words but trust only the parts the code confirms.
