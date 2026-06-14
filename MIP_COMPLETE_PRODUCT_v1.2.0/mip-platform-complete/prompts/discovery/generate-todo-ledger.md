# Generate Complete Todo Ledger

Scan the repository recursively and create one todo record per source artifact.

Requirements:

- no duplicate source path
- include source content hash
- include unresolved/unknown files
- reconcile todo count with inventory count
- preserve existing DONE rows whose hash is unchanged
- mark changed DONE rows as STALE
- never remove a row without an audit entry

Run validation and report missing, duplicate, and conflicting rows.
