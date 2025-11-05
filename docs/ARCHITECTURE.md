# Architecture

Modules (independently callable via API):
1. Deduplicator
2. Batch Manager
3. Syncthing Monitor
4. EXIF Sorter
5. Cleanup
6. Config & Insights
7. Workflow Orchestrator

Process guarantees: idempotent endpoints, atomic moves, resumable via DB, deterministic ordering.
