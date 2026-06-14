# Purpose

Perform a complete repository inventory.

# Prompt

Use the repository-discovery skill. Scan recursively, including extensionless files. Record path, size, content hash, encoding, classification, confidence, reasons, and errors. Reconcile filesystem count with inventory count. Produce artifact counts, unknowns, ignored items, and a todo ledger. Never silently skip a file.

# Required Output

- assumptions
- evidence used
- proposed or completed work
- tests and validation
- unknowns and risks
- next executable step

# Completion Rule

Do not declare completion until the stated acceptance criteria or validation commands pass. Follow `CLAUDE.md` and the relevant skill.
