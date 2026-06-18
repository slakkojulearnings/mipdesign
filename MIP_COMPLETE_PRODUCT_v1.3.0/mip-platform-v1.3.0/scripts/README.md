# Repository Helper Scripts

- `validate_memory_indices.py`: validates field counts and duplicate identities.
- `claim_todo_item.py`: claims the next pending artifact.
- `validate_skills.sh`: validates Agent Skills when `skills-ref` is installed.

These scripts are intentionally small. Add locking/database coordination only after concurrent execution requires it.
