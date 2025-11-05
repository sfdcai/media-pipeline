# TASKS

## TASK-001: Implement /api/dedup/start
Context: docs/API.md, docs/SCHEMAS.md
Acceptance:
- Reads config
- Hashes files deterministically
- Updates DB with status
- Idempotent re-run

## TASK-002: Implement /api/batch/create
Acceptance:
- Respects max_size_gb
- Deterministic ordering
- Writes manifest.json
- Updates DB

... add more tasks as needed.
