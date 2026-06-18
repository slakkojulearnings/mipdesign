# Document COBOL Programs in Parallel

Use the `repository-discovery` skill to ensure `memory/todo.list` is complete.

Launch multiple instances of the COBOL documentation translator, each claiming a different `PENDING` COBOL artifact. Each worker must:

- process only its claimed source path
- generate the standard program document
- record evidence and unresolved references
- update catalog and relationships through serialized helpers
- mark the todo item complete only after validation

Stop dispatching when no claimable items remain. Then run index validation and report coverage, blocked items, and unknowns.
